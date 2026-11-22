"""Receptor multiquadro: acha todos os quadros de uma captura e devolve os pacotes válidos.

Requisitos: RX-01 (detecção com limiar, todos os quadros), RX-03 (arquivo de
saída com sequência e payload), MET-02 (base da PER). Achados tratados: A1
(a referência decodifica um quadro só), A2 (sem limiar, ruído vira quadro) e
A18 (offset residual de até 1,6 kHz).

Etapas, para cada bloco da captura:
    1. desloca o sinal para a banda base (o TX transmite em LO + deslocamento);
    2. filtro de canal e decimação até cerca de 8 amostras por bit: sem isso o
       ruído da banda inteira capturada (2 MHz) afoga um sinal estreito;
    3. correlação coerente com o preâmbulo + Barker-13 modulados (29 bits
       inteiros), numa grade de hipóteses de frequência que cobre o offset
       máximo com perda de no máximo 0,9 dB (passo de 1/(2T), T = duração do
       modelo). A métrica é uma correlação de Pearson complexa: média do
       modelo removida e energia do sinal centrada no referencial da
       hipótese, para a portadora da OOK não correlacionar com qualquer dado.
       Fica entre 0 e 1 (Cauchy-Schwarz) e é comparada com um limiar fixo;
    4. supressão de não-máximos: um pico por quadro;
    5. por quadro: instante refinado por interpolação parabólica, offset
       grosso dado pela hipótese vencedora e refinado pela rotação de fase
       entre trechos do preâmbulo, corrigido,
       fase estimada (só a BPSK coerente usa), demodulação (sdrlink.modem) e
       interpretação (sdrlink.quadro).
A captura é processada em blocos com sobreposição de um quadro máximo, e um
quadro que cai na emenda é lido uma vez só.

Restrição: a taxa de amostragem dividida pela taxa de bits tem de ser inteira.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from scipy.signal import fftconvolve, firwin, resample_poly

from sdrlink import canal, modem, quadro
from sdrlink.modem import ConfigModem
from sdrlink.quadro import Pacote

Sinal = NDArray[np.complex128]
Interpretador = Callable[[NDArray[np.uint8]], quadro.Leitura]  # bits depois do sync -> leitura

BITS_PREFIXO = len(quadro.PREAMBULO) + len(quadro.SYNC)  # 29 bits conhecidos
LIMIAR_PADRAO = (
    0.5  # medido: quadros reais acima de 0,59 a partir de 8 dB; falsos 99,99% abaixo de 0,43
)
OFFSET_MAX_PADRAO_HZ = 3000.0
SPS_INTERNO_MIN = 8  # o receptor decima até ficar com pelo menos 8 amostras por bit
TRECHOS_ESTIMATIVA = 4  # o offset é medido entre pelo menos 4 trechos do preâmbulo
# meia banda do filtro de detecção, em múltiplos da taxa de bits: um pouco acima da banda a 99%
# de cada pulso (etapa3_modulacoes.md); tira da normalização o ruído fora da banda do sinal
MEIA_BANDA_DETECCAO_RB = {"rrc": 0.75, "gaussiano": 1.0, "retangular": 1.0}
MEIA_BANDA_FSK_RETANGULAR_RB = 1.25
COEFICIENTES_POR_BIT = 8  # duração do filtro de detecção: 8 bits
DISTANCIA_MIN_BITS = 60  # dois sincronismos não ficam mais perto que isso (quadro mínimo: 85 bits)
MAX_DETECCOES_POR_BLOCO = 100_000
BLOCO_PADRAO = 2**22  # amostras por bloco (cerca de 2 s a 2,048 MS/s)
MAX_BLOCOS = 100_000


@dataclass(frozen=True)
class ConfigReceptor:
    """Parâmetros do receptor.

    Attributes:
        modem: modulação e pulso do TX, com sps = amostras por bit na taxa da captura.
        taxa_sps: taxa de amostragem da captura.
        deslocamento_hz: posição do sinal em relação ao centro da captura.
        limiar: valor mínimo da métrica de correlação normalizada (0 a 1).
        offset_max_hz: maior offset residual esperado (define a grade de hipóteses).
        guardar_bits: guarda em cada detecção os bits demodulados depois do sync,
            mesmo com CRC falho (para a BER com sequência conhecida, MET-03).
    """

    modem: ConfigModem
    taxa_sps: float
    deslocamento_hz: float = 0.0
    limiar: float = LIMIAR_PADRAO
    offset_max_hz: float = OFFSET_MAX_PADRAO_HZ
    guardar_bits: bool = False

    def __post_init__(self) -> None:
        """Rejeita parâmetros incoerentes.

        Raises:
            ValueError: taxa, limiar, offset ou deslocamento inválidos.
        """
        if self.taxa_sps <= 0:
            raise ValueError(f"taxa de amostragem inválida: {self.taxa_sps}")
        if not 0 < self.limiar < 1:
            raise ValueError(f"limiar fora de (0, 1): {self.limiar}")
        if not 0 < self.offset_max_hz < self.taxa_interna / 8:
            raise ValueError(f"offset máximo fora de (0, taxa interna/8): {self.offset_max_hz}")
        if abs(self.deslocamento_hz) >= self.taxa_sps / 2:
            raise ValueError(f"deslocamento fora da banda capturada: {self.deslocamento_hz}")

    @property
    def decimacao(self) -> int:
        """Maior divisor de sps que deixa pelo menos SPS_INTERNO_MIN amostras por bit."""
        sps = self.modem.sps
        candidatos = [d for d in range(1, sps + 1) if sps % d == 0 and sps // d >= SPS_INTERNO_MIN]
        return max(candidatos, default=1)

    @property
    def taxa_interna(self) -> float:
        """Taxa de amostragem depois da decimação."""
        return self.taxa_sps / self.decimacao

    @property
    def modem_interno(self) -> ConfigModem:
        """A mesma modulação, com as amostras por bit depois da decimação."""
        return dataclasses.replace(self.modem, sps=self.modem.sps // self.decimacao)

    def modelo(self) -> Sinal:
        """Preâmbulo + Barker-13 modulados, como aparecem no início de todo quadro (taxa interna).

        Gerado na taxa da captura e decimado pelo mesmo filtro que o sinal, para o
        modelo passar exatamente pela mesma cadeia (sem desvio de alinhamento).
        """
        prefixo = np.concatenate([quadro.PREAMBULO, quadro.SYNC])
        sinal = modem.modular(prefixo, self.modem)
        if self.decimacao > 1:
            sinal = np.asarray(resample_poly(sinal, 1, self.decimacao), dtype=np.complex128)
        return sinal[: BITS_PREFIXO * self.modem_interno.sps]

    @property
    def taxa_bits(self) -> float:
        """Taxa de bits (um bit por símbolo em todas as modulações)."""
        return self.taxa_sps / self.modem.sps

    def filtro_deteccao(self) -> NDArray[np.float64]:
        """Passa-baixas da detecção na taxa interna, com a meia banda do pulso usado."""
        meia_banda = MEIA_BANDA_DETECCAO_RB[self.modem.pulso]
        if self.modem.modulacao == "fsk" and self.modem.pulso == "retangular":
            meia_banda = MEIA_BANDA_FSK_RETANGULAR_RB
        corte = min(meia_banda * self.taxa_bits, 0.45 * self.taxa_interna)
        coeficientes = COEFICIENTES_POR_BIT * self.modem_interno.sps + 1
        return np.asarray(firwin(coeficientes, corte, fs=self.taxa_interna), dtype=np.float64)

    def modelo_deteccao(self) -> Sinal:
        """Modelo passado pelo mesmo filtro de detecção que o sinal."""
        return np.asarray(
            np.convolve(self.modelo(), self.filtro_deteccao(), mode="same"), dtype=np.complex128
        )

    def hipoteses_hz(self) -> NDArray[np.float64]:
        """Grade de offsets da detecção: passo 1/(2T), erro máximo 1/(4T) (perda de 0,9 dB)."""
        passo = self.taxa_interna / (2 * len(self.modelo()))
        n = int(np.ceil(self.offset_max_hz / passo))
        return np.asarray(np.arange(-n, n + 1) * passo, dtype=np.float64)

    def amostras_por_quadro_max(self) -> int:
        """Duração do maior quadro possível (255 bytes) na taxa interna, com folga para a cauda."""
        bits = quadro.bits_por_quadro(quadro.PAYLOAD_MAX_BYTES)
        return (bits + 2 * self.modem.span) * self.modem_interno.sps


@dataclass(frozen=True)
class Deteccao:
    """Um sincronismo achado na captura e o resultado da leitura do quadro.

    Attributes:
        inicio: amostra da captura (taxa original) em que o quadro começa, com fração.
        metrica: correlação normalizada no pico (0 a 1).
        offset_hz: offset de frequência estimado pelo preâmbulo.
        situacao: "ok", "crc" ou "curto" (sdrlink.quadro.Leitura).
        pacote: o pacote, só quando o CRC confere.
        bits: bits demodulados depois do sync (só com ConfigReceptor.guardar_bits).
    """

    inicio: float
    metrica: float
    offset_hz: float
    situacao: str
    pacote: Pacote | None
    bits: NDArray[np.uint8] | None = None


def _soma_deslizante(valores: NDArray[np.float64], janela: int) -> NDArray[np.float64]:
    """Soma de cada janela de valores consecutivos (saída com len - janela + 1 elementos)."""
    acumulada = np.concatenate([[0.0], np.cumsum(valores)])
    return np.asarray(acumulada[janela:] - acumulada[:-janela], dtype=np.float64)


def metrica_de_correlacao(
    x: Sinal, config: ConfigReceptor
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Correlação normalizada com o modelo, para cada possível início de quadro.

    Para cada hipótese de offset f, com y[k] = x[n+k]·exp(-j2πfk/taxa) e o modelo
    t centrado (t0 = t - média):
        m_f[n] = |sum y·conj(t0)|² / (sum |t0|² · (sum |y|² - |sum y|²/L)),
    entre 0 e 1. Devolve o máximo sobre as hipóteses e o offset da hipótese vencedora.
    Recebe o sinal já na banda base, na taxa interna e filtrado pelo filtro de detecção.
    """
    modelo = config.modelo_deteccao()
    tamanho = len(modelo)
    n_saida = len(x) - tamanho + 1
    if n_saida <= 0:
        return np.zeros(0), np.zeros(0)
    centrado = modelo - np.mean(modelo)
    energia_modelo = float(np.sum(np.abs(centrado) ** 2))
    energia_sinal = _soma_deslizante(np.abs(x) ** 2, tamanho)
    k = np.arange(tamanho)
    melhor = np.zeros(n_saida)
    offset = np.zeros(n_saida)
    for f in config.hipoteses_hz():
        giro = np.exp(2j * np.pi * f * k / config.taxa_interna)
        c = fftconvolve(
            x, np.conj((centrado * giro)[::-1]), mode="valid"
        )  # sum x[n+k] conj(t0 giro)
        media = fftconvolve(x, np.conj(giro[::-1]), mode="valid")  # sum x[n+k] conj(giro)
        denominador = energia_modelo * np.maximum(
            energia_sinal - np.abs(media) ** 2 / tamanho, 1e-30
        )
        m = np.abs(c) ** 2 / denominador
        troca = m > melhor
        melhor[troca] = m[troca]
        offset[troca] = f
    return melhor, offset


def picos(metrica: NDArray[np.float64], limiar: float, distancia: int) -> list[int]:
    """Máximos acima do limiar, a pelo menos `distancia` amostras uns dos outros.

    Os candidatos são aceitos do maior para o menor (supressão de não-máximos).
    """
    candidatos = np.flatnonzero(metrica >= limiar)
    if len(candidatos) == 0:
        return []
    ordem = candidatos[np.argsort(metrica[candidatos])[::-1]]
    ocupado = np.zeros(len(metrica), dtype=bool)
    aceitos: list[int] = []
    for n in ordem[:MAX_DETECCOES_POR_BLOCO]:
        if ocupado[n]:
            continue
        aceitos.append(int(n))
        ocupado[max(0, n - distancia) : n + distancia + 1] = True
    return sorted(aceitos)


def _refinar(metrica: NDArray[np.float64], n: int) -> float:
    """Posição fracionária do pico por interpolação parabólica (entre -0,5 e +0,5 amostra)."""
    if n == 0 or n == len(metrica) - 1:
        return float(n)
    a, b, c = metrica[n - 1], metrica[n], metrica[n + 1]
    curvatura = a - 2 * b + c
    if curvatura >= 0:
        return float(n)
    return float(n + float(np.clip(0.5 * (a - c) / curvatura, -0.5, 0.5)))


def estimar_offset(x: Sinal, inicio: int, grosso_hz: float, config: ConfigReceptor) -> float:
    """Offset (Hz): o grosso da hipótese vencedora mais o resíduo fino.

    O resíduo fino é medido pela rotação de fase entre TRECHOS_ESTIMATIVA trechos
    consecutivos do preâmbulo. O resíduo depois da hipótese é no máximo 1/(4T),
    bem dentro da faixa sem ambiguidade do estimador fino, ±TRECHOS_ESTIMATIVA/(2T).
    """
    modelo = config.modelo_deteccao()
    tamanho = len(modelo) // TRECHOS_ESTIMATIVA
    n = np.arange(len(modelo))
    y = x[inicio : inicio + len(modelo)] * np.exp(-2j * np.pi * grosso_hz * n / config.taxa_interna)
    c = np.array(
        [
            np.vdot(modelo[k : k + tamanho], y[k : k + tamanho])
            for k in range(0, tamanho * TRECHOS_ESTIMATIVA, tamanho)
        ]
    )
    giro = np.sum(c[1:] * np.conj(c[:-1]))
    return grosso_hz + float(np.angle(giro) * config.taxa_interna / (2 * np.pi * tamanho))


def _alinhar(x: Sinal, inicio: float, n: int) -> Sinal:
    """Trecho de n amostras a partir da posição fracionária `inicio` (z[k] = x[inicio + k])."""
    base = int(np.floor(inicio))
    fracao = inicio - base
    if fracao == 0:
        return np.asarray(x[base : base + n], dtype=np.complex128)
    return canal.atrasar(x[base + 1 : base + 1 + n], 1 - fracao)  # avança a fração


def _limiar_do_prefixo(trecho: Sinal, cm: ConfigModem) -> float:
    """Limiar da OOK no meio dos níveis medidos nos "1" e nos "0" conhecidos do prefixo."""
    prefixo = np.concatenate([quadro.PREAMBULO, quadro.SYNC])
    modulo = np.abs(modem.saida_casada(trecho, cm, BITS_PREFIXO))
    return float(np.mean(modulo[prefixo == 1]) + np.mean(modulo[prefixo == 0])) / 2


def demodular_quadro(
    x: Sinal, inicio: float, offset_hz: float, config: ConfigReceptor
) -> NDArray[np.uint8] | None:
    """Corrige instante, offset e fase de um quadro e devolve os bits depois do sync.

    Devolve None se a captura acaba antes do cabeçalho.
    """
    cm = config.modem_interno
    trecho = canal.girar(
        _alinhar(x, inicio, config.amostras_por_quadro_max()), -offset_hz, config.taxa_interna
    )
    n_bits = min(
        quadro.bits_por_quadro(quadro.PAYLOAD_MAX_BYTES),
        (len(trecho) - len(cm.formato())) // cm.sps - 1,
    )
    if n_bits <= BITS_PREFIXO + quadro.BITS_CABECALHO:
        return None
    if cm.modulacao != "ook":
        modelo = config.modelo()
        fase = float(np.angle(np.vdot(modelo, trecho[: len(modelo)])))  # só a BPSK coerente usa
        return modem.demodular(trecho, cm, n_bits, fase=fase)[BITS_PREFIXO:]
    # OOK: a janela de leitura é maior que o quadro, e o que vem depois (silêncio, outro
    # quadro, interferência) puxaria um limiar ajustado na janela toda; o limiar vem dos
    # 29 bits conhecidos do prefixo. Uma 2ª passada com k-médias só nos símbolos do quadro
    # foi medida em 1500 quadros a 11 e 12 dB e não deu ganho significativo: ficou de fora.
    return modem.demodular(trecho, cm, n_bits, limiar=_limiar_do_prefixo(trecho, cm))[BITS_PREFIXO:]


def ler_quadro(
    x: Sinal,
    inicio: float,
    offset_hz: float,
    config: ConfigReceptor,
    interpretador: Interpretador = quadro.interpretar,
) -> quadro.Leitura:
    """Demodula um quadro e interpreta os bits depois do sync.

    O interpretador padrão é o do quadro v2; o ensaio com a captura da referência
    passa o do quadro antigo (comprimento, payload e CRC-8).
    """
    bits = demodular_quadro(x, inicio, offset_hz, config)
    return quadro.Leitura(None, "curto", 0) if bits is None else interpretador(bits)


def receber_bloco(
    x: Sinal,
    config: ConfigReceptor,
    origem: int = 0,
    interpretador: Interpretador = quadro.interpretar,
) -> list[Deteccao]:
    """Acha e lê todos os quadros de um bloco; `origem` é a posição do bloco na captura."""
    n = np.arange(origem, origem + len(x))
    base = np.asarray(x * np.exp(-2j * np.pi * config.deslocamento_hz * n / config.taxa_sps))
    d = config.decimacao
    if d > 1:
        base = np.asarray(
            resample_poly(base, 1, d), dtype=np.complex128
        )  # filtro de canal + decimação
    filtrado = np.asarray(
        fftconvolve(base, config.filtro_deteccao(), mode="same"), dtype=np.complex128
    )
    metrica, grosso = metrica_de_correlacao(filtrado, config)
    deteccoes = []
    for p in picos(metrica, config.limiar, DISTANCIA_MIN_BITS * config.modem_interno.sps):
        offset = estimar_offset(filtrado, p, float(grosso[p]), config)
        inicio = _refinar(metrica, p)
        # a 2-FSK demodula do sinal já filtrado na banda do pulso: o correlator dela não
        # rejeita sinais fortes fora da banda (pico de DC do RTL, outros sinais ISM), e um
        # pico de DC do tamanho do sinal multiplicava a BER por 25 (21/11/2026); OOK e
        # DBPSK passam pelo filtro casado RRC, que já os rejeita
        entrada = filtrado if config.modem.modulacao == "fsk" else base
        bits = demodular_quadro(entrada, inicio, offset, config)
        leitura = quadro.Leitura(None, "curto", 0) if bits is None else interpretador(bits)
        guardados = bits if config.guardar_bits else None
        deteccoes.append(
            Deteccao(
                origem + inicio * d,
                float(metrica[p]),
                offset,
                leitura.situacao,
                leitura.pacote,
                guardados,
            )
        )
    return deteccoes


def receber(
    x: Sinal,
    config: ConfigReceptor,
    tamanho_bloco: int = BLOCO_PADRAO,
    interpretador: Interpretador = quadro.interpretar,
) -> list[Deteccao]:
    """Processa a captura inteira em blocos com sobreposição de um quadro máximo.

    Cada bloco só fica com os quadros que começam antes do início do próximo
    bloco; os que começam depois são lidos inteiros no bloco seguinte.

    Raises:
        ValueError: bloco menor que duas vezes o quadro máximo.
    """
    sobra = (config.amostras_por_quadro_max() + len(config.modelo())) * config.decimacao
    if tamanho_bloco < 2 * sobra:
        raise ValueError(
            f"bloco de {tamanho_bloco} amostras menor que 2 quadros máximos ({2 * sobra})"
        )
    passo = tamanho_bloco - sobra
    deteccoes: list[Deteccao] = []
    for k in range(MAX_BLOCOS):
        origem = k * passo
        if origem >= len(x):
            break
        ultimo = origem + tamanho_bloco >= len(x)
        bloco = np.asarray(x[origem : origem + tamanho_bloco], dtype=np.complex128)
        lidas = receber_bloco(bloco, config, origem, interpretador)
        deteccoes.extend(d for d in lidas if ultimo or d.inicio < origem + passo)
    return _sem_repeticao(deteccoes, DISTANCIA_MIN_BITS * config.modem.sps)


def _sem_repeticao(deteccoes: list[Deteccao], distancia: float) -> list[Deteccao]:
    """Junta detecções do mesmo quadro achado em dois blocos.

    Um quadro perto da emenda pode ser achado nos dois blocos, com inícios dos
    dois lados da fronteira; fica só a de maior métrica entre as que estão a
    menos de `distancia` amostras.
    """
    resultado: list[Deteccao] = []
    for d in sorted(deteccoes, key=lambda d: d.inicio):
        if resultado and d.inicio - resultado[-1].inicio < distancia:
            if d.metrica > resultado[-1].metrica:
                resultado[-1] = d
            continue
        resultado.append(d)
    return resultado


def pacotes_aceitos(deteccoes: list[Deteccao]) -> list[Pacote]:
    """Pacotes com CRC válido, na ordem de chegada, sem duplicatas (mesma sequência e payload)."""
    vistos: set[tuple[int, bytes]] = set()
    aceitos = []
    for d in deteccoes:
        if d.pacote is None or (d.pacote.sequencia, d.pacote.payload) in vistos:
            continue
        vistos.add((d.pacote.sequencia, d.pacote.payload))
        aceitos.append(d.pacote)
    return aceitos


def gravar_saida(pacotes: list[Pacote], caminho: Path) -> Path:
    """Grava o arquivo de saída da prova: uma linha "sequência<TAB>payload em hex" por pacote.

    Raises:
        ValueError: caminho sem a extensão .txt.
    """
    if caminho.suffix != ".txt":
        raise ValueError(f"o arquivo de saída deve ser .txt: {caminho}")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linhas = [f"{p.sequencia}\t{p.payload.hex()}" for p in pacotes]
    caminho.write_text("\n".join(linhas) + ("\n" if linhas else ""), encoding="utf-8", newline="\n")
    return caminho


def resumo(deteccoes: list[Deteccao], duracao_s: float) -> dict[str, object]:
    """Números da recepção para o registro do ensaio (seção 7 do enunciado).

    Contagens por situação, pacotes aceitos e repetidos, offset residual estimado
    (mediana e faixa de 5% a 95%) e a menor métrica de correlação entre os aceitos.
    """
    aceitos = pacotes_aceitos(deteccoes)
    validas = [d for d in deteccoes if d.situacao == "ok"]
    offsets = [d.offset_hz for d in validas]
    return {
        "duracao_s": round(duracao_s, 3),
        "deteccoes": len(deteccoes),
        "crc_ok": len(validas),
        "crc_falho": sum(d.situacao == "crc" for d in deteccoes),
        "cortados": sum(d.situacao == "curto" for d in deteccoes),
        "pacotes_aceitos": len(aceitos),
        "repeticoes_descartadas": len(validas) - len(aceitos),
        "offset_residual_mediano_hz": round(float(np.median(offsets)), 1) if offsets else None,
        "offset_residual_p5_p95_hz": (
            [round(float(v), 1) for v in np.percentile(offsets, [5, 95])] if offsets else None
        ),
        "metrica_minima_aceitos": round(min(d.metrica for d in validas), 3) if validas else None,
    }
