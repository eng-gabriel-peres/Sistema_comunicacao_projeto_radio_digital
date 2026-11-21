"""Testes de pulsos, modem, canal e espectro (sub-bloco 3b)."""

import numpy as np
import pytest
from scipy.special import erfc

from sdrlink import canal, espectro, modem, pulsos, quadro
from sdrlink.modem import ConfigModem

CONFIGS = [
    ConfigModem("ook", "retangular", 16),
    ConfigModem("ook", "rrc", 16),
    ConfigModem("bpsk", "retangular", 16),
    ConfigModem("bpsk", "rrc", 16),
    ConfigModem("dbpsk", "retangular", 16),
    ConfigModem("dbpsk", "rrc", 16),
    ConfigModem("fsk", "retangular", 16),
    ConfigModem("fsk", "gaussiano", 16),
]
NOMES = [f"{c.modulacao}-{c.pulso}" for c in CONFIGS]


def _bits(n: int, semente: int = 1) -> np.ndarray:
    return np.random.default_rng(semente).integers(0, 2, n).astype(np.uint8)


def test_pulsos_tem_energia_ou_area_unitaria_e_rrc_casado_sem_isi() -> None:
    assert np.sum(pulsos.retangular(8) ** 2) == pytest.approx(1)
    p = pulsos.rrc(0.35, 8, 8)
    assert np.sum(p**2) == pytest.approx(1)
    rc = np.convolve(p, p[::-1])  # cosseno levantado: zero nos outros instantes de símbolo
    centro = len(p) - 1
    outros = rc[centro % 8 :: 8]
    assert np.max(np.abs(np.delete(outros, centro // 8))) < 0.02 * rc[centro]
    assert pulsos.gaussiano(0.5, 8, 4).sum() == pytest.approx(8)


@pytest.mark.parametrize("config", CONFIGS, ids=NOMES)
def test_ida_e_volta_sem_ruido(config: ConfigModem) -> None:
    bits = _bits(500)
    assert np.array_equal(modem.demodular(modem.modular(bits, config), config, 500), bits)


@pytest.mark.parametrize("config", CONFIGS, ids=NOMES)
def test_quadro_v2_passa_pela_cadeia_com_ruido(config: ConfigModem) -> None:
    pacote = quadro.Pacote(321, bytes(range(128)))
    bits = quadro.montar_quadro(pacote)
    sinal = canal.awgn(modem.modular(bits, config), 16.0, config.sps, np.random.default_rng(2))
    recebidos = modem.demodular(sinal, config, len(bits))
    assert quadro.interpretar(recebidos[29:]).pacote == pacote  # depois de preâmbulo e sync


def test_ber_da_bpsk_coerente_bate_com_a_teoria() -> None:
    config = ConfigModem("bpsk", "rrc", 8)
    bits = _bits(200_000, 3)
    sinal = canal.awgn(modem.modular(bits, config), 6.0, 8, np.random.default_rng(4))
    ber = np.mean(modem.demodular(sinal, config, len(bits)) != bits)
    teoria = 0.5 * erfc(np.sqrt(10 ** (6.0 / 10)))  # 2,4e-3
    assert ber == pytest.approx(teoria, rel=0.15)


def test_bpsk_coerente_precisa_da_fase_e_dbpsk_nao() -> None:
    bits = _bits(400)
    girado = 1j * modem.modular(bits, ConfigModem("bpsk", "rrc", 8))  # 90 graus de erro de fase
    errados = np.mean(modem.demodular(girado, ConfigModem("bpsk", "rrc", 8), 400) != bits)
    assert errados > 0.3  # sem estimar a fase, a BPSK coerente vira cara ou coroa
    assert (
        modem.demodular(girado, ConfigModem("bpsk", "rrc", 8), 400, fase=np.pi / 2).tolist()
        == bits.tolist()
    )
    config = ConfigModem("dbpsk", "rrc", 8)
    girado = np.exp(1j * 2.0) * modem.modular(bits, config)
    assert np.array_equal(modem.demodular(girado, config, 400), bits)


def test_ook_independe_da_amplitude_e_da_fase() -> None:
    config = ConfigModem("ook", "rrc", 8)
    bits = _bits(300)
    sinal = 0.01 * np.exp(1j * 1.3) * modem.modular(bits, config)
    assert np.array_equal(modem.demodular(sinal, config, 300), bits)


def test_banda_99_do_rrc_e_da_bpsk_retangular() -> None:
    rng = np.random.default_rng(5)
    rrc = modem.modular(rng.integers(0, 2, 8000).astype(np.uint8), ConfigModem("bpsk", "rrc", 16))
    baixo, alto = espectro.banda_ocupada(rrc, 16.0, nperseg=4096)  # taxa normalizada: Rb = 1
    assert alto - baixo == pytest.approx(1.16, abs=0.04)  # abaixo de (1 + beta) = 1,35
    ret = modem.modular(
        rng.integers(0, 2, 8000).astype(np.uint8), ConfigModem("bpsk", "retangular", 256)
    )
    baixo, alto = espectro.banda_ocupada(ret, 256.0, nperseg=32768)
    assert alto - baixo == pytest.approx(20.56, rel=0.05)  # valor teórico do sinc²


def test_validacoes() -> None:
    with pytest.raises(ValueError, match="modulação"):
        ConfigModem("qam", "rrc", 8)
    with pytest.raises(ValueError, match="não serve"):
        ConfigModem("fsk", "rrc", 8)
    with pytest.raises(ValueError, match="não serve"):
        ConfigModem("bpsk", "gaussiano", 8)
    with pytest.raises(ValueError, match="amostras por símbolo"):
        ConfigModem("bpsk", "rrc", 1)
    with pytest.raises(ValueError, match="rolagem"):
        ConfigModem("bpsk", "rrc", 8, beta=0)
    with pytest.raises(ValueError, match="0 e 1"):
        modem.modular(np.array([0, 2], dtype=np.uint8), ConfigModem("bpsk", "rrc", 8))
    with pytest.raises(ValueError, match="curto"):
        modem.demodular(np.zeros(10, dtype=complex), ConfigModem("bpsk", "rrc", 8), 50)
    with pytest.raises(ValueError, match="Eb/N0"):
        canal.awgn(np.ones(10, dtype=complex), 100.0, 8, np.random.default_rng())
    with pytest.raises(ValueError, match="potência"):
        canal.awgn(np.zeros(10, dtype=complex), 10.0, 8, np.random.default_rng())
    with pytest.raises(ValueError, match="fração"):
        espectro.banda_ocupada(np.ones(8192, dtype=complex), 1.0, fracao=1.0)


@pytest.mark.parametrize("pulso", ["retangular", "rrc"])
def test_filtro_casado_amostra_no_pico_do_simbolo(pulso: str) -> None:
    config = ConfigModem("bpsk", pulso, 16)
    bits = _bits(200)
    z = modem._amostras_casadas(modem.modular(bits, config), config, 200)
    np.testing.assert_allclose(np.real(z), 2.0 * bits - 1, atol=0.02)  # amplitude exata no pico
