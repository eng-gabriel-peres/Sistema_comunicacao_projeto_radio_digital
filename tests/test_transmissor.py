"""Testes do transmissor de prova, das métricas e do envio em fluxo ao Pluto (sub-bloco 3d)."""

import sys
import types
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from sdrlink import canal, metricas, modem, quadro, receptor, transmissor
from sdrlink.hw import pluto_tx
from sdrlink.modem import ConfigModem
from sdrlink.quadro import Pacote
from sdrlink.receptor import ConfigReceptor
from sdrlink.transmissor import ConfigTransmissor

FS = 2.048e6
DBPSK = ConfigModem("dbpsk", "rrc", 8)


def _payloads(n: int, semente: int = 1) -> list[bytes]:
    rng = np.random.default_rng(semente)
    return [rng.integers(0, 256, 128, dtype=np.uint8).tobytes() for _ in range(n)]


def test_ler_payloads_nos_dois_formatos(tmp_path: Path) -> None:
    payloads = _payloads(3)
    (tmp_path / "p.bin").write_bytes(b"".join(payloads))
    (tmp_path / "p.txt").write_text("\n".join(p.hex() for p in payloads) + "\n\n", encoding="utf-8")
    assert transmissor.ler_payloads(tmp_path / "p.bin") == payloads
    assert transmissor.ler_payloads(tmp_path / "p.txt") == payloads
    (tmp_path / "curto.bin").write_bytes(b"x" * 200)
    with pytest.raises(ValueError, match="múltiplo"):
        transmissor.ler_payloads(tmp_path / "curto.bin")
    (tmp_path / "curto.txt").write_text("abcd\n", encoding="utf-8")
    with pytest.raises(ValueError, match="tamanho"):
        transmissor.ler_payloads(tmp_path / "curto.txt")
    with pytest.raises(ValueError, match="formato"):
        transmissor.ler_payloads(tmp_path / "p.csv")


def test_sequencia_volta_a_zero() -> None:
    assert [p.sequencia for p in transmissor.numerar([b"a", b"b", b"c"], 65534)] == [
        65534,
        65535,
        0,
    ]


def test_fluxo_em_blocos_fixos_com_fase_continua() -> None:
    config = ConfigTransmissor(DBPSK, FS, 250e3)
    pacotes = transmissor.numerar(_payloads(3))
    saida = list(transmissor.fluxo(pacotes, config, duracao_s=1.0, tamanho_bloco=5000))
    assert all(len(b) == 5000 for b, _ in saida)
    registros = [r for _, rs in saida for r in rs]
    assert [r.pacote for r in registros] == pacotes  # todos, em ordem, cada um uma vez
    for k, (_, rs) in enumerate(saida):  # cada registro no bloco em que o quadro começa
        assert all(k * 5000 <= r.amostra_inicio < (k + 1) * 5000 for r in rs)
    # o mesmo sinal montado de uma vez: quadros um atrás do outro, deslocados de 250 kHz
    ondas = [modem.modular(quadro.montar_quadro(p), DBPSK) for p in pacotes]
    direto = np.concatenate(ondas) * config.escala()
    direto = direto * np.exp(2j * np.pi * 250e3 * np.arange(len(direto)) / FS)
    fluxo = np.concatenate([b for b, _ in saida])
    np.testing.assert_allclose(
        fluxo[: len(direto)], direto, atol=0.05
    )  # quadros cortados entre blocos
    assert not fluxo[len(direto) :].any()  # o último bloco é completado com zeros
    assert np.max(np.abs(fluxo)) <= transmissor.AMPLITUDE_PADRAO


def test_so_comecam_pacotes_dentro_da_janela() -> None:
    config = ConfigTransmissor(DBPSK, FS)
    duracao = 2.5 * len(modem.modular(quadro.montar_quadro(Pacote(0, bytes(128))), DBPSK)) / FS
    registros = [
        r
        for _, rs in transmissor.fluxo(transmissor.numerar(_payloads(10)), config, duracao)
        for r in rs
    ]
    assert len(registros) == 3  # começam em 0, 1 e 2 quadros: o 3º começa antes do fim da janela
    assert all(r.amostra_inicio < duracao * FS for r in registros)


def test_banda_do_sinal_transmitido() -> None:
    baixo, alto = ConfigTransmissor(DBPSK, FS, 250e3).banda_99_hz()
    assert alto - baixo == pytest.approx(1.165 * 256e3, rel=0.03)  # RRC 0,35 (etapa 3b)
    assert (alto + baixo) / 2 == pytest.approx(250e3, abs=2e3)


def test_ida_e_volta_tx_rx_metricas(tmp_path: Path) -> None:
    config = ConfigTransmissor(DBPSK, FS, 250e3)
    pacotes = transmissor.numerar(_payloads(12, 2))
    saida = list(transmissor.fluxo(pacotes, config, duracao_s=1.0))
    bruto = np.concatenate([b for b, _ in saida]).astype(np.complex128) / pluto_tx.FUNDO_ESCALA_DAC
    sinal = canal.awgn(canal.girar(bruto, -900.0, FS), 15.0, 8, np.random.default_rng(3))
    aceitos = receptor.pacotes_aceitos(receptor.receber(sinal, ConfigReceptor(DBPSK, FS, 250e3)))
    log = transmissor.gravar_log([r for _, rs in saida for r in rs], tmp_path / "tx.txt")
    saida_rx = receptor.gravar_saida(aceitos, tmp_path / "rx.txt")
    r = metricas.avaliar(metricas.ler_pacotes(log), metricas.ler_pacotes(saida_rx), 1.0)
    assert (r["transmitidos"], r["recebidos_certos"], r["per"]) == (12, 12, 0.0)
    assert r["goodput_bps"] == 12 * 128 * 8


def test_metricas_classificam_cada_recebido() -> None:
    tx = [Pacote(0, b"a"), Pacote(1, b"b"), Pacote(2, b"c"), Pacote(3, b"d")]
    rx = [Pacote(0, b"a"), Pacote(0, b"a"), Pacote(1, b"X"), Pacote(9, b"z"), Pacote(2, b"c")]
    r = metricas.avaliar(tx, rx, duracao_s=2.0)
    assert r["recebidos_certos"] == 2 and r["duplicados"] == 1
    assert r["conteudo_diferente"] == 1 and r["espurios"] == 1
    assert r["perdidos"] == 2 and r["per"] == 0.5  # o 1 com conteúdo errado e o 3 contam como falha
    assert r["goodput_bps"] == 2 * 8 / 2.0  # só os certos, sem a duplicata
    with pytest.raises(ValueError, match="vazio"):
        metricas.avaliar([], rx, 1.0)


def test_ler_pacotes_rejeita_linha_fora_do_formato(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("1\tab\n2 cd\n", encoding="utf-8")
    with pytest.raises(ValueError, match="linha 2"):
        metricas.ler_pacotes(tmp_path / "x.txt")


class _PlutoFalso:
    """Imita adi.Pluto: guarda os blocos enviados e os atributos que o código grava."""

    instancias: ClassVar[list["_PlutoFalso"]] = []

    def __init__(self, uri: str) -> None:
        self.uri = uri
        self.enviados: list[np.ndarray] = []
        self.destruido = False
        self.tx_lo = 0
        self.tx_cyclic_buffer: bool | None = None
        self.tx_hardwaregain_chan0 = 0.0
        _PlutoFalso.instancias.append(self)

    def tx(self, bloco: np.ndarray) -> None:
        self.enviados.append(bloco.copy())

    def tx_destroy_buffer(self) -> None:
        self.destruido = True


@pytest.fixture
def pluto_falso(monkeypatch: pytest.MonkeyPatch) -> type[_PlutoFalso]:
    _PlutoFalso.instancias = []
    monkeypatch.setitem(sys.modules, "adi", types.SimpleNamespace(Pluto=_PlutoFalso))
    return _PlutoFalso


def test_transmitir_fluxo_envia_em_ordem_e_desliga(pluto_falso: type[_PlutoFalso]) -> None:
    blocos = [np.full(4, k, dtype=np.complex64) for k in range(3)]
    vistos: list[int] = []
    n = pluto_tx.transmitir_fluxo(pluto_tx.ConfigPluto(919.5e6), iter(blocos), vistos.append)
    sdr = pluto_falso.instancias[0]
    assert n == 3 and vistos == [1, 2, 3]
    assert [b[0] for b in sdr.enviados] == [0, 1, 2]
    assert sdr.tx_cyclic_buffer is False
    assert sdr.destruido and sdr.tx_hardwaregain_chan0 == pluto_tx.GANHO_MIN_DB


def test_transmitir_fluxo_desliga_mesmo_com_erro(pluto_falso: type[_PlutoFalso]) -> None:
    blocos = [np.zeros(4, dtype=np.complex64), np.zeros(5, dtype=np.complex64)]
    with pytest.raises(ValueError, match="o primeiro tinha 4"):
        pluto_tx.transmitir_fluxo(pluto_tx.ConfigPluto(919.5e6), iter(blocos))
    sdr = pluto_falso.instancias[0]
    assert len(sdr.enviados) == 1 and sdr.destruido
    assert sdr.tx_hardwaregain_chan0 == pluto_tx.GANHO_MIN_DB
    with pytest.raises(ValueError, match="fundo de escala"):
        pluto_tx.transmitir_fluxo(
            pluto_tx.ConfigPluto(919.5e6), iter([np.full(4, 40000.0, dtype=np.complex64)])
        )


def test_registro_vai_com_o_bloco_em_que_o_quadro_comeca() -> None:
    # blocos maiores que um quadro (o caso real: 2^18 amostras e cerca de 9 mil por quadro)
    config = ConfigTransmissor(DBPSK, FS)
    saida = list(
        transmissor.fluxo(transmissor.numerar(_payloads(7)), config, 1.0, tamanho_bloco=20_000)
    )
    assert sum(len(rs) for _, rs in saida) == 7
    for k, (_, rs) in enumerate(saida):
        assert all(k * 20_000 <= r.amostra_inicio < (k + 1) * 20_000 for r in rs)
