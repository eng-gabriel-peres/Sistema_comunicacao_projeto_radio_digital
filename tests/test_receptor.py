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
    config: ConfigModem,
    n: int,
    rng: np.random.Generator,
    ebn0_db: float = 14.0,
    fec: bool = False,
    tamanhos: tuple[int, ...] = (128,),
) -> tuple[np.ndarray, list[Pacote], list[float]]:
    """Captura simulada: n quadros v2 separados por silêncio, com atraso, offset e ruído.

    O Eb/N0 é por bit no ar; os tamanhos de payload se repetem em ciclo.
    """
    pacotes = [
        Pacote(s, rng.integers(0, 256, tamanhos[s % len(tamanhos)], dtype=np.uint8).tobytes())
        for s in range(n)
    ]
    partes, inicios, pos = [np.zeros(2000, dtype=complex)], [], 2000.37
    for p in pacotes:
        onda = modem.modular(quadro.montar_quadro(p, fec), config)
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


def test_2fsk_rejeita_um_pico_de_dc_do_tamanho_do_sinal() -> None:
    # o correlator da 2-FSK precisa do filtro de banda antes: sem ele, um pico de DC do tamanho
    # do sinal (o do RTL, ou outro sinal forte na banda) multiplicava a BER por 25
    config = ConfigModem("fsk", "gaussiano", 16)
    x, pacotes, _ = _captura(config, 8, np.random.default_rng(14), ebn0_db=13.0)
    pico = np.sqrt(np.mean(np.abs(x[len(x) // 2 :]) ** 2))  # da ordem da amplitude do sinal
    rx = ConfigReceptor(config, FS, deslocamento_hz=DESLOCAMENTO)
    assert receptor.pacotes_aceitos(receptor.receber(x + pico, rx)) == pacotes


def test_fasor_rapido_igual_ao_exp() -> None:
    for ciclos in (100 / 4_194_304, -0.0371, 0.25):
        for n in (1, 7, 1000, 300_001):
            esperado = np.exp(2j * np.pi * ciclos * np.arange(n))
            np.testing.assert_allclose(receptor._fasor(ciclos, n), esperado, atol=1e-8)


def test_interpolador_fir_igual_ao_atraso_exato() -> None:
    # sinal de banda limitada (RRC, 8 amostras por bit): o FIR de 33 coeficientes reproduz o
    # atraso fracionário exato por FFT, longe das bordas
    sinal = modem.modular(
        np.random.default_rng(1).integers(0, 2, 400).astype(np.uint8),
        ConfigModem("dbpsk", "rrc", 8),
    )
    for inicio in (100.0, 100.25, 137.6):
        fir = receptor._alinhar(sinal, inicio, 2000)
        base = int(inicio)
        # referência: atraso por FFT do sinal inteiro e só depois o recorte (recortar antes
        # cria um começo abrupto, e o "toque" desse corte é que apareceria como erro)
        exato = (
            canal.atrasar(sinal, 1 - (inicio - base))[base + 1 : base + 2001]
            if inicio % 1
            else sinal[base : base + 2000]
        )
        np.testing.assert_allclose(fir, exato, atol=1e-3 * np.max(np.abs(sinal)))


def test_le_o_quadro_da_prova_mesmo_com_o_comprimento_corrompido() -> None:
    # a BER precisa dos 1024 bits de payload mesmo quando o campo de comprimento chega errado
    config = ConfigModem("dbpsk", "rrc", 8)
    bits = quadro.montar_quadro(Pacote(3, bytes(range(128))))
    bits[29:37] = [0, 0, 0, 0, 0, 1, 0, 1]  # comprimento 5 no lugar de 128
    onda = modem.modular(bits, config)
    x = np.concatenate([np.zeros(3000), onda, np.zeros(30_000)]).astype(complex)
    d = receptor.receber(x, ConfigReceptor(config, FS, guardar_bits=True))
    assert len(d) == 1 and d[0].situacao == "crc"
    assert d[0].bits is not None and len(d[0].bits) >= quadro.bits_apos_sync(128)
    np.testing.assert_array_equal(d[0].bits[24 : 24 + 1024], bits[29 + 24 : 29 + 24 + 1024])


def test_pulso_em_cache_e_so_leitura() -> None:
    forma = ConfigModem("dbpsk", "rrc", 8).formato()
    assert forma is ConfigModem("dbpsk", "rrc", 8).formato()  # calculado uma vez
    with pytest.raises(ValueError, match="read-only"):
        forma[0] = 1.0


def test_fec_le_quadros_de_varios_tamanhos_com_offset_e_emendas() -> None:
    # 128 bytes (a janela padrão), 40 (menor que a janela) e 200 (exige a releitura)
    cm = ConfigModem("dbpsk", "rrc", 8)
    x, pacotes, inicios = _captura(cm, 9, np.random.default_rng(31), 9.0, True, (128, 40, 200))
    config = ConfigReceptor(cm, FS, DESLOCAMENTO, fec=True)
    d = receptor.receber(x, config, tamanho_bloco=_bloco_pequeno(config))
    assert receptor.pacotes_aceitos(d) == pacotes
    assert all(abs(a.inicio - b) < 0.4 for a, b in zip(d, inicios, strict=True))


def test_fec_recebe_onde_sem_codigo_falha() -> None:
    # mesmo Eb/N0 por bit útil (8 dB) e mesma taxa útil (128 kbit/s): sem código a PER passa de
    # 25%; com o código no ar a 256 kbit/s (4,99 dB por bit no ar), os 20 quadros chegam
    sem = ConfigModem("dbpsk", "rrc", 16)
    com = ConfigModem("dbpsk", "rrc", 8)
    x, pacotes, _ = _captura(sem, 20, np.random.default_rng(32), 8.0)
    certos_sem = set(
        receptor.pacotes_aceitos(receptor.receber(x, ConfigReceptor(sem, FS, DESLOCAMENTO)))
    )
    x, pacotes_fec, _ = _captura(com, 20, np.random.default_rng(32), 8.0 - 3.0103, True)
    config = ConfigReceptor(com, FS, DESLOCAMENTO, fec=True)
    certos_com = set(receptor.pacotes_aceitos(receptor.receber(x, config)))
    assert len(certos_sem & set(pacotes)) <= 15
    assert certos_com == set(pacotes_fec)


def test_fec_com_captura_curta_nao_le_o_quadro() -> None:
    cm = ConfigModem("dbpsk", "rrc", 8)
    bits = quadro.montar_quadro(Pacote(1, bytes(128)), fec=True)
    onda = modem.modular(bits, cm)
    x = np.concatenate([np.zeros(3000), onda[: 40 * 8 * 8]]).astype(complex)  # só 320 bits
    d = receptor.receber(x, ConfigReceptor(cm, FS, fec=True))
    assert [a.situacao for a in d] == ["curto"]
