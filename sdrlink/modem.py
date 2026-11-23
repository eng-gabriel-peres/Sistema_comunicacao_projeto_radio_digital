"""Moduladores e demoduladores em banda base: OOK, BPSK, DBPSK, DQPSK, 8-PSK e 2-FSK.

Requisitos: MOD-01 a MOD-03 (OOK, 2-FSK e BPSK implementados pela equipe),
PUL-01 (pulso retangular e alternativas).

Um bit por símbolo em todas as modulações, menos no corpo da DQPSK (dois) e da 8-PSK (três). O sinal
é complexo, em banda base, com sps amostras por símbolo; o deslocamento para a
frequência de transmissão fica a cargo do TX. Os demoduladores deste módulo supõem o instante de
amostragem conhecido (sincronismo ideal): estimar tempo, fase e offset a partir
do preâmbulo é tarefa do receptor (sub-bloco 3c).

    OOK   amplitudes 0/1, detecção não coerente (módulo) com limiar entre os dois níveis
    BPSK  amplitudes -1/+1, detecção coerente (precisa da fase da portadora)
    DBPSK bit 1 = inversão de fase; detecção diferencial, não precisa da fase
    DQPSK 2 bits por símbolo (bloco 10): cada par de bits gira a fase de 0, 90, 180 ou
          270 graus (Gray); detecção diferencial. Os primeiros `prefixo` bits de
          modular/demodular vão um por símbolo, como na DBPSK: assim o preâmbulo e o
          sync de um quadro DQPSK são idênticos aos da DBPSK e o RX acha o quadro do
          mesmo jeito
    8-PSK 3 bits por símbolo (bloco 24), Gray, fase absoluta e detecção coerente: o
          prefixo vai como na DBPSK e dá a fase de referência; a fase e o offset do
          corpo saem da potência 8 dos símbolos
    2-FSK fase contínua, tons em +-h*Rb/2; detecção não coerente por correlação
          com os dois tons (ortogonais com h = 1)
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from sdrlink import pulsos

Bits = NDArray[np.uint8]
Sinal = NDArray[np.complex128]

MODULACOES = ("ook", "bpsk", "dbpsk", "dqpsk", "8psk", "fsk")
# DQPSK, Gray: o par (b1, b2) gira a fase de GIROS_DQPSK[2 b1 + b2]
GIROS_DQPSK = np.exp(1j * np.pi / 2 * np.array([0, 1, 3, 2]))  # 00: 0, 01: 90, 10: 270, 11: 180
PULSOS_LINEARES = ("retangular", "rrc")  # OOK, BPSK, DBPSK, DQPSK: pulso de símbolo
BITS_POR_SIMBOLO = {"dqpsk": 2, "8psk": 3}  # as outras levam 1 bit por símbolo
# índice de fase (k·45°) de cada valor de 3 bits b0b1b2: o inverso do Gray k ^ (k >> 1), para que
# fases vizinhas difiram em 1 bit (a primeira versão usava o próprio Gray aqui e não era Gray)
GRAY_8PSK = np.array([0, 1, 3, 2, 7, 6, 4, 5])
BITS_DO_INDICE_8PSK = np.argsort(GRAY_8PSK)  # os 3 bits (b0b1b2) de cada índice de fase
N_FFT_8PSK = 8192  # busca da frequência pela potência 8 (mínimo; maior se o corpo for maior)
GIRO_MAX_8PSK = 0.02  # rad/símbolo de offset residual depois do preâmbulo (2,2 kHz a 682,7 ksímb/s)
PREFIXO_MIN_8PSK = 8  # símbolos conhecidos para a fase de referência
GANHO_RASTREIO_8PSK = (
    0.1  # malha de fase guiada pelas decisões: fração do erro corrigida por símbolo
)
PULSOS_FSK = ("retangular", "gaussiano")  # 2-FSK: pulso de frequência
ITERACOES_LIMIAR = 20
H_MAX = 2.0  # índice de modulação máximo aceito


@dataclass(frozen=True)
class ConfigModem:
    """Escolha da modulação e do pulso.

    Attributes:
        modulacao: "ook", "bpsk", "dbpsk", "dqpsk" ou "fsk".
        pulso: "retangular" ou "rrc" (lineares); "retangular" ou "gaussiano" (fsk).
        sps: amostras por símbolo.
        beta: fator de rolagem do RRC.
        bt: produto banda-tempo do pulso gaussiano.
        h: índice de modulação da 2-FSK (desvio de pico = h * Rb / 2).
        span: duração dos pulsos RRC e gaussiano, em símbolos.
    """

    modulacao: str
    pulso: str
    sps: int
    beta: float = 0.35
    bt: float = 0.5
    h: float = 1.0
    span: int = 12  # RRC truncado em 8 símbolos deixa 3,4% de ISI no pico; em 12, 0,4%

    def __post_init__(self) -> None:
        """Rejeita combinações inválidas.

        Raises:
            ValueError: modulação, pulso ou índice de modulação inválidos.
        """
        if self.modulacao not in MODULACOES:
            raise ValueError(f"modulação desconhecida: {self.modulacao}")
        validos = PULSOS_FSK if self.modulacao == "fsk" else PULSOS_LINEARES
        if self.pulso not in validos:
            raise ValueError(f"pulso {self.pulso} não serve para {self.modulacao}: use {validos}")
        if not 0 < self.h <= H_MAX:
            raise ValueError(f"índice de modulação fora de (0, 2]: {self.h}")
        self.formato()  # valida sps, beta, bt e span

    def formato(self) -> NDArray[np.float64]:
        """Pulso de símbolo (lineares) ou de frequência (fsk), calculado uma vez."""
        return _formato(self)

    @property
    def linear(self) -> bool:
        """Modulação linear (soma de pulsos): OOK, BPSK, DBPSK e DQPSK; a 2-FSK não é."""
        return self.modulacao != "fsk"

    @property
    def bits_por_simbolo(self) -> int:
        """Bits levados por símbolo no corpo: 2 na DQPSK, 1 nas outras."""
        return bits_por_simbolo_de(self.modulacao)


def bits_por_simbolo_de(modulacao: str) -> int:
    """Bits por símbolo no corpo do quadro: 2 na DQPSK, 1 nas outras."""
    return BITS_POR_SIMBOLO.get(modulacao, 1)


def simbolos(n_bits: int, config: ConfigModem, prefixo: int = 0) -> int:
    """Quantos símbolos levam n_bits, com os primeiros `prefixo` bits a um por símbolo.

    Na DQPSK um corpo com número ímpar de bits ganha um bit 0 no fim.
    """
    corpo = max(n_bits - prefixo, 0)
    return min(n_bits, prefixo) + -(-corpo // config.bits_por_simbolo)


def bits_em(n_simbolos: int, config: ConfigModem, prefixo: int = 0) -> int:
    """Quantos bits cabem em n_simbolos (o inverso de simbolos)."""
    corpo = max(n_simbolos - prefixo, 0)
    return min(n_simbolos, prefixo) + corpo * config.bits_por_simbolo


@functools.cache
def _formato(config: ConfigModem) -> NDArray[np.float64]:
    """Pulso da configuração, só leitura (o mesmo vetor é devolvido a todos os chamadores)."""
    if config.pulso == "rrc":
        forma = pulsos.rrc(config.beta, config.sps, config.span)
    elif config.pulso == "gaussiano":
        forma = pulsos.gaussiano(config.bt, config.sps, config.span)
    elif config.modulacao == "fsk":
        forma = np.ones(config.sps)  # pulso de frequência retangular: CPFSK
    else:
        forma = pulsos.retangular(config.sps)
    forma.setflags(write=False)
    return forma


def _impulsos(simbolos: NDArray[np.generic], sps: int) -> NDArray[np.complex128]:
    """Um impulso por símbolo, a cada sps amostras."""
    trem = np.zeros(len(simbolos) * sps, dtype=np.complex128)
    trem[::sps] = simbolos
    return trem


def _simbolos_8psk(bits: Bits, prefixo: int) -> NDArray[np.complex128]:
    """Prefixo como na DBPSK (com o símbolo de referência), corpo em 8-PSK absoluta com Gray."""
    trios = bits[prefixo:].astype(np.intp)
    trios = np.concatenate([trios, np.zeros((-len(trios)) % 3, dtype=np.intp)])
    indice = GRAY_8PSK[4 * trios[0::3] + 2 * trios[1::3] + trios[2::3]]
    referencia = np.cumprod(np.concatenate([[1.0], 1 - 2 * bits[:prefixo].astype(np.float64)]))
    return np.concatenate([referencia, np.exp(1j * np.pi / 4 * indice)]).astype(np.complex128)


def _simbolos_lineares(bits: Bits, modulacao: str, prefixo: int = 0) -> NDArray[np.complex128]:
    """Símbolos de OOK, BPSK, DBPSK e DQPSK (as diferenciais ganham um símbolo de referência)."""
    b = bits.astype(np.float64)
    if modulacao == "ook":
        return b.astype(np.complex128)
    if modulacao == "bpsk":
        return (2 * b - 1).astype(np.complex128)
    if modulacao == "dbpsk":
        return np.cumprod(np.concatenate([[1.0], 1 - 2 * b])).astype(np.complex128)
    # dqpsk: os `prefixo` primeiros bits como na DBPSK, depois um giro de fase por par de bits
    corpo = bits[prefixo:].astype(np.intp)
    corpo = np.concatenate([corpo, np.zeros(len(corpo) % 2, dtype=np.intp)])
    giros = GIROS_DQPSK[2 * corpo[0::2] + corpo[1::2]]
    passos = np.concatenate([[1.0 + 0j], 1 - 2 * b[:prefixo] + 0j, giros])
    return np.asarray(np.cumprod(passos), dtype=np.complex128)


def modular(bits: Bits, config: ConfigModem, prefixo: int = 0) -> Sinal:
    """Sinal complexo em banda base para a sequência de bits.

    `prefixo`: só a DQPSK usa; os primeiros `prefixo` bits vão um por símbolo, como na
    DBPSK (o preâmbulo e o sync do quadro).

    Raises:
        ValueError: bits vazios ou com valores diferentes de 0 e 1.
    """
    if len(bits) == 0 or np.any(bits > 1):
        raise ValueError("os bits devem ser uma sequência não vazia de 0 e 1")
    forma = config.formato()
    if config.modulacao == "fsk":
        frequencia = np.convolve(_impulsos(2 * bits.astype(np.float64) - 1, config.sps).real, forma)
        # fase(n) = integral da frequência até n, exclusive (pi*h por símbolo); com a soma
        # inclusiva a fase ficava adiantada 1 amostra, e o alinhamento dependia da taxa
        fase = np.concatenate([[0.0], np.cumsum(frequencia)[:-1]]) * np.pi * config.h / config.sps
        return np.exp(1j * fase)
    if config.modulacao == "8psk":
        valores = _simbolos_8psk(bits, prefixo)
    else:
        valores = _simbolos_lineares(bits, config.modulacao, prefixo)
    return np.convolve(_impulsos(valores, config.sps), forma).astype(np.complex128)


def _limiar_dois_niveis(valores: NDArray[np.float64]) -> float:
    """Limiar entre os dois grupos de valores (k-médias com k = 2, número fixo de iterações)."""
    limiar = (float(np.min(valores)) + float(np.max(valores))) / 2
    for _ in range(ITERACOES_LIMIAR):
        altos, baixos = valores[valores > limiar], valores[valores <= limiar]
        if len(altos) == 0 or len(baixos) == 0:
            break
        limiar = float(altos.mean() + baixos.mean()) / 2
    return limiar


def saida_casada(amostras: Sinal, config: ConfigModem, n_simbolos: int) -> Sinal:
    """Saída do filtro casado no instante ótimo de cada símbolo (OOK, BPSK, DBPSK, DQPSK).

    Raises:
        ValueError: sinal curto demais para n_simbolos.
    """
    forma = config.formato()
    casado = np.convolve(amostras, forma[::-1])
    instantes = np.arange(n_simbolos) * config.sps + len(forma) - 1
    if instantes[-1] >= len(casado):
        raise ValueError("sinal curto demais para a quantidade de bits pedida")
    return casado[instantes]


def _suave_fsk(amostras: Sinal, config: ConfigModem, n_bits: int) -> NDArray[np.float64]:
    """Correlação não coerente com os dois tons, numa janela de um símbolo por bit.

    Devolve |tom alto| - |tom baixo| de cada bit (positivo = 1).

    Raises:
        ValueError: sinal curto demais para n_bits.
    """
    sps = config.sps
    centro = (len(config.formato()) - 1) / 2 - (sps - 1) / 2  # atraso do pulso de frequência
    # +1: a fase em n integra a frequência só até n - 1 (soma exclusiva, em modular), então
    # cada símbolo aparece na fase uma amostra depois. Sem isso a janela da GFSK ficava
    # 1,5 amostra adiantada e a BER subia 2,6 vezes em 11 dB (medido em 21/11/2026).
    inicios = np.arange(n_bits) * sps + round(centro + 1)
    if inicios[-1] + sps > len(amostras):
        raise ValueError("sinal curto demais para a quantidade de bits pedida")
    janelas = amostras[inicios[:, None] + np.arange(sps)]
    giro = np.exp(-1j * np.pi * config.h * np.arange(sps) / sps)  # tom de +h*Rb/2
    alto = np.abs(janelas @ giro)
    baixo = np.abs(janelas @ np.conj(giro))
    return np.asarray(alto - baixo, dtype=np.float64)


def _suave_diferencial(
    amostras: Sinal, config: ConfigModem, n_bits: int, prefixo: int
) -> NDArray[np.float64]:
    """Detecção diferencial: um valor por bit nos `prefixo` primeiros, dois por símbolo depois.

    w = z_k conj(z_k-1) traz o giro de fase entre símbolos. Nos bits um por símbolo, giro
    de 180 graus é 1: -Re(w). No corpo da DQPSK, w e^(j pi/4) cai em 45, 135, 225 ou
    315 graus para 00, 01, 11 e 10: o 1º bit é 1 com Im < 0 e o 2º com Re < 0.
    """
    z = saida_casada(amostras, config, simbolos(n_bits, config, prefixo) + 1)
    w = z[1:] * np.conj(z[:-1])
    corpo = w[prefixo:] * np.exp(1j * np.pi / 4)
    pares = np.column_stack([-np.imag(corpo), -np.real(corpo)]).ravel()
    return np.asarray(np.concatenate([-np.real(w[:prefixo]), pares])[:n_bits], dtype=np.float64)


def _frequencia_8psk(v: Sinal) -> float:
    """Giro por símbolo (rad) da potência 8: pico de |Σ v_k e^(−jωk)| dentro de ±8·GIRO_MAX_8PSK."""
    n_fft = max(N_FFT_8PSK, 1 << int(np.ceil(np.log2(max(len(v), 1)))))  # nunca trunca o corpo
    espectro = np.abs(np.fft.fft(v, n_fft))
    limite = int(np.ceil(8 * GIRO_MAX_8PSK / (2 * np.pi) * n_fft))
    candidatos = np.concatenate([np.arange(limite + 1), np.arange(n_fft - limite, n_fft)])
    pico = int(candidatos[np.argmax(espectro[candidatos])])
    a, b, c = (espectro[(pico + d) % n_fft] for d in (-1, 0, 1))
    denominador = a - 2 * b + c
    delta = 0.5 * (a - c) / denominador if denominador != 0 else 0.0
    ciclos = (pico + delta) / n_fft
    return float(2 * np.pi * (ciclos - np.round(ciclos)) / 8)


def _corrigir_8psk(corpo: Sinal, fase_prefixo: float, distancia: float) -> Sinal:
    """Tira fase e offset do corpo de uma 8-PSK.

    A frequência sai da potência 8 do corpo. A fase parte da do prefixo, levada até o
    corpo por essa frequência, e é rastreada símbolo a símbolo (_rastrear_8psk). A primeira
    versão tirava a fase da média da potência 8 do corpo inteiro: com ruído de fase, a fase
    média se afasta da do prefixo e a ambiguidade de 45° saía errada no quadro todo; e uma
    reta só por quadro não acompanhava a fase (Wiener de 30 Hz: PER de 17%, bloco 24).
    """
    k = np.arange(len(corpo))
    omega = _frequencia_8psk(np.abs(corpo) * np.exp(8j * np.angle(corpo)))
    inicio = fase_prefixo + omega * distancia
    return _rastrear_8psk(corpo * np.exp(-1j * (inicio + omega * k)))


def _rastrear_8psk(corpo: Sinal) -> Sinal:
    """Malha de fase guiada pelas decisões, símbolo a símbolo, a partir da fase do prefixo.

    Cada símbolo é girado pela fase estimada até o anterior, decidido, e o erro de fase
    da decisão corrige a estimativa em GANHO_RASTREIO_8PSK. Uma média móvel das decisões
    do quadro inteiro (testada antes) não resolvia: com a fase longe da reta inicial, as
    primeiras decisões no meio do quadro já saíam erradas e a média só as confirmava.
    """
    # a decisão só depende do ângulo: o laço anda sobre os ângulos, em aritmética escalar
    # (com operações do numpy por símbolo eram 2,4 ms por quadro; 121 s numa prova de 60 s)
    passo = np.pi / 4
    fases = []
    fase = 0.0
    for angulo in np.angle(corpo).tolist():  # no máximo len(corpo) símbolos
        fases.append(fase)
        desvio = angulo - fase
        fase += GANHO_RASTREIO_8PSK * (desvio - round(desvio / passo) * passo)
    return np.asarray(corpo * np.exp(-1j * np.asarray(fases)), dtype=np.complex128)


def _suave_8psk(
    amostras: Sinal, config: ConfigModem, n_bits: int, prefixo: int
) -> NDArray[np.float64]:
    """8-PSK coerente: o prefixo (DBPSK) dá a fase de referência; o corpo sai em max-log.

    Os `prefixo` primeiros bits saem como na DBPSK (−Re(z_k conj(z_k-1))). As decisões
    deles reconstroem os símbolos do prefixo e dão a fase de referência, que resolve a
    ambiguidade de 45° da potência 8. Cada bit do corpo vale max Re(z P*) entre os pontos
    com o bit em 1 menos o máximo entre os pontos com o bit em 0.

    Raises:
        ValueError: prefixo curto demais para a fase de referência.
    """
    if prefixo < PREFIXO_MIN_8PSK:
        raise ValueError(f"a 8-PSK precisa de pelo menos {PREFIXO_MIN_8PSK} bits de prefixo")
    z = saida_casada(amostras, config, simbolos(n_bits, config, prefixo) + 1)
    w = z[1 : prefixo + 1] * np.conj(z[:prefixo])
    referencia = np.cumprod(np.concatenate([[1.0], np.where(np.real(w) < 0, -1.0, 1.0)]))
    fase_prefixo = float(np.angle(np.sum(z[: prefixo + 1] * referencia)))
    corpo = _corrigir_8psk(z[prefixo + 1 :], fase_prefixo, prefixo + 1 - prefixo / 2)
    pontos = np.exp(1j * np.pi / 4 * np.arange(8))
    correlacao = np.real(corpo[:, None] * np.conj(pontos)[None, :])
    suaves = []
    for posicao in (2, 1, 0):  # b0 é o bit mais significativo do índice
        um = (BITS_DO_INDICE_8PSK >> posicao) & 1 == 1
        suaves.append(correlacao[:, um].max(axis=1) - correlacao[:, ~um].max(axis=1))
    corpo_suave = np.column_stack(suaves).ravel()
    return np.asarray(np.concatenate([-np.real(w), corpo_suave])[:n_bits], dtype=np.float64)


def demodular_suave(
    amostras: Sinal,
    config: ConfigModem,
    n_bits: int,
    fase: float = 0.0,
    limiar: float | None = None,
    prefixo: int = 0,
) -> NDArray[np.float64]:
    """Um valor por bit, positivo quando o bit provável é 1, com módulo maior quanto mais certo.

    É a entrada do decodificador de Viterbi com decisão suave (sdrlink.codigo):
        OOK    |z| - limiar
        BPSK   Re(z e^-jfase)
        DBPSK  -Re(z_k conj(z_k-1))   (fase invertida = 1)
        DQPSK  com w = z_k conj(z_k-1) e^(j pi/4): -Im(w) para o 1º bit, -Re(w) para o 2º
        8-PSK  coerente, max-log por bit (fase e offset estimados no próprio quadro)
        2-FSK  |tom alto| - |tom baixo|
    onde z é a saída do filtro casado no instante de cada símbolo. A decisão dura
    (demodular) é o sinal desses valores.

    Args:
        amostras: sinal recebido, alinhado com o início da modulação.
        config: a mesma configuração do modulador.
        n_bits: quantidade de bits a recuperar.
        fase: fase da portadora em radianos (só a BPSK coerente usa).
        limiar: limiar da OOK; se omitido, é ajustado pelos próprios símbolos (k-médias).
        prefixo: DQPSK e 8-PSK; os primeiros `prefixo` bits vêm um por símbolo (na
            8-PSK eles dão a fase de referência e são obrigatórios).

    Raises:
        ValueError: n_bits não positivo, sinal curto demais ou 8-PSK sem prefixo.
    """
    if n_bits <= 0:
        raise ValueError(f"quantidade de bits inválida: {n_bits}")
    if config.modulacao == "fsk":
        return _suave_fsk(amostras, config, n_bits)
    if config.modulacao == "8psk":
        return _suave_8psk(amostras, config, n_bits, prefixo)
    if config.modulacao in ("dbpsk", "dqpsk"):
        # a DBPSK é a DQPSK em que todos os bits vão um por símbolo
        um_por_simbolo = n_bits if config.modulacao == "dbpsk" else prefixo
        return _suave_diferencial(amostras, config, n_bits, um_por_simbolo)
    return _suave_bpsk_ook(saida_casada(amostras, config, n_bits), config, fase, limiar)


def _suave_bpsk_ook(
    z: Sinal, config: ConfigModem, fase: float, limiar: float | None
) -> NDArray[np.float64]:
    """BPSK coerente, Re(z e^-jfase), ou OOK, |z| - limiar (k-médias se não for dado)."""
    if config.modulacao == "bpsk":
        return np.asarray(np.real(z * np.exp(-1j * fase)), dtype=np.float64)
    modulo = np.abs(z)
    corte = _limiar_dois_niveis(modulo) if limiar is None else limiar
    return np.asarray(modulo - corte, dtype=np.float64)


def demodular(
    amostras: Sinal,
    config: ConfigModem,
    n_bits: int,
    fase: float = 0.0,
    limiar: float | None = None,
    prefixo: int = 0,
) -> Bits:
    """Bits a partir do sinal recebido, com o instante de amostragem conhecido.

    Decisão dura: o sinal de demodular_suave (os argumentos são os mesmos).

    Args:
        amostras: sinal recebido, alinhado com o início da modulação.
        config: a mesma configuração do modulador.
        n_bits: quantidade de bits a recuperar.
        fase: fase da portadora em radianos (só a BPSK coerente usa).
        limiar: limiar da OOK; se omitido, é ajustado pelos próprios símbolos (k-médias).
        prefixo: DQPSK e 8-PSK; os primeiros `prefixo` bits vêm um por símbolo (na
            8-PSK eles dão a fase de referência e são obrigatórios).

    Raises:
        ValueError: n_bits não positivo, sinal curto demais ou 8-PSK sem prefixo.
    """
    suaves = demodular_suave(amostras, config, n_bits, fase=fase, limiar=limiar, prefixo=prefixo)
    return np.asarray(suaves > 0, dtype=np.uint8)
