"""Testes do receptor multiquadro (sdrlink.receptor)."""

from pathlib import Path

import numpy as np
import pytest

from sdrlink import canal, modem, quadro, receptor
from sdrlink.modem import ConfigModem
from sdrlink.quadro import Pacote
from sdrlink.receptor import ConfigReceptor

FS = 2.048e6
DESLOCAMENTO = 250e3
OFFSET = -1600.0  # pior offset residual medido em 04/11 (A18)


def _captura(
    config: ConfigModem, n: int, rng: np.random.Generator, ebn0_db: float = 14.0
) -> tuple[np.ndarray, list[Pacote], list[float]]:
    """Captura simulada: n quadros v2 separados por silêncio, com atraso, offset e ruído."""
    pacotes = [Pacote(s, rng.integers(0, 256, 128, dtype=np.uint8).tobytes()) for s in range(n)]
    partes, inicios, pos = [np.zeros(2000, dtype=complex)], [], 2000.37
    for p in pacotes:
        onda = modem.modular(quadro.montar_quadro(p), config)
        intervalo = int(rng.integers(300, 3000))
        inicios.append(pos)
        partes += [onda, np.zeros(intervalo, dtype=complex)]
        pos += len(onda) + intervalo
    sinal = canal.girar(canal.atrasar(np.concatenate(partes), 0.37), DESLOCAMENTO + OFFSET, FS)
    return 0.05 * canal.awgn(sinal, ebn0_db, config.sps, rng), pacotes, inicios


def _bloco_pequeno(config: ConfigReceptor) -> int:
    """Bloco do menor tamanho aceito: força quadros nas emendas."""
    return 2 * (config.amostras_por_quadro_max() + len(config.modelo())) * config.decimacao + 7


@pytest.mark.parametrize(
    "config",
    [
        ConfigModem("dbpsk", "rrc", 8),
        ConfigModem("ook", "rrc", 16),
        ConfigModem("fsk", "gaussiano", 16),
        ConfigModem("fsk", "retangular", 32),
    ],
    ids=["dbpsk-256k", "ook-128k", "gfsk-128k", "cpfsk-64k"],
)
def test_todos_os_quadros_com_offset_atraso_e_emendas(config: ConfigModem) -> None:
    rng = np.random.default_rng(1)
    x, pacotes, inicios = _captura(config, 8, rng)
    rx = ConfigReceptor(config, FS, deslocamento_hz=DESLOCAMENTO)
    deteccoes = receptor.receber(x, rx, tamanho_bloco=_bloco_pequeno(rx))
    assert receptor.pacotes_aceitos(deteccoes) == pacotes  # todos, em ordem, sem duplicata
    certas = [d for d in deteccoes if d.situacao == "ok"]
    for d, i in zip(certas, inicios, strict=True):
        assert abs(d.inicio - i) < 0.05 * config.sps  # instante: menos de 5% do bit (Etapa 4)
        assert abs(d.offset_hz - OFFSET) < 300  # offset estimado pelo preâmbulo
    if config.pulso != "retangular":  # a CPFSK tem falsos raros (rejeitados pelo CRC)
        assert len(deteccoes) == len(pacotes)  # nenhuma detecção falsa nos dados


@pytest.mark.parametrize(
    "config",
    [ConfigModem("ook", "rrc", 16), ConfigModem("fsk", "gaussiano", 16)],
    ids=["ook-128k", "gfsk-128k"],
)
def test_todo_quadro_e_detectado_a_8_db(config: ConfigModem) -> None:
    # a 8 dB a OOK e a GFSK ainda não decodificam bem, mas o sincronismo já tem de ser achado:
    # é o filtro de detecção que tira o ruído fora da banda da métrica (seção 3, decisão 3)
    x, _, inicios = _captura(config, 12, np.random.default_rng(5), ebn0_db=8.0)
    deteccoes = receptor.receber(x, ConfigReceptor(config, FS, deslocamento_hz=DESLOCAMENTO))
    for i in inicios:
        assert any(abs(d.inicio - i) < config.sps for d in deteccoes), f"quadro em {i:.0f} perdido"


def test_taxa_baixa_com_decimacao_e_offset_grande() -> None:
    config = ConfigModem("dbpsk", "rrc", 200)  # 10,24 kbit/s: 1,6 kHz é 16% da taxa
    rx = ConfigReceptor(config, FS, deslocamento_hz=DESLOCAMENTO)
    assert rx.decimacao == 25
    x, pacotes, _ = _captura(config, 3, np.random.default_rng(2))
    deteccoes = receptor.receber(x, rx)
    assert receptor.pacotes_aceitos(deteccoes) == pacotes
    assert all(abs(d.offset_hz - OFFSET) < 50 for d in deteccoes if d.situacao == "ok")


def test_so_ruido_nao_gera_pacote() -> None:
    rng = np.random.default_rng(3)
    ruido = rng.standard_normal(400_000) + 1j * rng.standard_normal(400_000)
    rx = ConfigReceptor(ConfigModem("dbpsk", "rrc", 8), FS)
    deteccoes = receptor.receber(ruido, rx)
    assert receptor.pacotes_aceitos(deteccoes) == []
    assert len(deteccoes) <= 1  # a métrica do ruído fica abaixo do limiar (99,99% abaixo de 0,43)


def test_ook_le_o_limiar_so_no_proprio_quadro() -> None:
    # depois do quadro, uma portadora 4 vezes mais forte ocupa o resto da janela de leitura
    # (interferência ou outro TX): o limiar da OOK tem de vir só dos símbolos do quadro
    config = ConfigModem("ook", "rrc", 16)
    p = Pacote(9, bytes(range(32)))
    onda = modem.modular(quadro.montar_quadro(p), config)
    forte = 4 * np.max(np.abs(onda)) * np.ones(40_000)
    sinal = np.concatenate([np.zeros(500), onda, forte]).astype(complex)
    x = canal.awgn(sinal, 30.0, 16, np.random.default_rng(4))
    assert receptor.pacotes_aceitos(receptor.receber(x, ConfigReceptor(config, FS))) == [p]


def test_repeticao_nas_emendas_e_duplicatas() -> None:
    p = Pacote(1, b"a")
    d1 = receptor.Deteccao(1000.0, 0.8, 0.0, "ok", p)
    d2 = receptor.Deteccao(1000.4, 0.9, 0.0, "ok", p)  # o mesmo quadro visto no bloco seguinte
    d3 = receptor.Deteccao(90_000.0, 0.9, 0.0, "ok", p)  # o TX repetiu o pacote
    assert receptor._sem_repeticao([d2, d1, d3], 480) == [d2, d3]
    assert receptor.pacotes_aceitos([d1, d3]) == [p]


def test_arquivo_de_saida(tmp_path: Path) -> None:
    caminho = receptor.gravar_saida(
        [Pacote(1, b"\x01\xab"), Pacote(2, b"")], tmp_path / "saida.txt"
    )
    assert caminho.read_text(encoding="utf-8") == "1\t01ab\n2\t\n"
    assert receptor.gravar_saida([], tmp_path / "vazio.txt").read_text(encoding="utf-8") == ""
    with pytest.raises(ValueError, match=r".txt"):
        receptor.gravar_saida([], tmp_path / "saida.csv")


def test_validacoes_e_decimacao() -> None:
    assert ConfigReceptor(ConfigModem("ook", "rrc", 16), FS).decimacao == 2
    assert ConfigReceptor(ConfigModem("ook", "rrc", 12), FS).decimacao == 1  # 12/2 = 6 < 8
    assert len(ConfigReceptor(ConfigModem("dbpsk", "rrc", 8), FS).hipoteses_hz()) == 3
    with pytest.raises(ValueError, match="limiar"):
        ConfigReceptor(ConfigModem("ook", "rrc", 16), FS, limiar=1.0)
    with pytest.raises(ValueError, match="deslocamento"):
        ConfigReceptor(ConfigModem("ook", "rrc", 16), FS, deslocamento_hz=FS)
    with pytest.raises(ValueError, match="offset"):
        ConfigReceptor(ConfigModem("ook", "rrc", 16), FS, offset_max_hz=1e6)
    with pytest.raises(ValueError, match="bloco"):
        receptor.receber(
            np.zeros(10, dtype=complex),
            ConfigReceptor(ConfigModem("ook", "rrc", 16), FS),
            tamanho_bloco=100,
        )


def test_resumo_da_recepcao() -> None:
    p, q = Pacote(1, b"a"), Pacote(2, b"b")
    deteccoes = [
        receptor.Deteccao(0.0, 0.9, -1500.0, "ok", p),
        receptor.Deteccao(9e4, 0.8, -1400.0, "ok", p),  # repetição do mesmo pacote
        receptor.Deteccao(2e5, 0.7, -1300.0, "ok", q),
        receptor.Deteccao(3e5, 0.55, 0.0, "crc", None),
        receptor.Deteccao(4e5, 0.6, 0.0, "curto", None),
    ]
    r = receptor.resumo(deteccoes, 2.0)
    assert r["deteccoes"] == 5
    assert (r["crc_ok"], r["crc_falho"], r["cortados"]) == (3, 1, 1)
    assert (r["pacotes_aceitos"], r["repeticoes_descartadas"]) == (2, 1)
    assert r["offset_residual_mediano_hz"] == -1400.0
    assert r["metrica_minima_aceitos"] == 0.7
    assert receptor.resumo([], 1.0)["offset_residual_mediano_hz"] is None
