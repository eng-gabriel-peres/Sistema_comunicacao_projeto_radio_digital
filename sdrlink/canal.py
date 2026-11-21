"""Canal simulado: ruído branco gaussiano (AWGN) com Eb/N0 definido.

Requisito: Etapa 4 (BER × Eb/N0 simulada contra a teoria); usado já na Etapa 3
para validar a cadeia completa com ruído.

Definição: Eb é a energia média por bit do sinal transmitido, medida no próprio
sinal (potência média × amostras por bit). O ruído complexo tem variância N0 por
amostra (N0/2 em cada componente). Com os pulsos de energia unitária de
sdrlink.pulsos, isso reproduz as fórmulas de BER clássicas, por exemplo
Q(sqrt(2 Eb/N0)) na BPSK coerente.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

EBN0_MIN_DB = -20.0
EBN0_MAX_DB = 60.0


def awgn(
    sinal: NDArray[np.complex128],
    ebn0_db: float,
    amostras_por_bit: int,
    rng: np.random.Generator,
) -> NDArray[np.complex128]:
    """Soma ruído branco gaussiano complexo para o Eb/N0 pedido.

    Raises:
        ValueError: sinal vazio ou sem potência, Eb/N0 ou amostras por bit inválidos.
    """
    if len(sinal) == 0:
        raise ValueError("sinal vazio")
    if not EBN0_MIN_DB <= ebn0_db <= EBN0_MAX_DB:
        raise ValueError(f"Eb/N0 fora de {EBN0_MIN_DB} a {EBN0_MAX_DB} dB: {ebn0_db}")
    if amostras_por_bit < 1:
        raise ValueError(f"amostras por bit inválidas: {amostras_por_bit}")
    potencia = float(np.mean(np.abs(sinal) ** 2))
    if potencia == 0:
        raise ValueError("sinal sem potência")
    n0 = potencia * amostras_por_bit / 10 ** (ebn0_db / 10)
    ruido = rng.standard_normal(len(sinal)) + 1j * rng.standard_normal(len(sinal))
    return np.asarray(sinal + np.sqrt(n0 / 2) * ruido, dtype=np.complex128)
