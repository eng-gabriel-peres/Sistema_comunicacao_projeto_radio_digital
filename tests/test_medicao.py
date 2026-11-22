"""Testes das medidas da Etapa 5: BER com sequência conhecida, banda a 99% e Eb/N0 da captura."""

from dataclasses import dataclass

import numpy as np
import pytest

from sdrlink import canal, medicao, metricas, quadro, receptor, teoria, transmissor
from sdrlink.modem import ConfigModem
from sdrlink.quadro import Pacote
from sdrlink.receptor import ConfigReceptor
from sdrlink.transmissor import ConfigTransmissor

FS = 2.048e6
DBPSK = ConfigModem("dbpsk", "rrc", 8)
PERIODO = 9000.0


@dataclass(frozen=True)
class _Det:
    inicio: float
    pacote: Pacote | None
    bits: np.ndarray | None


def _bits_do_quadro(seq: int, erros: tuple[int, ...] = ()) -> np.ndarray:
    """Bits depois do sync de um quadro com o payload conhecido, com bits de payload trocados."""
    p = Pacote(seq, metricas.payload_conhecido(seq))
    bits = quadro.montar_quadro(p)[29:-16].copy()
    for k in erros:
        bits[quadro.BITS_CABECALHO + k] ^= 1
    return bits


def test_payload_conhecido_fixo_e_diferente_por_sequencia() -> None:
    assert metricas.payload_conhecido(7) == metricas.payload_conhecido(7)
    assert metricas.payload_conhecido(7) != metricas.payload_conhecido(8)
    assert metricas.payload_conhecido(2**24 + 3) == metricas.payload_conhecido(3)
    assert metricas.payload_conhecido(65536 + 3) != metricas.payload_conhecido(3)  # v3: 24 bits
    assert len(metricas.payload_conhecido(0)) == 128


def test_ber_conta_os_erros_e_deduz_a_sequencia_pela_posicao() -> None:
    deteccoes = [
        _Det(1000.0, Pacote(10, metricas.payload_conhecido(10)), _bits_do_quadro(10)),
        _Det(1000.0 + PERIODO, None, _bits_do_quadro(11, (0, 5, 900))),  # CRC falho, 3 erros
        _Det(1000.0 + 2.5 * PERIODO, None, _bits_do_quadro(11)),  # falso alarme entre quadros
        _Det(1000.0 + 3 * PERIODO + 4, None, _bits_do_quadro(13, (7,))),  # CRC falho, 1 erro
        _Det(1000.0 + 4 * PERIODO, None, None),  # sem bits guardados: ignorado
    ]
    r = metricas.medir_ber(deteccoes, PERIODO, tolerancia_amostras=16)
    assert r["quadros_comparados"] == 3
    assert r["quadros_com_crc_falho_comparados"] == 2
    assert r["deteccoes_fora_de_posicao"] == 1
    assert (r["bits_errados"], r["bits_comparados"]) == (4, 3 * 1024)


def test_ber_sem_quadro_valido_nao_identifica_nada() -> None:
    r = metricas.medir_ber([_Det(0.0, None, _bits_do_quadro(1))], PERIODO, 16)
    assert r["quadros_comparados"] == 0 and r["deteccoes_fora_de_posicao"] == 1
    assert np.isnan(r["ber"])
    with pytest.raises(ValueError, match="tolerância"):
        metricas.medir_ber([], PERIODO, PERIODO)


def _captura(ebn0_db: float, n_ruido: int, rng: np.random.Generator) -> tuple[np.ndarray, int]:
    """Ruído, depois quadros DBPSK com o payload conhecido; com um pico de DC constante."""
    tx = ConfigTransmissor(DBPSK, FS, 250e3)
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(150)])
    sinal = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, tx, 1.0)]).astype(complex)
    sinal = sinal[: 150 * transmissor.amostras_por_quadro(DBPSK)]
    potencia = np.mean(np.abs(sinal) ** 2)
    x = np.concatenate([np.zeros(n_ruido), canal.girar(sinal, -1300.0, FS)])
    n0 = potencia * 8 / 10 ** (ebn0_db / 10)
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    return x + 0.3 * np.sqrt(potencia), n_ruido  # pico de DC do RTL, nos dois trechos


def test_banda_e_ebn0_medidos_batem_com_os_verdadeiros() -> None:
    x, n_ruido = _captura(8.0, 500_000, np.random.default_rng(1))  # 0,24 s de ruído
    r = medicao.medir_captura(x, n_ruido, len(x), FS, FS / 8)
    assert r["medido"] is True
    assert r["banda_99_khz"] == pytest.approx(1.165 * 256, rel=0.03)  # 298 kHz (etapa 3b)
    limites = r["banda_99_limites_khz"]
    assert isinstance(limites, list)
    baixo, alto = limites
    # o centro flutua com o ruído: 243,9 a 251,4 kHz em 10 sementes (bloco 10); ±5 kHz era
    # do tamanho da flutuação e passava pela semente
    assert (baixo + alto) / 2 == pytest.approx(250, abs=8)
    assert r["ebn0_estimado_db"] == pytest.approx(8.0, abs=0.3)


def test_sem_ruido_antes_do_primeiro_quadro_nao_mede() -> None:
    # 0,1 s de ruído: menos que o mínimo de 0,2 s (com 49 ms a banda chegou a errar 33%)
    x, n_ruido = _captura(8.0, 204_800, np.random.default_rng(2))
    r = medicao.medir_captura(x, n_ruido, len(x), FS, FS / 8)
    assert r["medido"] is False and "ruído" in str(r["motivo"])
    with pytest.raises(ValueError, match="acima do ruído"):
        medicao.banda_99_medida(np.zeros(20_000, complex), np.zeros(20_000, complex), FS)


def test_cadeia_completa_de_ber_bate_com_a_teoria() -> None:
    x, _ = _captura(7.0, 50_000, np.random.default_rng(3))
    deteccoes = receptor.receber(x, ConfigReceptor(DBPSK, FS, 250e3, guardar_bits=True))
    r = metricas.medir_ber(deteccoes, transmissor.amostras_por_quadro(DBPSK), 16)
    assert r["quadros_comparados"] == 150  # todos, inclusive os de CRC falho
    assert r["quadros_com_crc_falho_comparados"] > 50  # a 7 dB a maioria falha no CRC
    assert r["ber"] == pytest.approx(float(teoria.ber_dbpsk(7.0)), rel=0.3)  # 3,1e-3


def _bits_com_sequencia_lida(seq_real: int, seq_lida: int) -> np.ndarray:
    """Quadro com o payload de seq_real, mas com o campo de sequência corrompido para seq_lida."""
    bits = _bits_do_quadro(seq_real)
    campo = np.unpackbits(
        np.frombuffer(seq_lida.to_bytes(quadro.BYTES_SEQUENCIA, "big"), dtype=np.uint8)
    )
    bits[quadro.BITS_COMPRIMENTO : quadro.BITS_CABECALHO] = campo
    return bits


def test_ber_sem_nenhum_crc_valido_acha_a_sequencia_por_votacao() -> None:
    # o 1º e o último quadro têm o campo de sequência corrompido: só a votação acerta
    deteccoes = [
        _Det(500.0, None, _bits_com_sequencia_lida(40, 7777)),
        _Det(500.0 + PERIODO, None, _bits_do_quadro(41, (3,))),
        _Det(500.0 + 2 * PERIODO, None, _bits_do_quadro(42)),
        _Det(500.0 + 3 * PERIODO, None, _bits_com_sequencia_lida(43, 9999)),
    ]
    r = metricas.medir_ber(deteccoes, PERIODO, 16)
    assert (r["quadros_comparados"], r["quadros_com_crc_falho_comparados"]) == (4, 4)
    assert r["bits_errados"] == 1  # o campo de sequência errado não entra: só o payload


def test_ber_acompanha_a_diferenca_de_relogio() -> None:
    # 0,5 amostra a mais por quadro: 50 amostras em 100 quadros, mais de 3 vezes a tolerância
    deteccoes = [_Det(1000.0 + k * (PERIODO + 0.5), None, _bits_do_quadro(k)) for k in range(100)]
    r = metricas.medir_ber(deteccoes, PERIODO, 16)
    assert (r["quadros_comparados"], r["segmentos"], r["bits_errados"]) == (100, 1, 0)
