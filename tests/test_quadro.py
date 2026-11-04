"""Testes do quadro v2 (sdrlink.quadro)."""

import numpy as np
import pytest

from sdrlink import quadro
from sdrlink.quadro import Pacote

PAYLOAD_PROVA = bytes(range(128))  # 128 bytes, como na prova


def _corpo(pacote: Pacote) -> np.ndarray:
    """Bits depois do sync (sem a guarda), como o RX os entrega a interpretar()."""
    bits = quadro.montar_quadro(pacote)
    inicio = len(quadro.PREAMBULO) + len(quadro.SYNC)
    return bits[inicio : len(bits) - len(quadro.GUARDA)]


def test_crc16_valor_de_conferencia_e_residuo_zero() -> None:
    assert quadro.crc16(b"123456789") == 0x29B1  # CRC-16/CCITT-FALSE padrão
    dados = b"HELLO WORLD MANDRIAUM"
    assert quadro.crc16(dados + quadro.crc16(dados).to_bytes(2, "big")) == 0


def test_quadro_da_prova_tem_1109_bits_e_mantem_preambulo_e_sync_da_referencia() -> None:
    bits = quadro.montar_quadro(Pacote(7, PAYLOAD_PROVA))
    assert len(bits) == quadro.bits_por_quadro(128) == 1109
    assert "".join(map(str, bits[:16])) == "10" * 8
    assert "".join(map(str, bits[16:29])) == "1111100110101"
    assert not bits[-16:].any()


def test_ida_e_volta() -> None:
    for pacote in (Pacote(0, b""), Pacote(65535, PAYLOAD_PROVA), Pacote(300, b"\x00" * 255)):
        leitura = quadro.interpretar(_corpo(pacote))
        assert leitura.situacao == "ok"
        assert leitura.pacote == pacote
        assert leitura.n_bits == quadro.bits_apos_sync(len(pacote.payload))


def test_bits_a_mais_depois_do_quadro_sao_ignorados() -> None:
    pacote = Pacote(42, b"abc")
    bits = np.concatenate([_corpo(pacote), np.ones(50, dtype=np.uint8)])
    assert quadro.interpretar(bits).pacote == pacote


def test_todo_erro_de_um_bit_e_detectado() -> None:
    corpo = _corpo(Pacote(1234, PAYLOAD_PROVA))
    assert len(corpo) == 1064  # comprimento 8 + sequência 16 + payload 1024 + CRC 16
    for k in range(len(corpo)):
        errado = corpo.copy()
        errado[k] ^= 1
        assert quadro.interpretar(errado).pacote is None, f"erro no bit {k} passou"


def test_amostra_de_erros_de_dois_e_tres_bits_e_detectada() -> None:
    # CRC-16/CCITT tem distância de Hamming 4 até 32 751 bits: detecta todo erro de até 3 bits
    corpo = _corpo(Pacote(1234, PAYLOAD_PROVA))
    rng = np.random.default_rng(20261104)
    for n_erros in (2, 3):
        for _ in range(500):
            errado = corpo.copy()
            errado[rng.choice(len(corpo), n_erros, replace=False)] ^= 1
            assert quadro.interpretar(errado).pacote is None


def test_erro_na_sequencia_e_no_comprimento_e_detectado() -> None:
    corpo = _corpo(Pacote(1000, b"dados"))
    for k in (0, 7, 8, 23):  # comprimento: bits 0 a 7; sequência: bits 8 a 23
        errado = corpo.copy()
        errado[k] ^= 1
        assert quadro.interpretar(errado).situacao in ("crc", "curto")


def test_bits_insuficientes() -> None:
    corpo = _corpo(Pacote(5, PAYLOAD_PROVA))
    assert quadro.interpretar(corpo[:10]).situacao == "curto"
    assert quadro.interpretar(corpo[:-1]).situacao == "curto"


def test_validacoes() -> None:
    with pytest.raises(ValueError, match="sequência"):
        Pacote(65536, b"")
    with pytest.raises(ValueError, match="payload"):
        Pacote(0, b"x" * 256)
    with pytest.raises(ValueError, match="payload"):
        quadro.bits_apos_sync(256)
    with pytest.raises(ValueError, match="bytes inteiros"):
        quadro.bits_para_bytes(np.ones(7, dtype=np.uint8))
