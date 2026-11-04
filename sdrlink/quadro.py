"""Quadro v2 do enlace: número de sequência de 16 bits e CRC-16.

Requisitos: PKT-01 (sequência, payload e verificação de integridade), PKT-02
(escolha do CRC justificada), PKT-03 (formato documentado em
docs/etapa3_quadro.md), PKT-04 (payload de 128 bytes da prova).

Formato (bits na ordem de transmissão, cada byte com o bit mais significativo
primeiro, como na referência):

    preâmbulo 16 | sync 13 | comprimento 8 | sequência 16 | payload 8N | CRC 16 | guarda 16

Diferenças em relação ao quadro da referência (achados A3 e A9):
    * campo de sequência de 16 bits, para PER e duplicatas;
    * CRC-16/CCITT-FALSE (polinômio 0x1021, valor inicial 0xFFFF) no lugar do
      CRC-8 com valor inicial 0;
    * o CRC cobre comprimento, sequência e payload: na referência só o payload
      era protegido, e um erro no cabeçalho passava sem ser detectado.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Bits = NDArray[np.uint8]

PREAMBULO = np.array([1, 0] * 8, dtype=np.uint8)  # 16 bits alternados, para o limiar e o relógio
SYNC = np.array([1, 1, 1, 1, 1, 0, 0, 1, 1, 0, 1, 0, 1], dtype=np.uint8)  # Barker-13
GUARDA = np.zeros(16, dtype=np.uint8)  # silêncio entre quadros
BITS_COMPRIMENTO = 8
BITS_SEQUENCIA = 16
BITS_CRC = 16
PAYLOAD_MAX_BYTES = 2**BITS_COMPRIMENTO - 1  # 255
SEQUENCIA_MAX = 2**BITS_SEQUENCIA - 1
BITS_CABECALHO = BITS_COMPRIMENTO + BITS_SEQUENCIA  # depois do sync, antes do payload

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
        sequencia: número do pacote, de 0 a 65535 (o TX volta a 0 depois do máximo).
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
    return bytes([len(pacote.payload)]) + pacote.sequencia.to_bytes(2, "big") + pacote.payload


def montar_quadro(pacote: Pacote) -> Bits:
    """Bits completos de um quadro, do preâmbulo à guarda."""
    protegido = _protegido(pacote)
    corpo = protegido + crc16(protegido).to_bytes(2, "big")
    return np.concatenate([PREAMBULO, SYNC, bytes_para_bits(corpo), GUARDA])


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
    pacote = Pacote(int.from_bytes(protegido[1:3], "big"), protegido[3:])
    return Leitura(pacote, "ok", total)


def bits_por_quadro(n_bytes_payload: int) -> int:
    """Tamanho do quadro completo em bits (1109 para os 128 bytes da prova)."""
    return len(PREAMBULO) + len(SYNC) + bits_apos_sync(n_bytes_payload) + len(GUARDA)
