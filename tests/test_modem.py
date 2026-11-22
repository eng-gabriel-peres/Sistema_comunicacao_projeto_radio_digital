"""Testes de pulsos, modem, canal e espectro (sub-bloco 3b)."""

import numpy as np
import pytest
from scipy.special import erfc

from sdrlink import canal, espectro, modem, pulsos, quadro, teoria
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
def test_quadro_passa_pela_cadeia_com_ruido(config: ConfigModem) -> None:
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
    z = modem.saida_casada(modem.modular(bits, config), config, 200)
    np.testing.assert_allclose(np.real(z), 2.0 * bits - 1, atol=0.02)  # amplitude exata no pico


def test_ber_teorica_em_valores_conhecidos() -> None:

    assert teoria.ber_bpsk(9.6)[()] == pytest.approx(1.0e-5, rel=0.05)  # valor clássico de tabela
    assert teoria.ber_dbpsk(0.0)[()] == pytest.approx(0.5 * np.exp(-1))
    assert teoria.ber_fsk_nao_coerente(10.0)[()] == pytest.approx(0.5 * np.exp(-5))
    assert teoria.ber_bpsk(8.0, np.pi / 2)[()] == pytest.approx(0.5)  # 90 graus: cara ou coroa
    # OOK exata: perto da aproximação 1/2 exp(-Eb/2N0) em SNR alta, e 1/2 sem sinal
    ook = teoria.ber_ook_nao_coerente(np.array([-20.0, 14.0]), limiar="meio")
    assert ook[0] == pytest.approx(0.5, abs=0.01)
    assert ook[1] == pytest.approx(0.5 * np.exp(-(10**1.4) / 2), rel=0.5)
    assert teoria.ber_ook_nao_coerente(10.0)[()] < teoria.ber_ook_nao_coerente(10.0, "meio")[()]
    with pytest.raises(ValueError, match="limiar"):
        teoria.ber_ook_nao_coerente(10.0, "fixo")


def test_ber_simulada_da_ook_bate_com_a_formula_exata() -> None:

    config = ConfigModem("ook", "rrc", 8)
    bits = _bits(200_000, 6)
    sinal = canal.awgn(modem.modular(bits, config), 10.0, 8, np.random.default_rng(7))
    ber = np.mean(modem.demodular(sinal, config, len(bits)) != bits)
    # o limiar por k-médias fica entre o ótimo e o da metade da amplitude
    assert (
        teoria.ber_ook_nao_coerente(10.0)[()] < ber < teoria.ber_ook_nao_coerente(10.0, "meio")[()]
    )


def test_girar_e_atrasar() -> None:
    s = np.exp(1j * 0.3 * np.arange(64))
    g = canal.girar(s, 1000.0, 8000.0, fase_rad=0.5)
    np.testing.assert_allclose(np.angle(g[1] / s[1]), 0.5 + 2 * np.pi * 1000 / 8000)
    pulso = np.zeros(64, dtype=complex)
    pulso[10] = 1
    np.testing.assert_allclose(canal.atrasar(pulso, 3.0)[13], 1, atol=1e-9)  # atraso inteiro
    suave = modem.modular(_bits(40), ConfigModem("bpsk", "rrc", 8))
    meia = canal.atrasar(canal.atrasar(suave, 0.5), 0.5)
    np.testing.assert_allclose(meia[24:-24], canal.atrasar(suave, 1.0)[24:-24], atol=1e-4)  # miolo
    with pytest.raises(ValueError, match="atraso"):
        canal.atrasar(pulso, -1.0)
    with pytest.raises(ValueError, match="taxa"):
        canal.girar(pulso, 10.0, 0.0)


@pytest.mark.parametrize("pulso", ["retangular", "gaussiano"])
def test_janela_da_2fsk_esta_no_ponto_otimo(pulso: str) -> None:
    # deslocar o sinal uma amostra para qualquer lado não pode melhorar a BER: a janela do
    # correlator já está no melhor lugar (uma janela 1,5 amostra adiantada passou despercebida)
    config = ConfigModem("fsk", pulso, 8)
    rng = np.random.default_rng(12)
    bits = rng.integers(0, 2, 200_000).astype(np.uint8)
    sinal = canal.awgn(modem.modular(bits, config), 11.0, 8, rng)
    n = len(bits) - 4
    ber = {
        d: np.mean(modem.demodular(np.roll(sinal, -d), config, n) != bits[:n]) for d in (-1, 0, 1)
    }
    assert ber[0] <= 1.15 * min(ber[-1], ber[1])


def test_ber_da_gfsk_na_referencia_da_etapa_4() -> None:
    # Etapa 4 (antes da troca da integral de fase): GFSK BT 0,5 com BER 2,0e-3 em 11 dB
    config = ConfigModem("fsk", "gaussiano", 8)
    rng = np.random.default_rng(13)
    bits = rng.integers(0, 2, 200_000).astype(np.uint8)
    sinal = canal.awgn(modem.modular(bits, config), 11.0, 8, rng)
    assert np.mean(modem.demodular(sinal, config, len(bits)) != bits) == pytest.approx(
        2.0e-3, rel=0.3
    )


@pytest.mark.parametrize(
    "config",
    [
        ConfigModem("ook", "rrc", 8),
        ConfigModem("bpsk", "rrc", 8),
        ConfigModem("dbpsk", "rrc", 8),
        ConfigModem("dqpsk", "rrc", 8),
        ConfigModem("fsk", "gaussiano", 16),
    ],
    ids=["ook", "bpsk", "dbpsk", "dqpsk", "gfsk"],
)
def test_saida_suave_tem_o_sinal_da_decisao_dura(config: ConfigModem) -> None:
    rng = np.random.default_rng(41)
    bits = rng.integers(0, 2, 400).astype(np.uint8)
    y = modem.modular(bits, config)
    # Eb/N0 baixo, por bit: alguns bits errados em todas
    y = canal.awgn(y, 3.0, config.sps / config.bits_por_simbolo, rng)
    suaves = modem.demodular_suave(y, config, 400)
    duros = modem.demodular(y, config, 400)
    np.testing.assert_array_equal((suaves > 0).astype(np.uint8), duros)
    assert 0.75 < np.mean(duros == bits) < 1  # erra alguns, acerta a maioria
    errados = duros != bits
    assert np.mean(np.abs(suaves[errados])) < np.mean(np.abs(suaves[~errados]))  # menos certeza


# ---- DQPSK (bloco 10) ----


@pytest.mark.parametrize("n", [1, 2, 3, 28, 29, 30, 31, 1109])
@pytest.mark.parametrize("prefixo", [0, 29])
def test_dqpsk_ida_e_volta_e_numero_de_simbolos(n: int, prefixo: int) -> None:
    config = ConfigModem("dqpsk", "rrc", 4)
    bits = _bits(n, n)
    um_por_simbolo = min(prefixo, n)
    sinal = modem.modular(bits, config, prefixo)
    simbolos = um_por_simbolo + (n - um_por_simbolo + 1) // 2  # corpo ímpar ganha um bit
    assert modem.simbolos(n, config, prefixo) == simbolos
    assert modem.bits_em(simbolos, config, prefixo) in (n, n + 1)
    assert len(sinal) == (simbolos + 1) * 4 + len(config.formato()) - 1  # +1: referência
    np.testing.assert_array_equal(modem.demodular(sinal, config, n, prefixo=prefixo), bits)


def test_dqpsk_mapa_de_gray_e_prefixo_igual_ao_da_dbpsk() -> None:
    # giro de cada par: 00 -> 0, 01 -> 90, 11 -> 180, 10 -> 270 graus; vizinhos diferem em 1 bit
    graus = np.degrees(np.angle(modem.GIROS_DQPSK)) % 360
    assert np.allclose(graus, [0, 90, 270, 180])
    ordem = [0b00, 0b01, 0b11, 0b10]  # pela fase crescente
    assert all(bin(ordem[k] ^ ordem[(k + 1) % 4]).count("1") == 1 for k in range(4))
    bits = quadro.montar_quadro(quadro.Pacote(9, bytes(range(128))))
    dq = modem.modular(bits, ConfigModem("dqpsk", "rrc", 4), quadro.BITS_PREFIXO)
    db = modem.modular(bits, ConfigModem("dbpsk", "rrc", 4))
    np.testing.assert_allclose(dq[: 29 * 4], db[: 29 * 4], atol=1e-12)  # o RX acha os dois igual
    assert modem.simbolos(len(bits), ConfigModem("dqpsk", "rrc", 4), 29) == 29 + 544


def test_dqpsk_nao_precisa_da_fase_e_bate_com_a_teoria() -> None:
    config = ConfigModem("dqpsk", "rrc", 4)
    bits = _bits(400_000, 5)
    sinal = modem.modular(bits, config)
    girado = np.exp(1j * 1.234) * sinal
    np.testing.assert_array_equal(modem.demodular(girado, config, len(bits)), bits)
    # Eb/N0 de 9 dB: com 2 bits por símbolo, o Eb é o de 2 amostras (sps / 2)
    ruidoso = canal.awgn(sinal, 9.0, 2, np.random.default_rng(6))
    ber = np.mean(modem.demodular(ruidoso, config, len(bits)) != bits)
    assert ber == pytest.approx(float(teoria.ber_dqpsk(9.0)), rel=0.12)  # 1,27e-3


def test_ber_teorica_da_dqpsk() -> None:
    # valores da fórmula exata (Marcum). Abaixo de uns 2,5 dB a DQPSK erra menos bits que a
    # DBPSK; acima, erra mais (cerca de 1,4 dB pior a 1e-4)
    np.testing.assert_allclose(
        teoria.ber_dqpsk([6.0, 9.0, 10.0]), [1.7236e-2, 1.2671e-3, 3.4318e-4], rtol=1e-3
    )
    ebn0 = np.arange(0.0, 14.0, 0.5)
    assert np.all(np.diff(teoria.ber_dqpsk(ebn0)) < 0)
    assert np.all(teoria.ber_dqpsk(ebn0[ebn0 >= 3]) > teoria.ber_dbpsk(ebn0[ebn0 >= 3]))
    assert np.all(teoria.ber_dqpsk(ebn0[ebn0 <= 2]) < teoria.ber_dbpsk(ebn0[ebn0 <= 2]))


def test_reamostrar_simula_a_diferenca_de_relogio() -> None:
    # um tom de f ciclos por amostra, amostrado 1000 ppm mais rápido, vira f (1 + 1e-3)
    n = np.arange(20_000)
    tom = np.exp(2j * np.pi * 0.01 * n)
    saida = canal.reamostrar(tom, 1000.0)
    esperado = np.exp(2j * np.pi * 0.01 * 1.001 * np.arange(len(saida)))
    meio = slice(100, len(saida) - 100)  # longe das bordas do interpolador
    np.testing.assert_allclose(saida[meio], esperado[meio], atol=1e-3)
    assert len(saida) == int((len(tom) - 17) / 1.001)
    np.testing.assert_allclose(canal.reamostrar(tom, 0.0)[meio], tom[meio], atol=1e-9)
    with pytest.raises(ValueError, match="ppm"):
        canal.reamostrar(tom, 5000.0)
    with pytest.raises(ValueError, match="curto"):
        canal.reamostrar(tom[:10], 0.0)
