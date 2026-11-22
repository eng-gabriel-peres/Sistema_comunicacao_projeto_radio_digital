"""Testes da análise de bancada: leitura dos registros, perda do enlace e tabela."""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from sdrlink import bancada, config, teoria


def _rx(  # noqa: PLR0913 (um parâmetro por campo do registro que o teste varia)
    pasta: Path,
    nome: str,
    *,
    modulacao: str = "dbpsk",
    fec: bool = False,
    ebn0: float | None = 9.0,
    ber: float = 1e-3,
    bits: int = 100_000,
    sps: int = 8,
) -> Path:
    """Um <nome>_rx.json no formato do scripts/receber.py."""
    medidas: dict[str, object] = {"medido": False}
    if ebn0 is not None:
        medidas = {
            "medido": True,
            "ebn0_estimado_db": ebn0,
            "banda_99_khz": 300.0,
            "banda_99_confiavel": True,
        }
    registro = {
        "captura": f"{nome}.npy",
        "perfil": {
            "nome": f"p-{modulacao}",
            "modulacao": modulacao,
            "fec": fec,
            "taxa_sps": 2.048e6,
            "sps": sps,
        },
        "medidas_da_captura": medidas,
        "ber": {"ber": ber, "bits_comparados": bits},
        "offset_residual_mediano_hz": -12.5,
        "gravacao": {"encontrada": True, "metadados": {"ganho_db": 30.0}},
    }
    caminho = pasta / f"{nome}{bancada.SUFIXO_RX}"
    caminho.write_text(json.dumps(registro), encoding="utf-8")
    return caminho


def _avaliacao(pasta: Path, nome: str, per: float = 0.02) -> None:
    dados = {"transmitidos": 500, "per": per, "goodput_bps": 120e3}
    (pasta / f"{nome}{bancada.SUFIXO_AVALIACAO}").write_text(json.dumps(dados), encoding="utf-8")


def test_ler_ponto_junta_rx_e_avaliacao(tmp_path: Path) -> None:
    _avaliacao(tmp_path, "c1")
    p = bancada.ler_ponto(_rx(tmp_path, "c1"))
    assert (p.captura, p.perfil, p.modulacao, p.fec) == ("c1.npy", "p-dbpsk", "dbpsk", False)
    assert p.taxa_bits == pytest.approx(256e3)
    assert (p.ganho_rx_db, p.ebn0_db, p.ber, p.bits_comparados) == (30.0, 9.0, 1e-3, 100_000)
    assert (p.per, p.goodput_bps, p.transmitidos) == (0.02, 120e3, 500)
    assert (p.banda_khz, p.banda_confiavel, p.offset_hz) == (300.0, True, -12.5)


def test_ler_ponto_sem_avaliacao_sem_medidas_e_ber_nan(tmp_path: Path) -> None:
    p = bancada.ler_ponto(_rx(tmp_path, "c1", ebn0=None, ber=math.nan, bits=0))
    assert p.per is None and p.goodput_bps is None and p.transmitidos is None
    assert p.ebn0_db is None and p.banda_khz is None and p.banda_confiavel is None
    assert p.ber is None  # NaN do medir_ber sem bits comparados não vira número
    assert bancada.perda_db(p) is None


def test_taxa_de_bits_da_dqpsk_conta_2_bits_por_simbolo(tmp_path: Path) -> None:
    p = bancada.ler_ponto(_rx(tmp_path, "c1", modulacao="dqpsk", sps=3))
    assert p.taxa_bits == pytest.approx(2 * 2.048e6 / 3)


def test_ler_ponto_recusa_outro_arquivo(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="receber"):
        bancada.ler_ponto(tmp_path / "c1_saida_avaliacao.json")


def test_ler_sessao_em_ordem_de_captura(tmp_path: Path) -> None:
    for nome in ("c2", "c1", "c3"):
        _rx(tmp_path, nome)
    _avaliacao(tmp_path, "c1")  # não é registro do RX: não vira ponto
    assert [p.captura for p in bancada.ler_sessao(tmp_path)] == ["c1.npy", "c2.npy", "c3.npy"]


@pytest.mark.parametrize("modulacao", sorted(teoria.BER_TEORICA))
def test_ebn0_teorico_inverte_a_curva(modulacao: str) -> None:
    for ebn0 in (6.0, 9.5, 12.0):
        ber = float(teoria.BER_TEORICA[modulacao](ebn0))
        assert bancada.ebn0_teorico_db(modulacao, ber) == pytest.approx(ebn0, abs=0.02)


def test_ebn0_teorico_fora_da_curva() -> None:
    assert bancada.ebn0_teorico_db("dbpsk", 0.0) is None
    assert bancada.ebn0_teorico_db("dbpsk", 0.5) is None
    assert bancada.ebn0_teorico_db("dbpsk", 1e-300) is None  # abaixo do fim da grade
    assert bancada.ebn0_teorico_db("qam64", 1e-3) is None


def test_perda_e_a_distancia_horizontal_ate_a_teoria(tmp_path: Path) -> None:
    teorico = 10 * np.log10(-np.log(2e-3))  # DBPSK: BER = exp(-Eb/N0)/2
    p = bancada.ler_ponto(_rx(tmp_path, "c1", ebn0=float(teorico) + 1.5))
    assert bancada.perda_db(p) == pytest.approx(1.5, abs=0.02)
    # FEC: a teoria sem código não vale; poucos bits: BER sem confiança
    assert bancada.perda_db(bancada.ler_ponto(_rx(tmp_path, "c2", fec=True))) is None
    poucos = bancada.ler_ponto(_rx(tmp_path, "c3", bits=bancada.BITS_MIN_BER - 1))
    assert bancada.perda_db(poucos) is None


def test_tabela_com_e_sem_dados(tmp_path: Path) -> None:
    _avaliacao(tmp_path, "c1", per=0.0123)
    _rx(tmp_path, "c1")
    _rx(tmp_path, "c2", ebn0=None, ber=math.nan, bits=0)
    linhas = bancada.tabela_markdown(bancada.ler_sessao(tmp_path)).splitlines()
    assert len(linhas) == 4
    assert "| 1.23% |" in linhas[2] and "| 120.0 |" in linhas[2] and "| 30.0 |" in linhas[2]
    assert "sem dado%" not in linhas[3] and linhas[3].count("sem dado") == 6


def test_banda_nao_confiavel_aparece_na_tabela(tmp_path: Path) -> None:
    caminho = _rx(tmp_path, "c1")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    dados["medidas_da_captura"]["banda_99_confiavel"] = False
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    assert "300.0 (não confiável)" in bancada.tabela_markdown(bancada.ler_sessao(tmp_path))


def _analisar(pasta: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (só o script do projeto, com a pasta do teste)
        [sys.executable, str(config.RAIZ / "scripts" / "analisar_bancada.py"), str(pasta)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=config.RAIZ,
        env={**os.environ, "PYTHONPATH": str(config.RAIZ), "PYTHONIOENCODING": "utf-8"},
    )


def test_script_grava_tabela_e_figura(tmp_path: Path) -> None:
    _avaliacao(tmp_path, "c1")
    _rx(tmp_path, "c1")
    r = _analisar(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "1 pontos" in r.stdout
    assert "| c1.npy |" in (tmp_path / "analise_bancada.md").read_text(encoding="utf-8")
    assert (tmp_path / "analise_bancada.png").stat().st_size > 0
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    r = _analisar(vazia)
    assert r.returncode != 0 and "nenhum registro" in r.stderr
