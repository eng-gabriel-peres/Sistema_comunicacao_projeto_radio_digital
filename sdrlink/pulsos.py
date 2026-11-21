"""Pulsos de formatação: retangular, cosseno levantado com raiz (RRC) e gaussiano.

Requisito: PUL-01 (formatação de pulso além da retangular, justificada pela
banda ocupada medida).

Convenção: os pulsos de símbolo (retangular e RRC) têm energia unitária,
sum(p**2) = 1, para que a saída do filtro casado no instante ótimo seja a
própria amplitude do símbolo. O pulso gaussiano é um pulso de frequência (2-FSK)
e tem área de um símbolo, sum(g) = sps, para que cada símbolo gire a fase o
mesmo que o pulso retangular de frequência.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

SPS_MIN = 2
SPS_MAX = 1024
SPAN_MAX = 32  # duração máxima do pulso, em símbolos
BT_MAX = 2.0  # acima disso o filtro gaussiano quase não suaviza


def _conferir(sps: int, span: int = 1) -> None:
    """Rejeita amostras por símbolo ou duração fora dos limites.

    Raises:
        ValueError: valores fora dos limites.
    """
    if not SPS_MIN <= sps <= SPS_MAX:
        raise ValueError(f"amostras por símbolo fora de {SPS_MIN} a {SPS_MAX}: {sps}")
    if not 1 <= span <= SPAN_MAX:
        raise ValueError(f"duração do pulso fora de 1 a {SPAN_MAX} símbolos: {span}")


def retangular(sps: int) -> NDArray[np.float64]:
    """Pulso retangular de um símbolo, com energia unitária."""
    _conferir(sps)
    return np.full(sps, 1 / np.sqrt(sps))


def rrc(beta: float, sps: int, span: int) -> NDArray[np.float64]:
    """Cosseno levantado com raiz (RRC), com span símbolos e energia unitária.

    No TX e no filtro casado do RX, o conjunto é um cosseno levantado: sem
    interferência entre símbolos e banda de (1 + beta) vezes a taxa de símbolos.

    Raises:
        ValueError: beta fora de (0, 1] ou sps/span inválidos.
    """
    _conferir(sps, span)
    if not 0 < beta <= 1:
        raise ValueError(f"fator de rolagem fora de (0, 1]: {beta}")
    t = (np.arange(span * sps + 1) - span * sps / 2) / sps  # em símbolos
    p = np.empty_like(t)
    centro = np.isclose(t, 0)
    singular = np.isclose(np.abs(t), 1 / (4 * beta))
    comum = ~(centro | singular)
    tc = t[comum]
    p[comum] = (
        np.sin(np.pi * tc * (1 - beta)) + 4 * beta * tc * np.cos(np.pi * tc * (1 + beta))
    ) / (np.pi * tc * (1 - (4 * beta * tc) ** 2))
    p[centro] = 1 - beta + 4 * beta / np.pi
    p[singular] = (beta / np.sqrt(2)) * (
        (1 + 2 / np.pi) * np.sin(np.pi / (4 * beta)) + (1 - 2 / np.pi) * np.cos(np.pi / (4 * beta))
    )
    return np.asarray(p / np.sqrt(np.sum(p**2)), dtype=np.float64)


def gaussiano(bt: float, sps: int, span: int) -> NDArray[np.float64]:
    """Pulso de frequência gaussiano da GFSK (produto banda-tempo bt), com área de um símbolo.

    É a resposta do filtro gaussiano a um pulso retangular de um símbolo.

    Raises:
        ValueError: bt fora de (0, 2] ou sps/span inválidos.
    """
    _conferir(sps, span)
    if not 0 < bt <= BT_MAX:
        raise ValueError(f"produto banda-tempo fora de (0, 2]: {bt}")
    t = (np.arange(span * sps + 1) - span * sps / 2) / sps  # em símbolos
    sigma = np.sqrt(np.log(2)) / (2 * np.pi * bt)  # desvio do filtro gaussiano, em símbolos
    h = np.exp(-(t**2) / (2 * sigma**2))
    g = np.convolve(h / h.sum(), np.ones(sps), mode="same")
    return g * sps / g.sum()
