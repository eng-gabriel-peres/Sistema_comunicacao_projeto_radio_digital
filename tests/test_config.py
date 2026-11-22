"""Testes da configuração (sdrlink.config) e do uso do valor padrão."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sdrlink import config, transmissor
from sdrlink.fm import erro_absoluto_ppm
from sdrlink.hw.rtl_rx import ConfigRtl
from sdrlink.modem import ConfigModem
from sdrlink.transmissor import ConfigTransmissor


def test_correcao_adotada_e_84_ppm() -> None:
    assert config.ler_correcao_ppm(config.ARQUIVO_RTL) == 84
    assert config.correcao_rtl_ppm_padrao() == 84


def test_captura_sem_correcao_explicita_usa_a_configuracao() -> None:
    assert ConfigRtl(915e6, 2.048e6, 20.0).correcao_ppm == 84
    assert ConfigRtl(915e6, 2.048e6, 20.0, 0).correcao_ppm == 0


@pytest.mark.parametrize(
    ("conteudo", "mensagem"),
    [
        ("[calibracao]\n", "ausente"),
        ("[calibracao]\ncorrecao_ppm = 77.5\n", "não inteiro"),
        ("[calibracao]\ncorrecao_ppm = true\n", "não inteiro"),
        ("[calibracao]\ncorrecao_ppm = 500\n", "fora"),
    ],
)
def test_configuracao_invalida_e_rejeitada(tmp_path: Path, conteudo: str, mensagem: str) -> None:
    arquivo = tmp_path / "rtl.toml"
    arquivo.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ValueError, match=mensagem):
        config.ler_correcao_ppm(arquivo)


def test_arquivo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        config.ler_correcao_ppm(tmp_path / "nao_existe.toml")


def test_erro_absoluto_desconta_a_correcao_aplicada() -> None:
    # medido +8,7 ppm com 77 aplicados -> o RTL sozinho erra -68,3 ppm
    assert erro_absoluto_ppm(8.7, 77) == pytest.approx(-68.3)
    assert erro_absoluto_ppm(-68.3, 0) == pytest.approx(-68.3)
    with pytest.raises(ValueError, match="plausível"):
        erro_absoluto_ppm(0.0, 500)


# ---- perfis de enlace (configs/perfis.toml) ----

PERFIL_MINIMO = '[p]\nmodulacao = "dbpsk"\npulso = "rrc"\nsps = 8\n'


def _arquivo(tmp_path: Path, conteudo: str) -> Path:
    arquivo = tmp_path / "perfis.toml"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def test_perfis_do_projeto_sao_validos_e_a_prova_a_cabe_em_1_mhz() -> None:
    perfis = config.ler_perfis(config.ARQUIVO_PERFIS)
    assert {"prova-a", "prova-a-dbpsk", "dbpsk-256k", "gfsk-128k", "ook-128k"} <= set(perfis)
    for nome, modulacao, bits_por_simbolo in (
        ("prova-a", "dqpsk", 2),
        ("prova-a-dbpsk", "dbpsk", 1),
    ):
        a = perfis[nome]
        assert (a.modulacao, a.pulso, a.sps, a.beta) == (modulacao, "rrc", 3, 0.25)
        assert a.taxa_bits == pytest.approx(bits_por_simbolo * 2.048e6 / 3)
        baixo, alto = ConfigTransmissor(a.modem(), a.taxa_sps, a.deslocamento_hz).banda_99_hz()
        assert a.modem() == ConfigModem(modulacao, "rrc", 3, beta=0.25)  # o beta chega ao modem
        assert alto - baixo == pytest.approx(749e3, abs=5e3)  # com beta = 0,35 seriam 792 kHz
        assert baixo > 25e3  # longe do DC do RTL
        assert alto < 850e3  # dentro da faixa plana do RTL (±1 dB até 850 kHz)
    assert perfis["dbpsk-256k"].taxa_bits == 256e3


def test_linha_de_comando_substitui_so_o_campo_dado(tmp_path: Path) -> None:
    arquivo = _arquivo(tmp_path, PERFIL_MINIMO + "deslocamento_hz = 300000\n")
    base = config.montar_perfil("p", {"modulacao": None, "beta": None}, arquivo)
    assert base == config.perfil("p", arquivo)
    assert base.deslocamento_hz == 300e3  # int do TOML vira float
    mudado = config.montar_perfil("p", {"taxa_bits": 512e3, "beta": 0.2}, arquivo)
    assert (mudado.sps, mudado.beta, mudado.deslocamento_hz) == (4, 0.2, 300e3)
    assert mudado.nome == "p (alterado)"


def test_sem_perfil_exige_modulacao_pulso_e_taxa(tmp_path: Path) -> None:
    solto = config.montar_perfil(
        None, {"modulacao": "fsk", "pulso": "gaussiano", "taxa_bits": 128e3}
    )
    assert (solto.nome, solto.sps, solto.lo_hz, solto.deslocamento_hz) == (
        "linha de comando",
        16,
        919.5e6,
        250e3,
    )
    with pytest.raises(ValueError, match="informe"):
        config.montar_perfil(None, {"modulacao": "fsk", "taxa_bits": 128e3})
    with pytest.raises(ValueError, match="informe"):
        config.montar_perfil(None, {"modulacao": "fsk", "pulso": "gaussiano"})


@pytest.mark.parametrize(
    ("conteudo", "mensagem"),
    [
        ("", "um ou mais perfis"),
        ("x = 1\n" + PERFIL_MINIMO, "um ou mais perfis"),
        (PERFIL_MINIMO + "potencia = 3\n", "desconhecido"),
        (PERFIL_MINIMO.replace("sps = 8", "sps = 8.0"), "não é int"),
        (PERFIL_MINIMO + "beta = true\n", "não é float"),
        (PERFIL_MINIMO + 'lo_hz = "919.5e6"\n', "não é float"),
        (PERFIL_MINIMO + "lo_hz = 930e6\n", "fora de 915 a 928"),
        (PERFIL_MINIMO + "deslocamento_hz = 1.1e6\n", "deslocamento"),
        (PERFIL_MINIMO.replace('"rrc"', '"gaussiano"'), "não serve"),
    ],
)
def test_perfil_invalido_e_rejeitado(tmp_path: Path, conteudo: str, mensagem: str) -> None:
    with pytest.raises(ValueError, match=mensagem):
        config.ler_perfis(_arquivo(tmp_path, conteudo))


def test_erros_de_montagem(tmp_path: Path) -> None:
    arquivo = _arquivo(tmp_path, PERFIL_MINIMO)
    with pytest.raises(ValueError, match="disponíveis: p"):
        config.perfil("nao-existe", arquivo)
    with pytest.raises(ValueError, match="precisa ser inteiro"):
        config.montar_perfil("p", {"taxa_bits": 300e3}, arquivo)
    with pytest.raises(ValueError, match="desconhecidos"):
        config.montar_perfil("p", {"potencia": 3.0}, arquivo)


def _rodar(script: str, *argumentos: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 (só os scripts do projeto, com argumentos do teste)
        [sys.executable, str(config.RAIZ / "scripts" / script), *argumentos],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        cwd=config.RAIZ,
        env={**os.environ, "PYTHONPATH": str(config.RAIZ), "PYTHONIOENCODING": "utf-8"},
    )


def test_tx_e_rx_com_o_mesmo_perfil_fecham_o_enlace(tmp_path: Path) -> None:
    payloads = tmp_path / "payloads.bin"
    payloads.write_bytes(bytes(range(128)) * 40)
    sinal = tmp_path / "prova_a.npy"
    tx = _rodar(
        "transmitir.py",
        str(payloads),
        "--perfil",
        "prova-a",
        "--duracao-s",
        "0.04",
        "--simular",
        str(sinal),
        "--pasta",
        str(tmp_path),
    )
    assert tx.returncode == 0, tx.stderr
    rx = _rodar("receber.py", str(sinal), "--perfil", "prova-a")
    assert rx.returncode == 0, rx.stderr
    log_tx = next(tmp_path.glob("tx_*.txt")).read_text(encoding="utf-8")
    saida = (tmp_path / "prova_a_saida.txt").read_text(encoding="utf-8")
    assert saida == log_tx and saida.count("\n") >= 20
    registro = json.loads((tmp_path / "prova_a_rx.json").read_text(encoding="utf-8"))
    assert registro["perfil"]["nome"] == "prova-a" and registro["perfil"]["sps"] == 3


def test_scripts_recusam_perfil_inexistente_ou_parametros_faltando(tmp_path: Path) -> None:
    sem = _rodar("receber.py", str(tmp_path / "x.npy"), "--perfil", "nao-existe")
    assert sem.returncode == 2 and "disponíveis" in sem.stderr
    falta = _rodar("transmitir.py", str(tmp_path / "x.bin"), "--modulacao", "dbpsk")
    assert falta.returncode == 2 and "informe" in falta.stderr


def test_perfil_com_fec(tmp_path: Path) -> None:
    arquivo = _arquivo(tmp_path, PERFIL_MINIMO + "fec = true\n")
    assert config.perfil("p", arquivo).fec is True
    assert config.montar_perfil("p", {"fec": False}, arquivo).fec is False  # --no-fec
    assert (
        config.montar_perfil(None, {"modulacao": "dbpsk", "pulso": "rrc", "taxa_bits": 256e3}).fec
        is False
    )
    with pytest.raises(ValueError, match="não é bool"):
        config.ler_perfis(_arquivo(tmp_path, PERFIL_MINIMO + "fec = 1\n"))


def test_tx_e_rx_com_fec_pela_linha_de_comando(tmp_path: Path) -> None:
    payloads = tmp_path / "payloads.bin"
    payloads.write_bytes(bytes(range(128)) * 30)
    sinal = tmp_path / "fec.npy"
    comum = ("--perfil", "dbpsk-256k", "--fec")
    tx = _rodar(
        "transmitir.py",
        str(payloads),
        *comum,
        "--duracao-s",
        "0.1",
        "--simular",
        str(sinal),
        "--pasta",
        str(tmp_path),
    )
    assert tx.returncode == 0, tx.stderr
    rx = _rodar("receber.py", str(sinal), *comum)
    assert rx.returncode == 0, rx.stderr
    log_tx = next(tmp_path.glob("tx_*.txt")).read_text(encoding="utf-8")
    assert (tmp_path / "fec_saida.txt").read_text(encoding="utf-8") == log_tx
    assert log_tx.count("\n") >= 10
    registro = json.loads((tmp_path / "fec_rx.json").read_text(encoding="utf-8"))
    assert (
        registro["perfil"]["fec"] is True and registro["perfil"]["nome"] == "dbpsk-256k (alterado)"
    )


def test_perfil_dqpsk_converte_a_taxa_de_bits_em_simbolos() -> None:
    perfil = config.montar_perfil(
        None, {"modulacao": "dqpsk", "pulso": "rrc", "taxa_bits": 2 * 2.048e6 / 3}
    )
    assert perfil.sps == 3 and perfil.taxa_bits == pytest.approx(2 * 2.048e6 / 3)
    trocado = config.montar_perfil("prova-a-dbpsk", {"modulacao": "dqpsk"})  # mesmo sps
    assert trocado.sps == 3 and trocado.taxa_bits == pytest.approx(
        2 * config.perfil("prova-a-dbpsk").taxa_bits
    )


@pytest.mark.parametrize(
    ("nome", "folga_minima"),
    # folgas com o quadro v3 (1130 tempos de bit; 2214 com FEC): 17,2%, 14,8% e 4,3%
    [("prova-b", 0.17), ("prova-b-sem-fec", 0.14), ("prova-b-limite", 0.04)],
)
def test_perfis_da_prova_b_passam_dos_10_kbps_com_per_de_1_pct(
    nome: str, folga_minima: float
) -> None:
    perfil = config.perfil(nome)
    periodo_s = transmissor.amostras_por_quadro(perfil.modem(), fec=perfil.fec) / perfil.taxa_sps
    goodput_com_per_1pct = 1024 / periodo_s * 0.99
    assert goodput_com_per_1pct > 10e3 * (1 + folga_minima)
    assert 500 * periodo_s < 50  # os 500 pacotes cabem em menos de 50 s
