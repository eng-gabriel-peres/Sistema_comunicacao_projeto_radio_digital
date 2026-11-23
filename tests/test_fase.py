"""Testes das imperfeições do hardware: ruído de fase (simulado e medido num tom) e ADC do RTL."""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from sdrlink import canal, config, fase
from sdrlink.hw import rtl_rx

FS = 2.048e6
N = 2**19  # 0,26 s
F_TOM = 249.6e3
LARGURA_HZ = 50.0
ATRASO = 80  # um símbolo da prova B


def _tom(
    largura_hz: float = LARGURA_HZ,
    snr_db: float = 40.0,
    deriva_hz_por_s: float = 0.0,
    semente: int = 1,
) -> np.ndarray:
    """Tom com ruído de fase de Wiener, deriva de frequência e ruído branco."""
    rng = np.random.default_rng(semente)
    t = np.arange(N) / FS
    ph = 2 * np.pi * (F_TOM * t + 0.5 * deriva_hz_por_s * t**2) + canal.ruido_de_fase(
        N, largura_hz, FS, rng
    )
    sigma = np.sqrt(10 ** (-snr_db / 10) / 2)
    ruido = sigma * (rng.standard_normal(N) + 1j * rng.standard_normal(N))
    return np.asarray(np.exp(1j * ph) + ruido, dtype=np.complex128)


def _esperado(largura_hz: float, atraso: int) -> float:
    return float(np.sqrt(2 * np.pi * largura_hz * atraso / FS))


def test_ruido_de_fase_de_wiener_tem_a_variancia_do_modelo() -> None:
    rng = np.random.default_rng(3)
    ph = canal.ruido_de_fase(2_000_000, 1000.0, FS, rng)
    for atraso in (1, 80, 800):
        variacao = ph[atraso:] - ph[:-atraso]
        assert np.std(variacao) == pytest.approx(_esperado(1000.0, atraso), rel=0.03)
    assert not np.any(canal.ruido_de_fase(100, 0.0, FS, rng))
    with pytest.raises(ValueError, match="inválidos"):
        canal.ruido_de_fase(0, 10.0, FS, rng)
    with pytest.raises(ValueError, match="inválidos"):
        canal.ruido_de_fase(10, -1.0, FS, rng)


def test_adc_de_8_bits_do_rtl() -> None:
    assert canal.ESCALA_ADC_RTL == rtl_rx.ESCALA_ADC
    rng = np.random.default_rng(4)
    x = rng.standard_normal(400_000) + 1j * rng.standard_normal(400_000)
    q = canal.quantizar_8_bits(x, -20.0)
    niveis = (np.arange(256) - rtl_rx.ESCALA_ADC) / rtl_rx.ESCALA_ADC
    assert np.all(np.isin(q.real, niveis)) and np.all(np.isin(q.imag, niveis))
    # nível eficaz pedido e SQNR do ADC ideal: −20 + 10·log10(12·127,5²) = 32,9 dB por componente
    assert 20 * np.log10(np.std(q.real)) == pytest.approx(-20.0, abs=0.05)
    referencia = x * (10 ** (-20 / 20) / np.sqrt(np.mean(np.abs(x) ** 2) / 2))
    sqnr = 10 * np.log10(np.mean(np.abs(referencia) ** 2) / np.mean(np.abs(q - referencia) ** 2))
    assert sqnr == pytest.approx(32.9, abs=0.3)
    assert rtl_rx.fracao_saturada(q.astype(np.complex64)) == 0.0
    # perto do fundo de escala o ADC satura
    saturado = canal.quantizar_8_bits(x, -3.0)
    assert (
        np.max(np.abs(saturado.real)) == 1.0
        and rtl_rx.fracao_saturada(saturado.astype(np.complex64)) > 0.01
    )
    with pytest.raises(ValueError, match="fundo de escala"):
        canal.quantizar_8_bits(x, 1.0)
    with pytest.raises(ValueError, match="nulo"):
        canal.quantizar_8_bits(np.zeros(10, complex), -10.0)


def test_fase_do_tom_mede_a_frequencia_e_a_variacao_de_wiener() -> None:
    assert fase.fase_do_tom(_tom(largura_hz=0.0), FS).freq_hz == pytest.approx(F_TOM, abs=0.5)
    tom = fase.fase_do_tom(_tom(), FS)
    assert tom.saltos == 0 and tom.validas.mean() > 0.99
    for atraso in (ATRASO, 400, 2000):  # atrasos curtos: o filtro de 50 kHz corta parte do Wiener
        v = fase.variacao_de_fase_rad(tom, atraso)
        assert v == pytest.approx(_esperado(LARGURA_HZ, atraso), rel=0.1)
        assert fase.largura_equivalente_hz(v, atraso, FS) == pytest.approx(LARGURA_HZ, rel=0.2)


def test_offset_de_cada_trecho_sai_da_conta() -> None:
    """Uma deriva forte de frequência (o RX estima o offset em cada quadro) não conta como ruído."""
    fraco = 5.0  # perto do tom real: sem tirar o offset de cada trecho, a deriva somaria 45%
    tom = fase.fase_do_tom(_tom(largura_hz=fraco, deriva_hz_por_s=2000.0), FS)
    assert fase.variacao_de_fase_rad(tom, ATRASO) == pytest.approx(
        _esperado(fraco, ATRASO), rel=0.1
    )


def test_saltos_de_emenda_ficam_fora_da_conta() -> None:
    x = _tom()
    for k in range(1, 11):  # 10 emendas com salto de fase, como nas leituras síncronas (A17)
        x[k * N // 11 :] *= np.exp(1.5j)  # o filtro espalha o salto por dezenas de amostras
    tom = fase.fase_do_tom(x, FS)
    assert tom.saltos == 10
    assert fase.variacao_de_fase_rad(tom, ATRASO) == pytest.approx(
        _esperado(LARGURA_HZ, ATRASO), rel=0.1
    )


def test_espectro_do_ruido_de_fase_em_dbc_por_hz() -> None:
    largura = 100.0
    snr_db = 30.0
    l_f = fase.ruido_de_fase_dbc_hz(_tom(largura, snr_db), FS, (1e3, 300e3))
    # Wiener: L(f) = Δν / (2π f²) longe da portadora; ruído branco: σ²/taxa relativo ao tom
    assert l_f[1e3] == pytest.approx(10 * np.log10(largura / (2 * np.pi * 1e3**2)), abs=1.0)
    branco = 10 ** (-snr_db / 10) / FS
    wiener = largura / (2 * np.pi * 300e3**2)
    assert l_f[300e3] == pytest.approx(10 * np.log10(branco + wiener), abs=0.5)
    with pytest.raises(ValueError, match="afastamento"):
        fase.ruido_de_fase_dbc_hz(_tom(), FS, (2e6,))


def test_entradas_invalidas() -> None:
    with pytest.raises(ValueError, match="curta"):
        fase.fase_do_tom(np.ones(100, complex), FS)
    with pytest.raises(ValueError, match="banda"):
        fase.fase_do_tom(_tom(), FS, banda_hz=2e6)
    tom = fase.fase_do_tom(_tom(), FS)
    with pytest.raises(ValueError, match="atraso"):
        fase.variacao_de_fase_rad(tom, 0)
    sem_trecho = fase.FaseDoTom(tom.fase, np.zeros_like(tom.validas), tom.freq_hz, 0, FS)
    with pytest.raises(ValueError, match="nenhum trecho"):
        fase.variacao_de_fase_rad(sem_trecho, ATRASO)


def test_parte_do_ruido_branco_na_variacao_medida() -> None:
    """Só ruído branco: a variação medida é a prevista pelo piso e pelo filtro, em todo atraso."""
    snr_db = 20.0
    piso = -snr_db - 10 * np.log10(FS)
    tom = fase.fase_do_tom(_tom(largura_hz=0.0, snr_db=snr_db), FS)
    for atraso in (3, 6, ATRASO, 400):
        prevista = fase.variacao_do_ruido_branco_rad(piso, atraso, FS)
        assert fase.variacao_de_fase_rad(tom, atraso) == pytest.approx(prevista, rel=0.05)
    # ruído de fase fraco e ruído branco do mesmo tamanho (como no tom real): o desconto
    # devolve o ruído de fase
    fraco = 2.0
    tom = fase.fase_do_tom(_tom(largura_hz=fraco, snr_db=snr_db), FS)
    medida = fase.variacao_de_fase_rad(tom, ATRASO)
    branco = fase.variacao_do_ruido_branco_rad(piso, ATRASO, FS)
    assert medida > 1.2 * _esperado(fraco, ATRASO)
    assert fase.descontar(medida, branco) == pytest.approx(_esperado(fraco, ATRASO), rel=0.1)
    assert fase.descontar(0.01, 0.02) == 0.0
    with pytest.raises(ValueError, match="inválidos"):
        fase.variacao_do_ruido_branco_rad(piso, 0, FS)


def test_trajetoria_medida_sem_saltos_e_com_o_tamanho_pedido() -> None:
    x = _tom()
    for k in range(1, 6):
        x[k * N // 6 :] *= np.exp(1.5j)
    tom = fase.fase_do_tom(x, FS)
    ph = fase.trajetoria(tom, 3 * N)
    assert len(ph) == 3 * N
    assert np.max(np.abs(np.diff(ph))) < 0.05  # sem os saltos de 1,5 rad e sem degrau nas junções
    variacao = ph[ATRASO:] - ph[:-ATRASO]
    assert np.std(variacao) == pytest.approx(_esperado(LARGURA_HZ, ATRASO), rel=0.15)
    with pytest.raises(ValueError, match="tamanho"):
        fase.trajetoria(tom, 0)
    sem_trecho = fase.FaseDoTom(tom.fase, np.zeros_like(tom.validas), tom.freq_hz, 0, FS)
    with pytest.raises(ValueError, match="nenhum trecho"):
        fase.trajetoria(sem_trecho, 10)


def _rodar_medir(captura: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (só o script do projeto, com a gravação do teste)
        [sys.executable, str(config.RAIZ / "scripts" / "medir_ruido_de_fase.py"), str(captura)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=config.RAIZ,
        env={**os.environ, "PYTHONPATH": str(config.RAIZ), "PYTHONIOENCODING": "utf-8"},
    )


def test_script_de_bancada_mede_o_tom_e_compara_com_a_tolerancia(tmp_path: Path) -> None:
    bom = tmp_path / "tom_bom.npy"
    np.save(bom, _tom(largura_hz=1.0, snr_db=30.0).astype(np.complex64))
    r = _rodar_medir(bom)
    assert r.returncode == 0, r.stderr
    registro = json.loads((tmp_path / "tom_bom_ruido_de_fase.json").read_text(encoding="utf-8"))
    assert registro["taxa_sps"] == FS and registro["saltos_de_emenda"] == 0
    assert {v["situacao"] for v in registro["perfis"].values()} == {"ok"}
    assert registro["perfis"]["prova-b"]["atraso_amostras"] == ATRASO
    assert registro["perfis"]["prova-a-8psk"]["atraso_amostras"] == 800  # coerente: 0,39 ms
    # ruído de fase forte demais para a prova B: o script avisa
    ruim = tmp_path / "tom_ruim.npy"
    np.save(ruim, _tom(largura_hz=600.0, snr_db=30.0).astype(np.complex64))
    assert _rodar_medir(ruim).returncode == 0
    registro = json.loads((tmp_path / "tom_ruim_ruido_de_fase.json").read_text(encoding="utf-8"))
    assert registro["perfis"]["prova-b"]["situacao"] == "ATENÇÃO"
    assert registro["perfis"]["prova-a-8psk"]["situacao"] == "ATENÇÃO"
    assert registro["perfis"]["prova-a"]["situacao"] == "ok"  # a DQPSK aguenta 1 kHz
    # tom fraco: o ruído branco da gravação esconde o que se quer medir
    fraco = tmp_path / "tom_fraco.npy"
    np.save(fraco, _tom(largura_hz=1.0, snr_db=-5.0).astype(np.complex64))
    assert _rodar_medir(fraco).returncode == 0
    registro = json.loads((tmp_path / "tom_fraco_ruido_de_fase.json").read_text(encoding="utf-8"))
    assert registro["perfis"]["prova-a"]["situacao"].startswith("inconclusivo")


def test_saltos_achados_tambem_com_filtro_estreito() -> None:
    """Com o filtro de 2 kHz um salto se espalha por centenas de amostras: busca em banda larga."""
    x = _tom(largura_hz=1.0)
    for k in range(1, 11):
        x[k * N // 11 :] *= np.exp(0.5j)  # os que escapavam nos tons reais eram os menores
    tom = fase.fase_do_tom(x, FS, banda_hz=2e3)
    assert tom.saltos == 10
    ph = fase.trajetoria(tom, N)
    t = np.arange(1182)  # um quadro de 8-PSK: nenhum trecho com resto de salto
    desvios = [
        np.std(ph[k : k + 1182] - np.polyval(np.polyfit(t, ph[k : k + 1182], 1), t))
        for k in range(0, N - 1182, 1182)
    ]
    assert max(desvios) < 0.06  # o Wiener de 1 Hz chega a 0,04; um salto esquecido, a 0,2


def test_repeticao_espelhada_mantem_a_frequencia_continua() -> None:
    """Frequência que anda devagar (caminhada aleatória): a emenda das cópias não dá degrau."""
    rng = np.random.default_rng(9)
    n = 2**17
    frequencia = np.cumsum(rng.standard_normal(n)) * 1e-6  # rad por amostra
    tom = fase.FaseDoTom(np.cumsum(frequencia), np.ones(n, dtype=bool), 0.0, 0, FS)
    ph = fase.trajetoria(tom, 3 * n)
    assert len(ph) == 3 * n
    degraus = np.abs(np.diff(np.diff(ph)))
    assert degraus.max() < 20 * np.median(degraus)
