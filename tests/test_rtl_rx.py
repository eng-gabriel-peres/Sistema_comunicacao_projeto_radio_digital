"""Testes da interface do RTL-SDR (sdrlink.hw.rtl_rx)."""

import numpy as np
import pytest

from sdrlink import canal
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


def test_nivel_eficaz_e_a_janela_do_adc() -> None:
    rng = np.random.default_rng(5)
    x = rng.standard_normal(100_000) + 1j * rng.standard_normal(100_000)
    for nivel in (-40.0, -20.0, -12.0):  # sem saturação; em −6 dBFS o corte já baixa o eficaz
        assert rtl_rx.nivel_eficaz_dbfs(canal.quantizar_8_bits(x, nivel)) == pytest.approx(
            nivel, abs=0.3
        )
    assert rtl_rx.nivel_eficaz_dbfs(np.zeros(4, complex)) == rtl_rx.NIVEL_PISO_DBFS
    with pytest.raises(ValueError, match="vazio"):
        rtl_rx.nivel_eficaz_dbfs(np.zeros(0, complex))
    assert rtl_rx.aviso_de_nivel(-20.0) is None
    assert rtl_rx.aviso_de_nivel(rtl_rx.NIVEL_MIN_DBFS) is None
    assert rtl_rx.aviso_de_nivel(rtl_rx.NIVEL_MAX_DBFS) is None
    assert "subir o ganho" in (rtl_rx.aviso_de_nivel(-35.0) or "")
    assert "baixar o ganho" in (rtl_rx.aviso_de_nivel(-3.0) or "")


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


class _RadioFalso:
    def __init__(self) -> None:
        self.cancelamentos = 0

    def cancel_read_async(self) -> None:
        self.cancelamentos += 1


def test_acumulador_descarta_inicio_guarda_em_ordem_e_cancela_uma_vez() -> None:
    radio = _RadioFalso()
    acc = rtl_rx.Acumulador(radio, n_bytes=10, n_bytes_descarte=4)
    blocos = [
        np.arange(0, 6, dtype=np.uint8),
        np.arange(6, 12, dtype=np.uint8),
        np.arange(12, 18, dtype=np.uint8),
    ]
    for b in blocos:
        acc(b, None)
    assert acc.completo
    np.testing.assert_array_equal(acc.dados, np.arange(4, 14, dtype=np.uint8))
    assert radio.cancelamentos == 1
    acc(np.arange(50, 56, dtype=np.uint8), None)  # bloco depois de cancelado é ignorado
    np.testing.assert_array_equal(acc.dados, np.arange(4, 14, dtype=np.uint8))


def test_acumulador_rejeita_tamanhos_invalidos() -> None:
    with pytest.raises(ValueError, match="inválidos"):
        rtl_rx.Acumulador(_RadioFalso(), n_bytes=7, n_bytes_descarte=0)


class _RadioAssincronoFalso(_RadioFalso):
    """Entrega blocos ao callback e, no fim, levanta o erro do cancelamento como o pyrtlsdr."""

    def __init__(self, n_blocos: int) -> None:
        super().__init__()
        self.n_blocos = n_blocos

    def read_bytes_async(self, callback: rtl_rx.Acumulador, num_bytes: int) -> None:
        for i in range(self.n_blocos):
            callback(np.full(num_bytes, i, dtype=np.uint8), None)
        raise OSError(-5, "LIBUSB_ERROR_NOT_FOUND")


def test_ler_ignora_erro_do_cancelamento_com_vetor_cheio() -> None:
    n = rtl_rx.AMOSTRAS_POR_LEITURA
    radio = _RadioAssincronoFalso(n_blocos=2)  # 1 bloco de descarte + 1 de dados
    iq = rtl_rx._ler(radio, n, 2.048e6)
    assert len(iq) == n
    assert radio.cancelamentos == 1


def test_ler_acusa_leitura_incompleta() -> None:
    radio = _RadioAssincronoFalso(n_blocos=1)  # só o descarte chega
    with pytest.raises(RuntimeError, match="incompleta"):
        rtl_rx._ler(radio, rtl_rx.AMOSTRAS_POR_LEITURA, 2.048e6)
