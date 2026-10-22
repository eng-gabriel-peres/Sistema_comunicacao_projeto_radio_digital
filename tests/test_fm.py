"""Testes da verificação absoluta pelas emissoras FM (sdrlink.fm)."""

import numpy as np
import pytest
from numpy.typing import NDArray

from sdrlink.fm import desvio_portadora_fm

TAXA_SPS = 2.048e6
DESLOCAMENTO_HZ = 250e3


def _fm(desvio_portadora_hz: float, n: int = 2**19) -> NDArray[np.complex64]:
    """FM estéreo simplificada: áudio de 1 kHz (±50 kHz) e piloto de 19 kHz (±7 kHz)."""
    rng = np.random.default_rng(4)
    t = np.arange(n) / TAXA_SPS
    freq_inst = 50e3 * np.sin(2 * np.pi * 1e3 * t) + 7e3 * np.sin(2 * np.pi * 19e3 * t)
    fase = 2 * np.pi * np.cumsum(DESLOCAMENTO_HZ + desvio_portadora_hz + freq_inst) / TAXA_SPS
    ruido = 0.1 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    resultado: NDArray[np.complex64] = (np.exp(1j * fase) + ruido).astype(np.complex64)
    return resultado


@pytest.mark.parametrize("desvio_hz", [-6950.0, 0.0, 3200.0])
def test_mede_o_desvio_da_portadora(desvio_hz: float) -> None:
    medido, incerteza = desvio_portadora_fm(_fm(desvio_hz), TAXA_SPS, DESLOCAMENTO_HZ)
    assert medido == pytest.approx(desvio_hz, abs=50)
    assert incerteza < 50


def test_argumentos_invalidos() -> None:
    sinal = _fm(0.0)
    with pytest.raises(ValueError, match="n_blocos"):
        desvio_portadora_fm(sinal, TAXA_SPS, DESLOCAMENTO_HZ, n_blocos=1)
    with pytest.raises(ValueError, match="não cabe"):
        desvio_portadora_fm(sinal, TAXA_SPS, 950e3)
    with pytest.raises(ValueError, match="curta"):
        desvio_portadora_fm(sinal[:1000], TAXA_SPS, DESLOCAMENTO_HZ)
