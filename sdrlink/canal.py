"""Canal simulado: AWGN, erro de fase, offset de frequência, atraso e diferença de relógio.

Requisito: Etapa 4 (BER × Eb/N0 simulada contra a teoria e efeito de erro de
fase, offset de frequência e erro de temporização); usado já na Etapa 3 para
validar a cadeia completa com ruído.

Definição: Eb é a energia média por bit do sinal transmitido, medida no próprio
sinal (potência média × amostras por bit). O ruído complexo tem variância N0 por
amostra (N0/2 em cada componente). Com os pulsos de energia unitária de
sdrlink.pulsos, isso reproduz as fórmulas de BER clássicas, por exemplo
Q(sqrt(2 Eb/N0)) na BPSK coerente.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

EBN0_MIN_DB = -20.0
EBN0_MAX_DB = 60.0
ATRASO_MAX_AMOSTRAS = 1e6
PPM_MAX = 1000.0  # diferença de relógio aceita na simulação
MEIO_INTERPOLADOR = 16  # interpolador de reamostrar: 33 coeficientes (sinc com janela de Kaiser)
_JANELA_INTERPOLADOR = np.kaiser(2 * MEIO_INTERPOLADOR + 1, 8.0)
BLOCO_REAMOSTRAGEM = 2**16  # amostras de saída por bloco (memória: bloco × 33 complexos)


def awgn(
    sinal: NDArray[np.complex128],
    ebn0_db: float,
    amostras_por_bit: float,
    rng: np.random.Generator,
) -> NDArray[np.complex128]:
    """Soma ruído branco gaussiano complexo para o Eb/N0 pedido.

    Eb é a potência média do sinal inteiro vezes as amostras por **bit**: na DQPSK,
    sps / 2 (sps é por símbolo). Se o sinal tem silêncio entre quadros, a média inclui
    o silêncio e o Eb real dos quadros fica um pouco maior que o pedido.

    Raises:
        ValueError: sinal vazio ou sem potência, Eb/N0 ou amostras por bit inválidos.
    """
    if len(sinal) == 0:
        raise ValueError("sinal vazio")
    if not EBN0_MIN_DB <= ebn0_db <= EBN0_MAX_DB:
        raise ValueError(f"Eb/N0 fora de {EBN0_MIN_DB} a {EBN0_MAX_DB} dB: {ebn0_db}")
    if amostras_por_bit <= 0:
        raise ValueError(f"amostras por bit inválidas: {amostras_por_bit}")
    potencia = float(np.mean(np.abs(sinal) ** 2))
    if potencia == 0:
        raise ValueError("sinal sem potência")
    n0 = potencia * amostras_por_bit / 10 ** (ebn0_db / 10)
    ruido = rng.standard_normal(len(sinal)) + 1j * rng.standard_normal(len(sinal))
    return np.asarray(sinal + np.sqrt(n0 / 2) * ruido, dtype=np.complex128)


def girar(
    sinal: NDArray[np.complex128], offset_hz: float, taxa_sps: float, fase_rad: float = 0.0
) -> NDArray[np.complex128]:
    """Aplica um erro de fase fixo e um offset de frequência (a fase cresce com o tempo).

    Raises:
        ValueError: taxa de amostragem não positiva.
    """
    if taxa_sps <= 0:
        raise ValueError(f"taxa de amostragem inválida: {taxa_sps}")
    n = np.arange(len(sinal))
    return np.asarray(
        sinal * np.exp(1j * (fase_rad + 2 * np.pi * offset_hz * n / taxa_sps)), dtype=np.complex128
    )


def atrasar(sinal: NDArray[np.complex128], atraso_amostras: float) -> NDArray[np.complex128]:
    """Atrasa o sinal por um número fracionário de amostras (fase linear na frequência).

    O sinal é completado com zeros antes da FFT para o atraso não dar a volta no
    fim do vetor; a saída tem o mesmo comprimento da entrada.

    Raises:
        ValueError: atraso negativo ou grande demais.
    """
    if not 0 <= atraso_amostras <= ATRASO_MAX_AMOSTRAS:
        raise ValueError(f"atraso fora de 0 a {ATRASO_MAX_AMOSTRAS} amostras: {atraso_amostras}")
    n = len(sinal) + int(np.ceil(atraso_amostras)) + 16
    f = np.fft.fftfreq(n)
    espectro = np.fft.fft(sinal, n) * np.exp(-2j * np.pi * f * atraso_amostras)
    return np.asarray(np.fft.ifft(espectro)[: len(sinal)], dtype=np.complex128)


def reamostrar(sinal: NDArray[np.complex128], ppm: float) -> NDArray[np.complex128]:
    """O mesmo sinal amostrado por um relógio ppm partes por milhão mais rápido.

    Simula a diferença entre o relógio do DAC do Pluto e o do ADC do RTL: a amostra k
    da saída é o sinal no instante k (1 + ppm·10⁻⁶) da entrada, por interpolação sinc
    com janela de Kaiser (33 coeficientes), em blocos. A saída perde as amostras do fim
    que precisariam de entrada além do último ponto.

    Raises:
        ValueError: diferença fora de ±PPM_MAX ou sinal curto demais.
    """
    if not -PPM_MAX <= ppm <= PPM_MAX:
        raise ValueError(f"diferença de relógio fora de ±{PPM_MAX} ppm: {ppm}")
    fator = 1 + ppm * 1e-6
    n = int((len(sinal) - MEIO_INTERPOLADOR - 1) / fator)
    if n <= 0:
        raise ValueError("sinal curto demais para reamostrar")
    vizinhos = np.arange(-MEIO_INTERPOLADOR, MEIO_INTERPOLADOR + 1)
    estendido = np.concatenate(
        [np.zeros(MEIO_INTERPOLADOR, complex), sinal, np.zeros(MEIO_INTERPOLADOR + 1, complex)]
    )
    saida = np.zeros(n, dtype=np.complex128)
    for k in range(0, n, BLOCO_REAMOSTRAGEM):
        instantes = np.arange(k, min(k + BLOCO_REAMOSTRAGEM, n)) * fator
        base = np.floor(instantes).astype(np.int64)
        pesos = np.sinc((instantes - base)[:, None] - vizinhos[None, :]) * _JANELA_INTERPOLADOR
        pesos /= pesos.sum(axis=1, keepdims=True)
        indices = base[:, None] + vizinhos[None, :] + MEIO_INTERPOLADOR
        saida[k : k + len(base)] = np.sum(estendido[indices] * pesos, axis=1)
    return saida
