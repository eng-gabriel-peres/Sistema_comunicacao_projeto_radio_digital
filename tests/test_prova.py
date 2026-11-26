"""Testes do dia da prova: arquivo qualquer em pacotes, remontagem, resumo do RX e alcance."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from sdrlink import config, prova
from sdrlink.quadro import Pacote


def test_fatiar_completa_o_ultimo_com_zeros() -> None:
    dados = bytes(range(256)) + b"abc"
    payloads = prova.fatiar(dados)
    assert [len(p) for p in payloads] == [128, 128, 128]
    assert payloads[2] == b"abc" + bytes(125)
    assert b"".join(payloads)[: len(dados)] == dados
    assert prova.fatiar(bytes(256)) == [bytes(128), bytes(128)]  # múltiplo: sem enchimento
    with pytest.raises(ValueError, match="vazio"):
        prova.fatiar(b"")


def test_ler_arquivo_qualquer_e_txt_estrito(tmp_path: Path) -> None:
    cifrado = tmp_path / "prova.enc"
    cifrado.write_bytes(bytes(range(200)))
    payloads, aviso = prova.ler_arquivo(cifrado)
    assert len(payloads) == 2 and aviso is not None and "56 bytes zero" in aviso
    exato = tmp_path / "payloads.bin"
    exato.write_bytes(bytes(256))
    assert prova.ler_arquivo(exato) == ([bytes(128), bytes(128)], None)
    texto = tmp_path / "payloads.txt"
    texto.write_text(bytes(range(128)).hex() + "\n", encoding="utf-8")
    assert prova.ler_arquivo(texto) == ([bytes(range(128))], None)
    texto.write_text("abcd\n", encoding="utf-8")
    with pytest.raises(ValueError, match="tamanho"):
        prova.ler_arquivo(texto)


def test_repetir_ate_encher_a_janela() -> None:
    assert prova.repetir_ate([b"a", b"b"], 5) == [b"a", b"b", b"a", b"b", b"a"]
    with pytest.raises(ValueError, match="nada"):
        prova.repetir_ate([], 3)


def test_remontar_na_ordem_com_os_que_faltam() -> None:
    pacotes = [Pacote(2, b"c" * 4), Pacote(0, b"a" * 4), Pacote(0, b"a" * 4)]
    dados, faltando = prova.remontar(pacotes)
    assert dados == b"aaaa" + bytes(4) + b"cccc" and faltando == [1]
    dados, faltando = prova.remontar(pacotes, n_pacotes=4)
    assert len(dados) == 16 and faltando == [1, 3]
    with pytest.raises(ValueError, match="nenhum"):
        prova.remontar([])
    with pytest.raises(ValueError, match="tamanhos"):
        prova.remontar([Pacote(0, b"a"), Pacote(1, b"bb")])


def test_resumo_da_recepcao_sem_o_log_do_tx() -> None:
    sequencias = [5, 6, 8, 9, 9, 12]  # 7, 10 e 11 faltam; 9 repetida
    pacotes = [Pacote(s, bytes(128)) for s in sequencias]
    instantes = [0.1, 0.6, 1.2, 1.4, 1.5, 2.9]
    r = prova.resumo_da_recepcao(pacotes, instantes, janela_s=60.0)
    assert (r.unicos, r.primeira, r.ultima, r.buracos) == (5, 5, 12, 3)
    assert r.per_estimada == pytest.approx(3 / 8)
    assert r.goodput_bps == pytest.approx(5 * 1024 / 60)
    assert r.por_segundo == [2, 3, 1]
    with pytest.raises(ValueError, match="janela"):
        prova.resumo_da_recepcao(pacotes, instantes, 0.0)


def test_alcance_e_criterio_da_prova_b() -> None:
    posicoes = [
        prova.Posicao(40.0, 11_800.0, 0.0, 694, 12.0),
        prova.Posicao(10.0, 11_800.0, 0.0, 694, 30.0),
        prova.Posicao(70.0, 11_000.0, 0.02, 680, 4.0),  # PER acima de 1%
        prova.Posicao(55.0, 9_500.0, 0.0, 560, 6.0),  # goodput abaixo de 10 kbit/s
    ]
    ordenadas, maior = prova.alcance(posicoes)
    assert [p.distancia_m for p in ordenadas] == [10.0, 40.0, 55.0, 70.0]
    assert maior == 40.0
    assert prova.alcance([prova.Posicao(5.0, 1.0, 0.5, 10, None)])[1] is None
    poucos = prova.Posicao(60.0, 11_800.0, 0.0, 400, 8.0)  # goodput e PER bons, só 400 pacotes
    assert not poucos.passou


def test_ocupacao_dos_canais_acha_o_surto() -> None:
    rng = np.random.default_rng(1)
    fs = 2.048e6
    x = rng.standard_normal(2**20) + 1j * rng.standard_normal(2**20)
    t = np.arange(2**20) / fs
    surto = (t > 0.2) & (t < 0.21)  # 10 ms de interferência em +250 kHz
    x[surto] += 30 * np.exp(2j * np.pi * 250e3 * t[surto])
    ocupacao = prova.ocupacao_dos_canais(x, fs, [250e3, 375e3], meia_largura_hz=20e3)
    assert ocupacao[250e3] > ocupacao[375e3] + 15
    with pytest.raises(ValueError, match="fora da faixa"):
        prova.ocupacao_dos_canais(x, fs, [5e6], 20e3)


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


def test_arquivo_cifrado_de_ponta_a_ponta_sem_radio(tmp_path: Path) -> None:
    original = np.random.default_rng(9).integers(0, 256, 128 * 40 + 77).astype(np.uint8).tobytes()
    arquivo = tmp_path / "prova.enc"  # tamanho que não é múltiplo de 128, como um cifrado
    arquivo.write_bytes(original)
    sinal = tmp_path / "prova_a_sim.npy"
    tx = _rodar(
        "transmitir.py", str(arquivo), "--perfil", "prova-a", "--duracao-s", "0.05",
        "--simular", str(sinal), "--pasta", str(tmp_path),
    )  # fmt: skip
    assert tx.returncode == 0, tx.stderr
    assert "77 bytes" not in tx.stdout and "51 bytes zero" in tx.stdout  # 128 - 77 = 51
    rx = _rodar(
        "prova_rx.py", "--prova", "a", "--captura", str(sinal), "--janela-s", "0.05",
        "--log-tx", str(next(tmp_path.glob("tx_*.txt"))), "--pasta", str(tmp_path),
    )  # fmt: skip
    assert rx.returncode == 0, rx.stderr
    remontado = (tmp_path / "prova_a_sim_arquivo.bin").read_bytes()
    assert remontado[: len(original)] == original  # o arquivo volta inteiro
    resumo = json.loads((tmp_path / "prova_a_sim_resumo.json").read_text(encoding="utf-8"))
    assert resumo["per"] == 0.0 and resumo["per_e_goodput"] == "exatos, pelo log do TX"
    assert (tmp_path / "prova_a_sim_relatorio.png").stat().st_size > 0
    assert "RESULTADO" in rx.stdout and "Prova A: PASSA" in rx.stdout
    assert "Recomendação pelo sinal medido:" in rx.stdout


def test_prova_rx_num_terminal_sem_utf8(tmp_path: Path) -> None:
    """Num PowerShell comum o filho escreve em cp1252; o prova_rx tem de ler mesmo assim."""
    arquivo = tmp_path / "p.enc"
    arquivo.write_bytes(bytes(range(256)) * 20)
    sinal = tmp_path / "sim.npy"
    tx = _rodar("transmitir.py", str(arquivo), "--perfil", "prova-a", "--duracao-s", "0.02",
                "--simular", str(sinal), "--pasta", str(tmp_path))  # fmt: skip
    assert tx.returncode == 0, tx.stderr
    ambiente = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    rx = subprocess.run(  # noqa: S603
        [sys.executable, str(config.RAIZ / "scripts" / "prova_rx.py"), "--prova", "a",
         "--captura", str(sinal), "--janela-s", "0.02", "--pasta", str(tmp_path)],
        capture_output=True, check=False, cwd=config.RAIZ,
        env={**ambiente, "PYTHONPATH": str(config.RAIZ), "PYTHONIOENCODING": "cp1252"},
    )  # fmt: skip
    assert rx.returncode == 0, rx.stderr.decode("cp1252", "replace")
    assert b"RESULTADO" in rx.stdout


def test_relatorio_de_alcance_junta_as_posicoes(tmp_path: Path) -> None:
    for d, goodput, per in ((10, 11_800.0, 0.0), (40, 11_700.0, 0.004), (80, 9_000.0, 0.2)):
        resumo = {"prova": "b", "distancia_m": d, "goodput_bps": goodput, "per": per,
                  "pacotes_unicos": 600, "ebn0_db": 20.0 - d / 10}  # fmt: skip
        (tmp_path / f"p{d}_resumo.json").write_text(json.dumps(resumo), encoding="utf-8")
    (tmp_path / "a_resumo.json").write_text(json.dumps({"prova": "a"}), encoding="utf-8")
    r = _rodar("relatorio_alcance.py", str(tmp_path))
    assert r.returncode == 0, r.stderr
    texto = (tmp_path / "alcance.md").read_text(encoding="utf-8")
    assert "Maior distância validada: **40 m**" in texto and texto.count("| sim |") == 2
    assert (tmp_path / "alcance.png").stat().st_size > 0


def test_escolher_canal_evita_o_surto(tmp_path: Path) -> None:
    rng = np.random.default_rng(2)
    fs = 2.048e6
    n = 2**21
    x = (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)
    t = np.arange(n) / fs
    for inicio in (0.1, 0.5, 0.9):  # surtos curtos em +375 kHz, o deslocamento do prova-b
        janela = (t > inicio) & (t < inicio + 0.02)
        x[janela] += (20 * np.exp(2j * np.pi * 375e3 * t[janela])).astype(np.complex64)
    captura = tmp_path / "sem_tx.npy"
    np.save(captura, x)
    r = _rodar("escolher_canal.py", "--captura", str(captura), "--perfil", "prova-b")
    assert r.returncode == 0, r.stderr
    assert "(+375 kHz)" in r.stdout and "--deslocamento-hz 375000 " not in r.stdout
    atual = float(r.stdout.split("kHz): ")[1].split(" dB")[0])
    assert atual > 20  # o surto aparece no deslocamento atual


def test_gravar_iq_troca_o_ponto_do_nome(tmp_path: Path) -> None:
    caminho = config.RAIZ / "scripts" / "gravar_iq.py"
    spec = importlib.util.spec_from_file_location("script_gravar_iq", caminho)
    assert spec is not None and spec.loader is not None
    gravar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gravar)
    pasta = tmp_path / "sessao.1"  # o ponto da pasta fica
    base = gravar.caminho_base(pasta, "var_919.12", "20261125_101010")
    assert base == pasta / "var_919_12_20261125_101010"
    assert base.with_suffix(".npy").name == "var_919_12_20261125_101010.npy"


def test_criterio_da_prova_a() -> None:
    assert prova.criterio_prova_a(0.00064, 747.4).startswith("PASSA (")
    assert prova.criterio_prova_a(0.01, 999.0).startswith("PASSA (")  # 1% ainda vale
    assert "PER de 4.99%" in prova.criterio_prova_a(0.0499, 744.1)  # 8-PSK a -25 dB, 25/11
    assert prova.criterio_prova_a(0.0, 1000.0) == "NÃO PASSA: banda de 1000 kHz"
    assert prova.criterio_prova_a(0.0, None) == "PASSA na PER; banda não medida"
    assert prova.criterio_prova_a(None, 700.0) == "NÃO PASSA: sem PER"


def test_quadros_falsos_de_outro_tamanho_ficam_de_fora() -> None:
    pacotes = [
        Pacote(0, bytes(128)),
        Pacote(7, bytes(80)),
        Pacote(1, b"x" * 128),
        Pacote(9, bytes(208)),
    ]
    validos, falsos = prova.so_os_da_prova(pacotes)
    assert [p.sequencia for p in validos] == [0, 1] and falsos == 2
    dados, faltando = prova.remontar(validos)  # antes caía com "tamanhos"
    assert dados == bytes(128) + b"x" * 128 and faltando == []


def test_alcance_com_as_distancias_informadas_no_fim(tmp_path: Path) -> None:
    """No pátio ninguém sabe a distância na hora: grava P1, P2, P3 e informa no fim."""
    for nome, goodput, per in (
        ("P1", 11_800.0, 0.0),
        ("P2", 11_700.0, 0.005),
        ("P3", 7_000.0, 0.4),
    ):
        resumo = {"prova": "b", "posicao": nome, "distancia_m": None, "goodput_bps": goodput,
                  "per": per, "pacotes_unicos": 600, "ebn0_db": None}  # fmt: skip
        (tmp_path / f"prova_b_{nome}_resumo.json").write_text(json.dumps(resumo), encoding="utf-8")
    sem = _rodar("relatorio_alcance.py", str(tmp_path))
    assert sem.returncode == 0, sem.stderr
    assert (
        "Sem distância: P2 (passou)" in sem.stdout
        and "Sem distância: P3 (não passou)" in sem.stdout
    )
    com = _rodar("relatorio_alcance.py", str(tmp_path), "--distancias", "P1=12", "P2=37,5", "P3=60")
    assert com.returncode == 0, com.stderr
    texto = (tmp_path / "alcance.md").read_text(encoding="utf-8")
    assert "Maior distância validada: **37.5 m**" in texto and "Sem distância" not in texto
    errado = _rodar("relatorio_alcance.py", str(tmp_path), "--distancias", "P1")
    assert errado.returncode != 0 and "NOME=METROS" in errado.stderr


def test_prova_rx_da_o_veredito_da_prova_b(tmp_path: Path) -> None:
    arquivo = tmp_path / "b.enc"
    arquivo.write_bytes(bytes(range(256)) * 4)
    sinal = tmp_path / "b_sim.npy"
    tx = _rodar("transmitir.py", str(arquivo), "--perfil", "prova-b", "--duracao-s", "0.5",
                "--simular", str(sinal), "--pasta", str(tmp_path))  # fmt: skip
    assert tx.returncode == 0, tx.stderr
    rx = _rodar("prova_rx.py", "--prova", "b", "--captura", str(sinal), "--janela-s", "0.5",
                "--posicao", "P1", "--pasta", str(tmp_path))  # fmt: skip
    assert rx.returncode == 0, rx.stderr
    assert "Prova B: NÃO PASSA" in rx.stdout  # poucos pacotes em 0,5 s: menos de 500


@pytest.mark.parametrize(
    ("ebn0_db", "taxa_bits", "esperado"),
    [
        (22.0, 2_048_000.0, "prova-a-8psk"),  # 8-PSK a -20 dB em 25/11: passou
        (17.0, 2_048_000.0, "prova-a"),  # 8-PSK a -25 dB: PER de 5%, a DQPSK cabe
        (18.13, 1_365_333.3, "prova-a"),  # DQPSK em dois PCs, 26/11: PER de 0,68%
        (12.1, 1_365_333.3, "prova-a-fec"),  # DQPSK a -30 dB em casa: PER de 55%
        (5.0, 1_365_333.3, None),  # nem a FEC
        (None, 1_365_333.3, None),
    ],
)
def test_recomendar_perfil_da_prova_a_pelo_sinal(
    ebn0_db: float | None, taxa_bits: float, esperado: str | None
) -> None:
    nome, frase = prova.recomendar_perfil_a(ebn0_db, taxa_bits)
    assert nome == esperado
    assert (f"--perfil {esperado}" in frase) if esperado else ("--perfil" not in frase)


def test_prova_b_recebe_com_o_rtl_frio_andando_ate_9_khz(tmp_path: Path) -> None:
    """Ensaio externo de 26/11: offset de 2,1 kHz e andando; a busca de 3 kHz perdia quadros."""
    from sdrlink import receptor  # noqa: PLC0415

    arquivo = tmp_path / "b.enc"
    arquivo.write_bytes(bytes(range(256)) * 4)
    sinal = tmp_path / "b_sim.npy"
    tx = _rodar("transmitir.py", str(arquivo), "--perfil", "prova-b", "--duracao-s", "0.6",
                "--simular", str(sinal), "--pasta", str(tmp_path))  # fmt: skip
    assert tx.returncode == 0, tx.stderr
    p = config.perfil("prova-b")
    x = np.load(sinal)
    f = np.linspace(4000.0, 9000.0, len(x))  # RTL esquentando: de 4 a 9 kHz na gravação
    y = x * np.exp(2j * np.pi * np.cumsum(f) / p.taxa_sps)
    cfg = receptor.ConfigReceptor(p.modem(), p.taxa_sps, p.deslocamento_hz, p.limiar, fec=p.fec)
    aceitos = {q.sequencia for q in receptor.pacotes_aceitos(receptor.receber(y, cfg))}
    transmitidos = len((next(tmp_path.glob("tx_*.txt"))).read_text(encoding="utf-8").splitlines())
    assert transmitidos >= 5 and len(aceitos) == transmitidos  # todos
