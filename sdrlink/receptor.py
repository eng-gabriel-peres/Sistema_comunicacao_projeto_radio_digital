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
import functools
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from scipy import fft as sfft
from scipy.signal import fftconvolve, firwin, resample_poly

from sdrlink import modem, quadro
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
PISO_RELATIVO = 1e-9  # energia centrada mínima da janela, em relação à média do bloco
MEIO_FIR = 16  # interpolador do instante fracionário: 33 coeficientes
BETA_KAISER = 8.0
_JANELA_FIR = np.kaiser(2 * MEIO_FIR + 1, BETA_KAISER)  # calculada uma vez
PAYLOAD_MINIMO_LIDO = (
    128  # bytes: lê ao menos o quadro da prova, mesmo com o comprimento corrompido
)
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
        Calculado uma vez por configuração.
        """
        return _em_cache(self, "modelo")

    def _calcular_modelo(self) -> Sinal:
        """Corpo de modelo(), sem cache."""
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
        return np.asarray(_em_cache(self, "filtro").real, dtype=np.float64)

    def _calcular_filtro(self) -> NDArray[np.float64]:
        """Corpo de filtro_deteccao(), sem cache."""
        meia_banda = MEIA_BANDA_DETECCAO_RB[self.modem.pulso]
        if self.modem.modulacao == "fsk" and self.modem.pulso == "retangular":
            meia_banda = MEIA_BANDA_FSK_RETANGULAR_RB
        corte = min(meia_banda * self.taxa_bits, 0.45 * self.taxa_interna)
        coeficientes = COEFICIENTES_POR_BIT * self.modem_interno.sps + 1
        return np.asarray(firwin(coeficientes, corte, fs=self.taxa_interna), dtype=np.float64)

    def modelo_deteccao(self) -> Sinal:
        """Modelo passado pelo mesmo filtro de detecção que o sinal."""
        return _em_cache(self, "modelo_deteccao")

    def _calcular_modelo_deteccao(self) -> Sinal:
        """Corpo de modelo_deteccao(), sem cache."""
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


@functools.cache
def _em_cache(config: ConfigReceptor, nome: str) -> NDArray[np.complex128]:
    """Modelo, filtro e modelo filtrado: iguais na captura inteira, calculados uma vez."""
    calcular = {
        "modelo": config._calcular_modelo,
        "filtro": config._calcular_filtro,
        "modelo_deteccao": config._calcular_modelo_deteccao,
    }[nome]
    valor = np.asarray(calcular(), dtype=np.complex128)
    valor.setflags(write=False)
    return valor


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


def _modulo2(z: NDArray[np.complexfloating]) -> NDArray[np.float64]:
    """|z|² sem a raiz quadrada de np.abs."""
    return np.asarray(z.real**2 + z.imag**2, dtype=np.float64)


def _fasor(ciclos_por_amostra: float, n: int) -> NDArray[np.complex128]:
    """exp(j2π·c·k), k = 0..n-1, sem exp nos n pontos: e^(jθ(aM + b)) = e^(jθaM)·e^(jθb).

    O produto externo de dois vetores de uns sqrt(n) elementos dá o fasor inteiro com
    uma multiplicação por ponto (o exp de 4 M pontos custava mais que uma FFT).
    """
    passo = int(np.ceil(np.sqrt(n)))
    fino = np.exp(2j * np.pi * ciclos_por_amostra * np.arange(passo))
    grosso = np.exp(2j * np.pi * ciclos_por_amostra * passo * np.arange(-(-n // passo)))
    return np.asarray(np.outer(grosso, fino).ravel()[:n], dtype=np.complex128)


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
    energia_sinal = _soma_deslizante(_modulo2(x), tamanho)
    # Uma FFT do bloco e uma do modelo servem para todas as hipóteses. Cada hipótese é
    # arredondada para uma raia da FFT (nfft >= 4 M pontos dá raias de 0,5 Hz; o offset fino
    # corrige depois), e aí deslocar o sinal em frequência é só rotacionar o espectro:
    # FFT(x·e^(-j2πsm/nfft)) = roll(X, -s). Com y = x·e^(-jwm), |sum_k x[n+k] conj(t0[k] e^(jwk))|
    # = |sum_k y[n+k] conj(t0[k])| = |ifft(Y·conj(T0))[n]|, sem dar a volta (nfft >= len(x)).
    nfft = sfft.next_fast_len(len(x))
    # precisão simples nas FFTs grandes (25% mais rápidas): a métrica só é comparada com o
    # limiar de 0,5, e o erro relativo de 1e-6 não muda nenhuma detecção; as somas
    # deslizantes, sensíveis ao cancelamento, continuam em precisão dupla
    espectro = sfft.fft(x.astype(np.complex64), nfft)
    espectro_modelo = np.conj(sfft.fft(centrado.astype(np.complex64), nfft))
    piso = PISO_RELATIVO * float(np.mean(energia_sinal)) + np.finfo(float).tiny
    melhor = np.zeros(n_saida)
    offset = np.zeros(n_saida)
    for f in config.hipoteses_hz():
        raia = round(f * nfft / config.taxa_interna)
        f_raia = raia * config.taxa_interna / nfft
        c = sfft.ifft(np.roll(espectro, -raia) * espectro_modelo)[:n_saida]
        # |sum_k y[n+k]| na janela: soma deslizante, sem FFT
        y = x if raia == 0 else x * _fasor(-raia / nfft, len(x))
        acumulada = np.concatenate([[0], np.cumsum(y)])
        media2 = _modulo2(acumulada[tamanho:] - acumulada[:-tamanho])
        centrada = energia_sinal - media2 / tamanho
        # janela sem energia própria (zeros exatos, sem ruído): métrica 0 em vez de 0/0
        m = np.where(
            centrada > piso, _modulo2(c) / (energia_modelo * np.maximum(centrada, piso)), 0.0
        )
        troca = m > melhor
        melhor[troca] = m[troca]
        offset[troca] = f_raia
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
    """Trecho de n amostras a partir da posição fracionária `inicio` (z[k] = x[inicio + k]).

    Interpolação por sinc com janela de Kaiser (2·MEIO_FIR + 1 coeficientes): o sinal
    na taxa interna ocupa no máximo uns 30% da banda, e o erro fica abaixo de 1e-4. Antes
    era um atraso por FFT da janela inteira, que dominava o tempo de cada quadro.
    """
    base = int(np.floor(inicio))
    fracao = inicio - base
    if fracao == 0:
        return np.asarray(x[base : base + n], dtype=np.complex128)
    ini = base - MEIO_FIR
    trecho = np.asarray(x[max(ini, 0) : base + n + MEIO_FIR], dtype=np.complex128)
    if ini < 0:
        trecho = np.concatenate([np.zeros(-ini, dtype=np.complex128), trecho])
    j = np.arange(-MEIO_FIR, MEIO_FIR + 1)
    pesos = np.sinc(fracao - j) * _JANELA_FIR
    pesos /= np.sum(pesos)  # ganho 1 em DC
    # z[k] = sum_j x[base + k + j] · sinc(fracao - j)
    return np.asarray(np.correlate(trecho, pesos, mode="valid")[:n], dtype=np.complex128)


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
    cauda = len(cm.formato())
    disponivel = min(
        config.amostras_por_quadro_max(), len(x) - int(np.floor(inicio)) - MEIO_FIR - 1
    )
    n_max = min(
        quadro.bits_por_quadro(quadro.PAYLOAD_MAX_BYTES), (disponivel - cauda) // cm.sps - 2
    )
    n_cabecalho = BITS_PREFIXO + quadro.BITS_CABECALHO
    if n_max <= n_cabecalho:
        return None

    def preparar(n_bits: int) -> Sinal:
        """Alinha e tira o offset só das amostras que a leitura de n_bits usa."""
        z = _alinhar(x, inicio, (n_bits + 2) * cm.sps + cauda)
        return np.asarray(z * _fasor(-offset_hz / config.taxa_interna, len(z)))

    # primeiro só o cabeçalho, para saber o tamanho; depois exatamente o quadro (antes a
    # janela era sempre a do maior quadro possível, 2093 bits, quase o dobro do da prova)
    cabecalho = preparar(n_cabecalho)
    modelo = config.modelo()
    fase = float(np.angle(np.vdot(modelo, cabecalho[: len(modelo)])))  # só a BPSK coerente usa
    # OOK: limiar dos 29 bits conhecidos do prefixo (o que vem depois do quadro, silêncio ou
    # outro quadro, não pode puxar o limiar; a 2ª passada com k-médias não deu ganho medido)
    limiar = _limiar_do_prefixo(cabecalho, cm) if cm.modulacao == "ook" else None
    bits = modem.demodular(cabecalho, cm, n_cabecalho, fase=fase, limiar=limiar)
    campo = bits[BITS_PREFIXO : BITS_PREFIXO + quadro.BITS_COMPRIMENTO]
    n_bytes = max(int(quadro.bits_para_bytes(campo)[0]), PAYLOAD_MINIMO_LIDO)
    n_bits = min(n_max, BITS_PREFIXO + quadro.bits_apos_sync(n_bytes))
    bits = modem.demodular(preparar(n_bits), cm, n_bits, fase=fase, limiar=limiar)
    return bits[BITS_PREFIXO:]


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
    giro = -config.deslocamento_hz / config.taxa_sps  # ciclos por amostra
    base = np.asarray(x * _fasor(giro, len(x)) * np.exp(2j * np.pi * giro * origem))
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
