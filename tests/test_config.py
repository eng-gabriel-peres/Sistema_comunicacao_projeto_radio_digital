"""Testes da configuração (sdrlink.config) e do uso do valor padrão."""

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from sdrlink import config, receptor, transmissor
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
    payloads.write_bytes(bytes(range(128)) * 100)  # mais do que cabe na janela
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
    # o TX aplicou a emenda do perfil: na janela de 0,04 s cabem os quadros do período curto
    perfil = config.perfil("prova-a")
    periodo = transmissor.amostras_por_quadro(perfil.modem(), emendar_caudas=True)
    assert log_tx.count("\n") == -(-int(0.04 * perfil.taxa_sps) // periodo)


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


def test_emenda_das_caudas_so_nos_perfis_da_prova_a(tmp_path: Path) -> None:
    perfis = config.ler_perfis(config.ARQUIVO_PERFIS)
    for nome, perfil in perfis.items():
        assert perfil.emendar_caudas is nome.startswith("prova-a"), nome  # a B vale sensibilidade
    arquivo = _arquivo(tmp_path, PERFIL_MINIMO + "emendar_caudas = true\n")
    assert config.perfil("p", arquivo).emendar_caudas is True
    assert config.montar_perfil("p", {"emendar_caudas": False}, arquivo).emendar_caudas is False
    with pytest.raises(ValueError, match="não é bool"):
        config.ler_perfis(_arquivo(tmp_path, PERFIL_MINIMO + "emendar_caudas = 1\n"))


def test_transmitir_avisa_quando_faltam_payloads(tmp_path: Path) -> None:
    payloads = tmp_path / "poucos.bin"
    payloads.write_bytes(bytes(128) * 5)  # em 0,04 s cabem 48 quadros do prova-a
    tx = _rodar(
        "transmitir.py",
        str(payloads),
        "--perfil",
        "prova-a",
        "--duracao-s",
        "0.04",
        "--simular",
        str(tmp_path / "x.npy"),
        "--pasta",
        str(tmp_path),
    )
    assert tx.returncode == 0, tx.stderr
    assert "AVISO" in tx.stdout and "5 payloads" in tx.stdout and "cabem 48" in tx.stdout
    registro = json.loads(next(tmp_path.glob("tx_*.json")).read_text(encoding="utf-8"))
    assert (
        registro["payloads_suficientes"] is False and registro["pacotes_que_cabem_na_janela"] == 48
    )


@pytest.mark.parametrize("perfil", ["prova-a", "prova-b"])
def test_receber_mede_ber_banda_e_ebn0_com_os_perfis_da_prova(tmp_path: Path, perfil: str) -> None:
    # de ponta a ponta: payloads conhecidos, TX do perfil, ruído antes e depois, receber --ber;
    # cobre o período com emenda (prova-a, DQPSK) e com FEC (prova-b) na BER e na medida
    escolhido = config.perfil(perfil)
    payloads = tmp_path / "conhecidos.bin"
    gerado = _rodar("gerar_payloads.py", "--conhecidos", "200", str(payloads))
    assert gerado.returncode == 0, gerado.stderr
    sinal = tmp_path / "tx.npy"
    duracao = "0.06" if perfil == "prova-a" else "0.3"
    tx = _rodar(
        "transmitir.py",
        str(payloads),
        "--perfil",
        perfil,
        "--duracao-s",
        duracao,
        "--simular",
        str(sinal),
        "--pasta",
        str(tmp_path),
    )
    assert tx.returncode == 0, tx.stderr
    s = np.load(sinal).astype(complex)
    s = s[: np.flatnonzero(s)[-1] + 1]
    ebn0_por_bit = 14.0
    amostras_por_bit = escolhido.taxa_sps / escolhido.taxa_bits
    n0 = np.mean(np.abs(s) ** 2) * amostras_por_bit / 10 ** (ebn0_por_bit / 10)
    margem = np.zeros(int(0.3 * escolhido.taxa_sps), dtype=complex)
    x = np.concatenate([margem, s, margem])
    rng = np.random.default_rng(5)
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    captura = tmp_path / "cap.npy"
    np.save(captura, x.astype(np.complex64))
    rx = _rodar("receber.py", str(captura), "--perfil", perfil, "--ber")
    assert rx.returncode == 0, rx.stderr
    registro = json.loads((tmp_path / "cap_rx.json").read_text(encoding="utf-8"))
    enviados = next(tmp_path.glob("tx_*.txt")).read_text(encoding="utf-8").count("\n")
    assert registro["ber"]["quadros_comparados"] == enviados
    assert registro["ber"]["bits_errados"] == 0
    medidas = registro["medidas_da_captura"]
    assert medidas["ebn0_estimado_db"] == pytest.approx(ebn0_por_bit, abs=0.6)  # por bit no ar
    assert "snr_na_captura_db" in medidas
    if perfil == "prova-a":  # na B, a 14 dB por bit, a SNR na captura fica em -5,0 dB: no limite
        assert medidas["banda_99_confiavel"] is True
    if escolhido.fec:  # por bit útil: o código de taxa 1/2 com cauda soma cerca de 3 dB
        assert medidas["ebn0_por_bit_util_db"] == pytest.approx(ebn0_por_bit + 3.03, abs=0.6)
    else:
        assert "ebn0_por_bit_util_db" not in medidas


def test_receber_junta_os_metadados_da_gravacao_e_avisa_divergencias(tmp_path: Path) -> None:
    # o ganho do RX vem do JSON do gravar_iq.py (seção 7 do enunciado); centro errado vira aviso
    payloads = tmp_path / "p.bin"
    payloads.write_bytes(bytes(128) * 60)
    captura = tmp_path / "cap.npy"
    tx = _rodar(
        "transmitir.py",
        str(payloads),
        "--perfil",
        "prova-a",
        "--duracao-s",
        "0.02",
        "--simular",
        str(captura),
        "--pasta",
        str(tmp_path),
    )
    assert tx.returncode == 0, tx.stderr
    metadados = {
        "centro_hz": 919.6e6,
        "taxa_sps": 2.048e6,
        "ganho_db": 30.0,
        "correcao_ppm": 84,
        "fracao_saturada": 0.0,
        "nivel_eficaz_dbfs": -38.0,
    }
    captura.with_suffix(".json").write_text(json.dumps(metadados), encoding="utf-8")
    rx = _rodar("receber.py", str(captura), "--perfil", "prova-a")
    assert rx.returncode == 0, rx.stderr
    assert "AVISO: gravada com centro em 919.600000 MHz" in rx.stdout
    assert "AVISO: nível de -38.0 dBFS" in rx.stdout
    registro = json.loads((tmp_path / "cap_rx.json").read_text(encoding="utf-8"))
    assert registro["gravacao"]["metadados"]["ganho_db"] == 30.0
    assert len(registro["gravacao"]["avisos"]) == 2
    captura.with_suffix(".json").unlink()
    sem = _rodar("receber.py", str(captura), "--perfil", "prova-a")
    assert sem.returncode == 0, sem.stderr
    registro = json.loads((tmp_path / "cap_rx.json").read_text(encoding="utf-8"))
    assert registro["gravacao"]["encontrada"] is False


def test_perfil_experimental_a_2_4_ms_por_segundo_cabe_em_1_mhz() -> None:
    perfil = config.perfil("prova-a-24")
    assert perfil.taxa_bits == pytest.approx(1.6e6)
    tx = ConfigTransmissor(perfil.modem(), perfil.taxa_sps, perfil.deslocamento_hz)
    baixo, alto = tx.banda_99_hz()
    assert alto - baixo < 0.86e6  # 15% de folga sobre 1 MHz
    assert baixo > 25e3  # longe do DC
    assert alto < 0.8 * perfil.taxa_sps / 2  # mesma fração da faixa útil do perfil a 2,048 MS/s


def test_limiar_de_deteccao_vem_do_perfil(tmp_path: Path) -> None:
    assert config.LIMIAR_PADRAO == receptor.LIMIAR_PADRAO
    assert config.perfil("prova-b").limiar == 0.4
    assert config.perfil("prova-a").limiar == receptor.LIMIAR_PADRAO
    arquivo = _arquivo(tmp_path, PERFIL_MINIMO + "limiar = 0.45\n")
    assert config.perfil("p", arquivo).limiar == 0.45
    with pytest.raises(ValueError, match="limiar"):
        config.ler_perfis(_arquivo(tmp_path, PERFIL_MINIMO + "limiar = 1.5\n"))
