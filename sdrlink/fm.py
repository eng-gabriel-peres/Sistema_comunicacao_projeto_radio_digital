"""Erro absoluto de frequência do RTL-SDR medido com emissoras FM comerciais.

As emissoras FM ficam numa grade regulada e não dependem de nenhum Pluto, então
servem de referência independente: se todas aparecem deslocadas para o mesmo
lado, quem erra é o receptor. Em 22/10 isso revelou que o RTL do projeto erra
cerca de -64 ppm, e que a "calibração de 0 ppm" daquele dia tinha travado num
espúrio interno do RTL.

Método: translada a emissora para 0 Hz, filtra, demodula pela diferença de fase
entre amostras e tira a média da frequência instantânea. O áudio FM não tem
componente DC, logo essa média é o desvio da portadora.

Requisitos: CAL-01 (verificação independente da calibração).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.signal import firwin, lfilter

N_TAPS_FILTRO = 255
DECIMACAO = 8
BANDA_FM_HZ = 110e3  # desvio de ±75 kHz mais o espectro do áudio estéreo
ERRO_MAXIMO_PPM = 200
N_BLOCOS_MINIMO = 2  # precisa de pelo menos 2 blocos para estimar a incerteza


def desvio_portadora_fm(
    amostras: NDArray[np.complex64],
    taxa_sps: float,
    deslocamento_hz: float,
    n_blocos: int = 8,
) -> tuple[float, float]:
    """Desvio médio da portadora FM em relação ao esperado e o erro padrão.

    Args:
        amostras: IQ com a emissora em +deslocamento_hz.
        taxa_sps: taxa de amostragem.
        deslocamento_hz: onde a emissora deveria estar em banda base.
        n_blocos: em quantos pedaços dividir a captura para estimar a incerteza.

    Returns:
        (desvio_hz, erro_padrao_hz). Desvio negativo: chegou abaixo do esperado.

    Raises:
        ValueError: argumentos inválidos ou captura curta demais.
    """
    if taxa_sps <= 0 or n_blocos < N_BLOCOS_MINIMO:
        raise ValueError("taxa deve ser positiva e n_blocos >= 2")
    if abs(deslocamento_hz) + BANDA_FM_HZ >= taxa_sps / 2:
        raise ValueError("a emissora deslocada não cabe na banda amostrada")
    if len(amostras) < n_blocos * DECIMACAO * N_TAPS_FILTRO:
        raise ValueError("captura curta demais para a demodulação")
    t = np.arange(len(amostras)) / taxa_sps
    transladado = amostras.astype(np.complex128) * np.exp(-2j * np.pi * deslocamento_hz * t)
    filtrado = lfilter(firwin(N_TAPS_FILTRO, BANDA_FM_HZ, fs=taxa_sps), 1, transladado)
    x = filtrado[N_TAPS_FILTRO::DECIMACAO]  # descarta o transitório do filtro
    taxa_dec = taxa_sps / DECIMACAO
    freq_inst = np.angle(x[1:] * np.conj(x[:-1])) * taxa_dec / (2 * np.pi)
    por_bloco = freq_inst[: len(freq_inst) // n_blocos * n_blocos].reshape(n_blocos, -1).mean(1)
    return float(por_bloco.mean()), float(por_bloco.std(ddof=1) / np.sqrt(n_blocos))


def erro_absoluto_ppm(erro_medido_ppm: float, correcao_aplicada_ppm: int) -> float:
    """Erro do próprio RTL a partir de uma medida feita com correção aplicada.

    Aplicar +c ppm desloca o sinal observado em +c ppm (visto em 22/10: com 77
    ppm o tom subiu cerca de 70 kHz em 915 MHz), logo erro sem correção = erro
    medido - c.

    Raises:
        ValueError: correção fora de ±200 ppm.
    """
    if abs(correcao_aplicada_ppm) > ERRO_MAXIMO_PPM:
        raise ValueError(f"correção fora da faixa plausível: {correcao_aplicada_ppm}")
    return erro_medido_ppm - correcao_aplicada_ppm
