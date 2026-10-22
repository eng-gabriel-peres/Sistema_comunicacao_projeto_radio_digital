"""Testes da calibração de frequência (sdrlink.calibracao)."""

import numpy as np
import pytest
from numpy.typing import NDArray

from sdrlink import calibracao as cal

TAXA_SPS = 2.048e6
DESLOCAMENTO_HZ = 250e3


def _tom(freq_hz: float, n: int, snr_db: float, semente: int = 1) -> NDArray[np.complex64]:
    """Tom complexo com ruído branco (SNR por amostra), mais um DC como o do RTL."""
    rng = np.random.default_rng(semente)
    t = np.arange(n) / TAXA_SPS
    ruido_std = 10 ** (-snr_db / 20) / np.sqrt(2)
    ruido = ruido_std * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    sinal = np.exp(2j * np.pi * freq_hz * t + 0.7j) + ruido + 0.05
    resultado: NDArray[np.complex64] = sinal.astype(np.complex64)
    return resultado


def _ook(freq_hz: float, n: int, semente: int = 2) -> NDArray[np.complex64]:
    """OOK a 10 kbit/s com quadro de 229 bits repetido (como o pluto_tx_ook_v2.py)."""
    rng = np.random.default_rng(semente)
    quadro = rng.integers(0, 2, 229)
    envoltoria = np.resize(np.repeat(quadro, round(TAXA_SPS / 10e3)), n)
    t = np.arange(n) / TAXA_SPS
    ruido = 0.3 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    return (envoltoria * np.exp(2j * np.pi * freq_hz * t) + ruido).astype(np.complex64)


def test_tom_puro_estimado_com_erro_menor_que_0_2_hz() -> None:
    freq = DESLOCAMENTO_HZ + 123.4
    est = cal.estimar_tom(_tom(freq, cal.N_FFT_PADRAO, snr_db=0), TAXA_SPS, DESLOCAMENTO_HZ, 60e3)
    assert abs(est.freq_hz - freq) < 0.2
    assert est.snr_db > 40
    assert est.resolucao_hz == pytest.approx(TAXA_SPS / cal.N_FFT_PADRAO)


@pytest.mark.parametrize("fracao_bin", [0.0, 0.25, 0.5])
def test_interpolacao_acerta_entre_bins(fracao_bin: float) -> None:
    n_fft = 2**16
    freq = DESLOCAMENTO_HZ + (100 + fracao_bin) * TAXA_SPS / n_fft
    est = cal.estimar_tom(_tom(freq, n_fft, snr_db=20), TAXA_SPS, DESLOCAMENTO_HZ, 60e3, n_fft)
    assert abs(est.freq_hz - freq) < 0.1 * est.resolucao_hz


def test_ook_de_referencia_mede_a_portadora() -> None:
    freq = DESLOCAMENTO_HZ - 731.6
    n_fft = 2**18
    est = cal.estimar_tom(_ook(freq, n_fft), TAXA_SPS, DESLOCAMENTO_HZ, 60e3, n_fft)
    assert abs(est.freq_hz - freq) < 0.1 * est.resolucao_hz
    assert est.snr_db > cal.SNR_MINIMA_DB


def test_sem_tom_nenhuma_raia_passa_do_limiar() -> None:
    rng = np.random.default_rng(3)
    n = 8 * 2**14
    ruido = (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)
    freqs, potencia = cal.espectro_medio(ruido, TAXA_SPS, 2**14)
    raias = cal.detectar_raias(freqs, potencia, DESLOCAMENTO_HZ, 60e3)
    assert raias[0].snr_db < cal.SNR_MINIMA_DB


def test_estimar_por_blocos_e_resumir_medem_a_deriva() -> None:
    n_fft = 2**16
    duracao_s = n_fft / TAXA_SPS
    blocos = [_tom(DESLOCAMENTO_HZ + 50 * i * duracao_s, n_fft, 10, semente=i) for i in range(4)]
    estimativas = cal.estimar_por_blocos(
        np.concatenate(blocos), TAXA_SPS, DESLOCAMENTO_HZ, 60e3, n_fft
    )
    resumo = cal.resumir(estimativas, duracao_s)
    assert resumo.n == 4
    assert resumo.deriva_hz_s == pytest.approx(50, abs=5)


def test_resumir_um_bloco_tem_desvio_e_deriva_zero() -> None:
    est = cal.EstimativaTom(freq_hz=10.0, snr_db=30.0, resolucao_hz=2.0)
    resumo = cal.resumir([est], 0.5)
    assert (resumo.media_hz, resumo.desvio_hz, resumo.deriva_hz_s) == (10.0, 0.0, 0.0)


def test_convencao_de_sinal_ppm_e_correcao() -> None:
    # tom chegou 915 Hz acima em 915 MHz: erro +1 ppm, correção -1 ppm
    assert cal.erro_ppm(915e6 + 915, 915e6) == pytest.approx(1.0)
    assert cal.correcao_rtl_ppm(1.0) == -1
    assert cal.correcao_rtl_ppm(-33.6) == 34


def test_residuo_previsto_sobra_da_parte_fracionaria() -> None:
    erro = 1.3
    assert cal.residuo_previsto_hz(erro, cal.correcao_rtl_ppm(erro), 915e6) == pytest.approx(274.5)


@pytest.mark.parametrize(
    ("kwargs", "mensagem"),
    [
        ({"taxa_sps": 0}, "taxa"),
        ({"janela_busca_hz": 0}, "janela"),
        ({"freq_busca_hz": 1.0e6}, "ultrapassa"),
        ({"n_fft": 1000}, "potência de 2"),
        ({"n_fft": 2**20}, "insuficientes"),
    ],
)
def test_argumentos_invalidos_sao_rejeitados(kwargs: dict[str, float], mensagem: str) -> None:
    argumentos: dict[str, float] = {
        "taxa_sps": TAXA_SPS,
        "freq_busca_hz": DESLOCAMENTO_HZ,
        "janela_busca_hz": 60e3,
        "n_fft": 2**16,
    }
    argumentos.update(kwargs)
    amostras = np.zeros(2**16, dtype=np.complex64)
    with pytest.raises(ValueError, match=mensagem):
        cal.estimar_tom(
            amostras,
            argumentos["taxa_sps"],
            argumentos["freq_busca_hz"],
            argumentos["janela_busca_hz"],
            int(argumentos["n_fft"]),
        )


def test_entradas_invalidas_das_contas() -> None:
    with pytest.raises(ValueError, match="1-D"):
        cal.estimar_tom(np.zeros((2, 2**10), np.complex64), TAXA_SPS, DESLOCAMENTO_HZ, 60e3, 2**10)
    with pytest.raises(ValueError, match="menor que um bloco"):
        cal.estimar_por_blocos(np.zeros(10, np.complex64), TAXA_SPS, DESLOCAMENTO_HZ, 60e3, 2**10)
    with pytest.raises(ValueError, match="nenhuma"):
        cal.resumir([], 0.5)
    with pytest.raises(ValueError, match="duração"):
        cal.resumir([cal.EstimativaTom(0.0, 0.0, 1.0)], 0)
    with pytest.raises(ValueError, match="esperada"):
        cal.erro_ppm(1.0, 0)
    with pytest.raises(ValueError, match="plausível"):
        cal.correcao_rtl_ppm(500)
    with pytest.raises(ValueError, match="frequência"):
        cal.residuo_previsto_hz(0.1, 0, -1)


def test_espectro_medio_e_deteccao_ordenam_as_raias() -> None:
    n_fft = 2**16
    forte = _tom(DESLOCAMENTO_HZ - 44.0, 4 * n_fft, snr_db=0, semente=5)
    fraco = 0.3 * _tom(DESLOCAMENTO_HZ - 15.5e3, 4 * n_fft, snr_db=60, semente=6)
    freqs, potencia = cal.espectro_medio(forte + fraco, TAXA_SPS, n_fft)
    raias = cal.detectar_raias(freqs, potencia, DESLOCAMENTO_HZ, 60e3, n_max=2)
    assert len(raias) == 2
    assert abs(raias[0].freq_hz - (DESLOCAMENTO_HZ - 44.0)) < TAXA_SPS / n_fft
    assert abs(raias[1].freq_hz - (DESLOCAMENTO_HZ - 15.5e3)) < TAXA_SPS / n_fft
    assert raias[0].snr_db > raias[1].snr_db > cal.SNR_MINIMA_DB


def test_entradas_invalidas_da_deteccao() -> None:
    with pytest.raises(ValueError, match="taxa"):
        cal.espectro_medio(np.zeros(2**10, np.complex64), 0, 2**10)
    with pytest.raises(ValueError, match="menor que um bloco"):
        cal.espectro_medio(np.zeros(10, np.complex64), TAXA_SPS, 2**10)
    freqs = np.fft.fftfreq(2**10, 1 / TAXA_SPS)
    with pytest.raises(ValueError, match="mesmo tamanho"):
        cal.detectar_raias(freqs, np.ones(5), DESLOCAMENTO_HZ, 60e3)
    with pytest.raises(ValueError, match="n_max"):
        cal.detectar_raias(freqs, np.ones(2**10), DESLOCAMENTO_HZ, 60e3, n_max=0)
    with pytest.raises(ValueError, match="bins"):
        cal.detectar_raias(freqs, np.ones(2**10), DESLOCAMENTO_HZ, 1.0)
