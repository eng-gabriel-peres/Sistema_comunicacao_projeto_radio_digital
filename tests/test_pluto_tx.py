"""Testes do transmissor do Pluto (sdrlink.hw.pluto_tx)."""

import numpy as np
import pytest

from sdrlink.hw import pluto_tx
from sdrlink.hw.pluto_tx import ConfigPluto


def test_buffer_fecha_ciclos_inteiros() -> None:
    n = pluto_tx.n_amostras_ciclos_inteiros(250e3, 2e6)
    assert n >= pluto_tx.N_MINIMO
    assert (250e3 * n / 2e6).is_integer()


def test_tom_do_tx_test_viraria_pente() -> None:
    # 200 kHz em 1024 amostras a 2 MS/s = 102,4 ciclos (achado A15)
    with pytest.raises(ValueError, match="pente"):
        pluto_tx.tom_complexo(200e3, 2e6, 1024)


def test_tom_com_ciclos_inteiros_e_uma_raia_so() -> None:
    n = pluto_tx.n_amostras_ciclos_inteiros(250e3, 2e6)
    tom = pluto_tx.tom_complexo(250e3, 2e6, n)
    espectro = np.abs(np.fft.fft(tom)) ** 2
    assert espectro.max() / espectro.sum() > 0.999999
    assert np.max(np.abs(tom)) == pytest.approx(pluto_tx.AMPLITUDE_PADRAO, rel=1e-6)


def test_argumentos_invalidos_do_tom() -> None:
    with pytest.raises(ValueError, match="entre 0 e taxa/2"):
        pluto_tx.n_amostras_ciclos_inteiros(1.5e6, 2e6)
    with pytest.raises(ValueError, match="fundo de escala"):
        pluto_tx.tom_complexo(250e3, 2e6, 1024, amplitude=40000)


def test_config_padrao_e_validacao() -> None:
    config = ConfigPluto(915e6)
    assert config.ganho_db == -30.0
    with pytest.raises(ValueError, match="LO"):
        ConfigPluto(10e6)
    with pytest.raises(ValueError, match="taxa"):
        ConfigPluto(915e6, taxa_sps=100e3)
    with pytest.raises(ValueError, match="ganho"):
        ConfigPluto(915e6, ganho_db=5.0)
    with pytest.raises(ValueError, match="URI"):
        ConfigPluto(915e6, uri="")


def test_transmitir_rejeita_duracao_e_buffer_invalidos() -> None:
    tom = pluto_tx.tom_complexo(250e3, 2e6, 1024)
    with pytest.raises(ValueError, match="duração"):
        pluto_tx.transmitir(ConfigPluto(915e6), tom, 0)
    with pytest.raises(ValueError, match="vazio"):
        pluto_tx.transmitir(ConfigPluto(915e6), tom[:0], 1.0)
