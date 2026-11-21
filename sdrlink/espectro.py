"""Densidade espectral de potência e banda ocupada a 99%.

Requisito: MET-04 e seção 7 do enunciado: "largura da faixa que contém 99% da
potência total do sinal", estimada pela densidade espectral de potência. O
limite da prova é de 1 MHz.

A banda é a faixa entre os pontos em que a potência acumulada atinge 0,5% e
99,5% do total (0,5% de cada lado fica de fora). A mesma função serve para o
sinal simulado (Etapa 3) e para a captura do RTL-SDR (Etapa 5).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.signal import welch

FRACAO_PADRAO = 0.99
NPERSEG_PADRAO = 4096


def densidade(
    sinal: NDArray[np.complexfloating], taxa_sps: float, nperseg: int = NPERSEG_PADRAO
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Densidade espectral (Welch, janela de Hann), com as frequências em ordem crescente.

    Raises:
        ValueError: sinal mais curto que um segmento.
    """
    if len(sinal) < nperseg:
        raise ValueError(f"sinal de {len(sinal)} amostras, menor que o segmento de {nperseg}")
    f, p = welch(sinal, fs=taxa_sps, nperseg=nperseg, return_onesided=False, detrend=False)
    return np.fft.fftshift(f), np.fft.fftshift(p)


def banda_ocupada(
    sinal: NDArray[np.complexfloating],
    taxa_sps: float,
    fracao: float = FRACAO_PADRAO,
    nperseg: int = NPERSEG_PADRAO,
) -> tuple[float, float]:
    """Limites inferior e superior (Hz) da faixa que contém a fração pedida da potência.

    Raises:
        ValueError: fração fora de (0, 1) ou sinal curto demais.
    """
    if not 0 < fracao < 1:
        raise ValueError(f"fração fora de (0, 1): {fracao}")
    f, p = densidade(sinal, taxa_sps, nperseg)
    acumulada = np.cumsum(p) / np.sum(p)
    sobra = (1 - fracao) / 2
    return float(np.interp(sobra, acumulada, f)), float(np.interp(1 - sobra, acumulada, f))
