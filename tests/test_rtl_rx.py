"""Testes da interface do RTL-SDR (sdrlink.hw.rtl_rx)."""

import numpy as np
import pytest

from sdrlink.hw import rtl_rx
from sdrlink.hw.rtl_rx import ConfigRtl


def test_bytes_para_iq_usa_a_escala_do_pyrtlsdr() -> None:
    iq = rtl_rx.bytes_para_iq(np.array([0, 255, 255, 0], dtype=np.uint8))
    assert iq.dtype == np.complex64
    np.testing.assert_allclose(iq, [-1 + 1j, 1 - 1j])


def test_bytes_para_iq_rejeita_entradas_invalidas() -> None:
    with pytest.raises(ValueError, match="ímpar"):
        rtl_rx.bytes_para_iq(np.zeros(3, dtype=np.uint8))
    with pytest.raises(ValueError, match="1-D"):
        rtl_rx.bytes_para_iq(np.zeros((2, 2), dtype=np.uint8))


def test_fracao_saturada() -> None:
    amostras = np.array([0.1 + 0.1j, 1.0 + 0j, 0.2 - 1.0j, 0j], dtype=np.complex64)
    assert rtl_rx.fracao_saturada(amostras) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="vazio"):
        rtl_rx.fracao_saturada(np.zeros(0, dtype=np.complex64))


def test_config_valida_e_aceita() -> None:
    config = ConfigRtl(914.95e6, 2.048e6, 20.0, 0)
    assert config.correcao_ppm == 0


@pytest.mark.parametrize(
    ("argumentos", "mensagem"),
    [
        ((10e6, 2.048e6, 20.0, 0), "centro"),
        ((915e6, 500e3, 20.0, 0), "taxa"),
        ((915e6, 2.048e6, 60.0, 0), "ganho"),
        ((915e6, 2.048e6, 20.0, 500), "correção"),
    ],
)
def test_config_invalida_e_rejeitada(
    argumentos: tuple[float, float, float, int], mensagem: str
) -> None:
    with pytest.raises(ValueError, match=mensagem):
        ConfigRtl(*argumentos)


def test_capturar_rejeita_tamanho_invalido() -> None:
    with pytest.raises(ValueError, match="múltiplo"):
        rtl_rx.capturar(ConfigRtl(915e6, 2.048e6, 20.0), 1000)


@pytest.mark.hardware
def test_captura_real_devolve_complex64_e_parametros() -> None:
    captura = rtl_rx.capturar(ConfigRtl(100e6, 2.048e6, 20.0), rtl_rx.AMOSTRAS_POR_LEITURA)
    assert captura.amostras.dtype == np.complex64
    assert len(captura.amostras) == rtl_rx.AMOSTRAS_POR_LEITURA
    assert captura.centro_hz == pytest.approx(100e6)
