"""Testes do transmissor de prova, das métricas e do envio em fluxo ao Pluto (sub-bloco 3d)."""

import importlib.util
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
    maximo = quadro.SEQUENCIA_MAX
    assert [p.sequencia for p in transmissor.numerar([b"a", b"b", b"c"], maximo - 1)] == [
        maximo - 1,
        maximo,
        0,
    ]
    assert maximo == 2**24 - 1  # quadro v3: 60 s de DQPSK (70 400 pacotes) não dão a volta


@pytest.mark.parametrize("bloco", [5000, 8950, 997])
def test_fluxo_em_blocos_fixos_com_fase_continua(bloco: int) -> None:
    # 8950: a borda do 1º bloco cai dentro da sobreposição do 2º quadro (que começa em 8944):
    # um bloco que saísse antes de o quadro seguinte somar a sua parte ficaria errado ali
    config = ConfigTransmissor(DBPSK, FS, 250e3, emendar_caudas=True)
    pacotes = transmissor.numerar(_payloads(3))
    saida = list(transmissor.fluxo(pacotes, config, duracao_s=1.0, tamanho_bloco=bloco))
    assert all(len(b) == bloco for b, _ in saida)
    registros = [r for _, rs in saida for r in rs]
    assert [r.pacote for r in registros] == pacotes  # todos, em ordem, cada um uma vez
    for k, (_, rs) in enumerate(saida):  # cada registro no bloco em que o quadro começa
        assert all(k * bloco <= r.amostra_inicio < (k + 1) * bloco for r in rs)
    # o mesmo sinal montado de uma vez: cada quadro começa um período depois do anterior e
    # as caudas do pulso se somam (bloco 12); tudo deslocado de 250 kHz
    ondas = [modem.modular(quadro.montar_quadro(p), DBPSK) for p in pacotes]
    periodo = transmissor.amostras_por_quadro(DBPSK, emendar_caudas=True)
    assert periodo == len(ondas[0]) - (len(DBPSK.formato()) - 1)
    direto = np.zeros(2 * periodo + len(ondas[-1]), dtype=complex)
    for k, onda in enumerate(ondas):
        direto[k * periodo : k * periodo + len(onda)] += onda
    direto = direto * config.escala() * np.exp(2j * np.pi * 250e3 * np.arange(len(direto)) / FS)
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


def test_transmitir_fluxo_envia_em_ordem_e_desliga(
    pluto_falso: type[_PlutoFalso], monkeypatch: pytest.MonkeyPatch
) -> None:
    esperas: list[float] = []
    monkeypatch.setattr("sdrlink.hw.pluto_tx.time.sleep", esperas.append)
    blocos = [np.full(4, k, dtype=np.complex64) for k in range(3)]
    vistos: list[int] = []
    n = pluto_tx.transmitir_fluxo(pluto_tx.ConfigPluto(919.5e6), iter(blocos), vistos.append)
    # antes de desligar, espera a fila de 4 buffers sair (bancada de 25/11)
    taxa = pluto_tx.ConfigPluto(919.5e6).taxa_sps
    assert esperas == [pytest.approx(4 * 4 / taxa + pluto_tx.MARGEM_DRENO_S)]
    sdr = pluto_falso.instancias[0]
    assert n == 3 and vistos == [1, 2, 3]
    assert [b[0] for b in sdr.enviados] == [0, 1, 2]
    assert sdr.tx_cyclic_buffer is False
    assert sdr.destruido and sdr.tx_hardwaregain_chan0 == pluto_tx.GANHO_MIN_DB


def test_transmitir_fluxo_desliga_mesmo_com_erro(
    pluto_falso: type[_PlutoFalso], monkeypatch: pytest.MonkeyPatch
) -> None:
    esperas: list[float] = []
    monkeypatch.setattr("sdrlink.hw.pluto_tx.time.sleep", esperas.append)
    blocos = [np.zeros(4, dtype=np.complex64), np.zeros(5, dtype=np.complex64)]
    with pytest.raises(ValueError, match="o primeiro tinha 4"):
        pluto_tx.transmitir_fluxo(pluto_tx.ConfigPluto(919.5e6), iter(blocos))
    sdr = pluto_falso.instancias[0]
    assert len(sdr.enviados) == 1 and sdr.destruido
    assert esperas == []  # com erro desliga na hora
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


def test_fluxo_com_fec_e_periodo_do_quadro_codificado() -> None:
    cm = ConfigModem("dbpsk", "rrc", 8)
    # período: os bits do quadro mais o símbolo de referência; com as caudas emendadas os
    # 12 símbolos de cauda do RRC deixam de contar (bloco 12)
    assert transmissor.amostras_por_quadro(cm, emendar_caudas=True) == (1117 + 1) * 8
    assert transmissor.amostras_por_quadro(cm, fec=True, emendar_caudas=True) == (2201 + 1) * 8
    assert transmissor.amostras_por_quadro(cm) == (1117 + 13) * 8  # padrão: sem emenda
    assert transmissor.amostras_por_quadro(cm, fec=True) == (2201 + 13) * 8
    config = ConfigTransmissor(cm, FS, 250e3, fec=True)
    pacotes = transmissor.numerar([bytes(128)] * 3)
    registros = [r for _, rs in transmissor.fluxo(pacotes, config, 1.0) for r in rs]
    assert [r.amostra_inicio for r in registros] == [k * (2201 + 13) * 8 for k in range(3)]


def test_dqpsk_dobra_a_taxa_e_encurta_o_quadro() -> None:
    cm = ConfigModem("dqpsk", "rrc", 3, beta=0.25)
    assert ConfigTransmissor(cm, FS, 425e3).taxa_bits == pytest.approx(2 * FS / 3)
    # 29 símbolos do prefixo + 544 do resto (1088 bits / 2) + 1 de referência; sem a emenda,
    # mais 12 da cauda do RRC
    assert transmissor.amostras_por_quadro(cm, emendar_caudas=True) == (29 + 544 + 1) * 3
    assert transmissor.amostras_por_quadro(cm) == (29 + 544 + 13) * 3
    baixo, alto = ConfigTransmissor(cm, FS, 425e3).banda_99_hz()
    assert alto - baixo == pytest.approx(749e3, abs=10e3)  # mesma banda da DBPSK do prova-a


def test_fluxo_dqpsk_do_tx_e_recebido_pelo_rx() -> None:
    # o TX manda o prefixo um bit por símbolo; sem isso o RX não acha nenhum quadro
    cm = ConfigModem("dqpsk", "rrc", 3, beta=0.25)
    pacotes = transmissor.numerar([bytes([k]) * 128 for k in range(6)])
    config = ConfigTransmissor(cm, FS, 425e3)
    sinal = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, config, 1.0)])
    x = np.concatenate([np.zeros(5000, dtype=complex), sinal / config.amplitude])
    d = receptor.receber(x, ConfigReceptor(cm, FS, 425e3))
    assert receptor.pacotes_aceitos(d) == pacotes


def test_emenda_nao_vale_para_a_2fsk() -> None:
    # na 2-FSK a fase é contínua dentro do quadro: somar as caudas não seria uma modulação
    # contínua, então os quadros continuam encostados, com ou sem a opção
    gfsk = ConfigModem("fsk", "gaussiano", 16)
    assert transmissor.amostras_por_quadro(gfsk, emendar_caudas=True) == (
        transmissor.amostras_por_quadro(gfsk)
    )
    pacotes = transmissor.numerar(_payloads(3))
    com = [
        b
        for b, _ in transmissor.fluxo(
            pacotes, ConfigTransmissor(gfsk, FS, emendar_caudas=True), 1.0
        )
    ]
    sem = [b for b, _ in transmissor.fluxo(pacotes, ConfigTransmissor(gfsk, FS), 1.0)]
    np.testing.assert_array_equal(np.concatenate(com), np.concatenate(sem))


@pytest.mark.parametrize("emendar", [False, True])
def test_pacotes_que_cabem_e_o_que_o_fluxo_manda(emendar: bool) -> None:
    config = ConfigTransmissor(
        ConfigModem("dqpsk", "rrc", 3, beta=0.25), FS, 425e3, emendar_caudas=emendar
    )
    cabem = transmissor.pacotes_que_cabem(config, 0.05)
    pacotes = transmissor.numerar([bytes(128)] * (cabem + 10))
    enviados = [r for _, rs in transmissor.fluxo(pacotes, config, 0.05) for r in rs]
    assert len(enviados) == cabem
    assert (
        transmissor.pacotes_que_cabem(
            ConfigTransmissor(config.modem, FS, 425e3, emendar_caudas=True), 60.0
        )
        > 2**16
    )
    with pytest.raises(ValueError, match="duração"):
        transmissor.pacotes_que_cabem(config, 0.0)


def _script_transmitir() -> types.ModuleType:
    """O scripts/transmitir.py como módulo (scripts/ não é pacote)."""
    caminho = Path(__file__).resolve().parents[1] / "scripts" / "transmitir.py"
    spec = importlib.util.spec_from_file_location("script_transmitir", caminho)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize("pre_gerar", [False, True])
def test_pre_gerar_entrega_ao_pluto_os_mesmos_blocos_ja_prontos(pre_gerar: bool) -> None:
    script = _script_transmitir()
    config = ConfigTransmissor(DBPSK, FS, 250e3)
    pacotes = transmissor.numerar(_payloads(30))
    log: list[transmissor.RegistroTx] = []
    fonte = script.fonte_de_blocos(pacotes, config, 0.05, log, pre_gerar)
    # com pre_gerar, o log já está completo antes de o 1º bloco ir para o Pluto
    assert (len(log) > 0) is pre_gerar
    blocos = list(fonte)
    referencia = [b for b, _ in transmissor.fluxo(pacotes, config, 0.05)]
    assert len(blocos) == len(referencia)
    assert all(np.array_equal(a, b) for a, b in zip(blocos, referencia, strict=True))
    assert len(log) == transmissor.pacotes_que_cabem(config, 0.05)
