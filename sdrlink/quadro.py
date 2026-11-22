"""Quadro v3 do enlace: número de sequência de 24 bits e CRC-16.

Requisitos: PKT-01 (sequência, payload e verificação de integridade), PKT-02
(escolha do CRC justificada), PKT-03 (formato documentado em
docs/etapa3_quadro.md), PKT-04 (payload de 128 bytes da prova).

Formato (bits na ordem de transmissão, cada byte com o bit mais significativo
primeiro, como na referência):

    preâmbulo 16 | sync 13 | comprimento 8 | sequência 24 | payload 8N | CRC 16 | guarda 16

Diferenças em relação ao quadro da referência (achados A3 e A9):
    * campo de sequência, para PER e duplicatas: 16 bits no v2 (Etapa 3) e 24 bits no
      v3 (bloco 10), porque a 1,2 Mbit/s a de 16 bits dava a volta dentro dos 60 s;
    * CRC-16/CCITT-FALSE (polinômio 0x1021, valor inicial 0xFFFF) no lugar do
      CRC-8 com valor inicial 0;
    * o CRC cobre comprimento, sequência e payload: na referência só o payload
      era protegido, e um erro no cabeçalho passava sem ser detectado.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from sdrlink import codigo

Bits = NDArray[np.uint8]

PREAMBULO = np.array([1, 0] * 8, dtype=np.uint8)  # 16 bits alternados, para o limiar e o relógio
SYNC = np.array([1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1], dtype=np.uint8)  # Barker-13
GUARDA = np.zeros(16, dtype=np.uint8)  # silêncio entre quadros
BITS_COMPRIMENTO = 8
BITS_SEQUENCIA = 24  # quadro v3 (bloco 10); era 16 no v2
BYTES_SEQUENCIA = BITS_SEQUENCIA // 8
BITS_CRC = 16
PAYLOAD_MAX_BYTES: int = 2**BITS_COMPRIMENTO - 1  # 255
SEQUENCIA_MAX: int = 2**BITS_SEQUENCIA - 1
BITS_CABECALHO = BITS_COMPRIMENTO + BITS_SEQUENCIA  # depois do sync, antes do payload
PREFIXO = np.concatenate([PREAMBULO, SYNC])  # os bits conhecidos do início de todo quadro
PREFIXO.setflags(write=False)
BITS_PREFIXO = len(PREFIXO)  # 29
PAYLOAD_PROVA_BYTES = 128  # payload da competição (seção 12 do enunciado)

POLINOMIO_CRC16 = 0x1021  # CRC-16/CCITT-FALSE
INICIAL_CRC16 = 0xFFFF


def _tabela_crc16() -> tuple[int, ...]:
    """Tabela de 256 entradas do CRC-16 (calculada uma vez, na carga do módulo)."""
    tabela = []
    for byte in range(256):
        crc = byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ POLINOMIO_CRC16) if crc & 0x8000 else (crc << 1)
        tabela.append(crc & 0xFFFF)
    return tuple(tabela)


TABELA_CRC16 = _tabela_crc16()


def crc16(dados: bytes, inicial: int = INICIAL_CRC16) -> int:
    """CRC-16/CCITT-FALSE (valor de conferência para b"123456789": 0x29B1)."""
    crc = inicial
    for byte in dados:
        crc = ((crc << 8) & 0xFFFF) ^ TABELA_CRC16[(crc >> 8) ^ byte]
    return crc


@dataclass(frozen=True)
class Pacote:
    """Conteúdo útil de um quadro.

    Attributes:
        sequencia: número do pacote, de 0 a 2^24 - 1 (o TX volta a 0 depois do máximo).
        payload: dados úteis, de 0 a 255 bytes.
    """

    sequencia: int
    payload: bytes

    def __post_init__(self) -> None:
        """Rejeita valores que não cabem nos campos do quadro."""
        if not 0 <= self.sequencia <= SEQUENCIA_MAX:
            raise ValueError(f"sequência fora de 0 a {SEQUENCIA_MAX}: {self.sequencia}")
        if len(self.payload) > PAYLOAD_MAX_BYTES:
            raise ValueError(f"payload maior que {PAYLOAD_MAX_BYTES} bytes: {len(self.payload)}")


def bytes_para_bits(dados: bytes) -> Bits:
    """Bytes em bits, o mais significativo primeiro."""
    return np.unpackbits(np.frombuffer(dados, dtype=np.uint8))


def bits_para_bytes(bits: Bits) -> bytes:
    """Bits (múltiplo de 8, o mais significativo primeiro) em bytes.

    Raises:
        ValueError: quantidade de bits não múltipla de 8.
    """
    if len(bits) % 8:
        raise ValueError(f"{len(bits)} bits não formam bytes inteiros")
    return np.packbits(bits).tobytes()


def _protegido(pacote: Pacote) -> bytes:
    """Bytes cobertos pelo CRC: comprimento, sequência (big-endian) e payload."""
    sequencia = pacote.sequencia.to_bytes(BYTES_SEQUENCIA, "big")
    return bytes([len(pacote.payload)]) + sequencia + pacote.payload


def montar_quadro(pacote: Pacote, fec: bool = False) -> Bits:
    """Bits completos de um quadro, do preâmbulo à guarda.

    Com fec, o que vem depois do sync (comprimento, sequência, payload e CRC) passa
    pelo código convolucional de sdrlink.codigo; preâmbulo, sync e guarda não mudam,
    para a detecção do RX ser a mesma com e sem código.
    """
    protegido = _protegido(pacote)
    corpo = bytes_para_bits(protegido + crc16(protegido).to_bytes(2, "big"))
    if fec:
        corpo = codigo.codificar(corpo)
    return np.concatenate([PREAMBULO, SYNC, corpo, GUARDA])


def bits_apos_sync(n_bytes_payload: int) -> int:
    """Quantos bits o RX precisa ler depois do sync para um payload desse tamanho.

    Raises:
        ValueError: tamanho fora de 0 a 255.
    """
    if not 0 <= n_bytes_payload <= PAYLOAD_MAX_BYTES:
        raise ValueError(f"payload fora de 0 a {PAYLOAD_MAX_BYTES} bytes: {n_bytes_payload}")
    return BITS_CABECALHO + 8 * n_bytes_payload + BITS_CRC


@dataclass(frozen=True)
class Leitura:
    """Resultado de interpretar os bits que vêm depois do sync.

    Attributes:
        pacote: o pacote, só quando o CRC confere.
        situacao: "ok", "crc" (CRC não confere) ou "curto" (faltam bits).
        n_bits: bits consumidos depois do sync (0 se "curto").
    """

    pacote: Pacote | None
    situacao: str
    n_bits: int


def interpretar(bits: Bits) -> Leitura:
    """Lê comprimento, sequência, payload e CRC a partir do primeiro bit depois do sync.

    O comprimento só é confiável depois de conferido o CRC; se ele vier errado,
    o CRC calculado sobre o tamanho errado não confere e o quadro é rejeitado.
    """
    if len(bits) < BITS_CABECALHO:
        return Leitura(None, "curto", 0)
    n_bytes = int(bits_para_bytes(bits[:BITS_COMPRIMENTO])[0])
    total = bits_apos_sync(n_bytes)
    if len(bits) < total:
        return Leitura(None, "curto", 0)
    corpo = bits_para_bytes(bits[:total])
    protegido, crc_recebido = corpo[:-2], int.from_bytes(corpo[-2:], "big")
    if crc16(protegido) != crc_recebido:
        return Leitura(None, "crc", total)
    fim_sequencia = 1 + BYTES_SEQUENCIA
    pacote = Pacote(int.from_bytes(protegido[1:fim_sequencia], "big"), protegido[fim_sequencia:])
    return Leitura(pacote, "ok", total)


def bits_no_ar_apos_sync(n_bytes_payload: int, fec: bool = False) -> int:
    """Bits transmitidos depois do sync: os de bits_apos_sync, ou os codificados com fec.

    Raises:
        ValueError: tamanho fora de 0 a 255.
    """
    n = bits_apos_sync(n_bytes_payload)
    return codigo.bits_codificados(n) if fec else n


def bits_por_quadro(n_bytes_payload: int, fec: bool = False) -> int:
    """Tamanho do quadro completo em bits (1117 para os 128 bytes da prova; 2201 com fec)."""
    depois = bits_no_ar_apos_sync(n_bytes_payload, fec)
    return len(PREAMBULO) + len(SYNC) + depois + len(GUARDA)
