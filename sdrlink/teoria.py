"""BER teórica em AWGN das modulações do projeto, em função de Eb/N0.

Requisito: Etapa 4 (curvas BER × Eb/N0 simuladas comparadas às teóricas).

Todas as fórmulas usam Eb médio por bit, a mesma definição de sdrlink.canal:
    BPSK coerente        Q(sqrt(2 Eb/N0))
    DBPSK diferencial    1/2 exp(-Eb/N0)
    DQPSK diferencial    Gray: Q1(a, b) - 1/2 I0(a b) exp(-(a² + b²)/2), com
                         a² = 2 Eb/N0 (1 - 1/sqrt 2) e b² = 2 Eb/N0 (1 + 1/sqrt 2)
    2-FSK não coerente   1/2 exp(-Eb/(2 N0))          (tons ortogonais, h = 1)
    2-FSK coerente       Q(sqrt(Eb/N0))               (só referência: não implementada)
    OOK não coerente     exata, detector de envoltória com limiar T:
                         1/2 [exp(-T²/(2 s²)) + 1 - Q1(A/s, T/s)], com A² = E1 = 2 Eb
                         (energia do "1"), s² = N0/2 e Q1 a função Q de Marcum; duas
                         versões: limiar na metade da amplitude e limiar ótimo. O
                         demodulador do projeto ajusta o limiar pelos dados (k-médias) e
                         fica entre as duas.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.integrate import quad
from scipy.optimize import minimize_scalar
from scipy.special import erfc, i0e
from scipy.stats import ncx2


def _linear(ebn0_db: ArrayLike) -> NDArray[np.float64]:
    """Eb/N0 de dB para razão linear."""
    return np.asarray(10 ** (np.asarray(ebn0_db, dtype=np.float64) / 10), dtype=np.float64)


def q(x: ArrayLike) -> NDArray[np.float64]:
    """Função Q gaussiana: probabilidade de uma normal padrão passar de x."""
    return np.asarray(0.5 * erfc(np.asarray(x, dtype=np.float64) / np.sqrt(2)), dtype=np.float64)


def ber_bpsk(ebn0_db: ArrayLike, erro_fase_rad: float = 0.0) -> NDArray[np.float64]:
    """BPSK coerente; com erro de fase fixo phi a amplitude útil cai para cos(phi)."""
    return q(np.sqrt(2 * _linear(ebn0_db)) * np.cos(erro_fase_rad))


def ber_dbpsk(ebn0_db: ArrayLike) -> NDArray[np.float64]:
    """DBPSK com detecção diferencial."""
    return np.asarray(0.5 * np.exp(-_linear(ebn0_db)), dtype=np.float64)


def ber_dqpsk(ebn0_db: ArrayLike) -> NDArray[np.float64]:
    """DQPSK com mapa de Gray e detecção diferencial (exata, com a função Q de Marcum).

    Q1(a, b) = ncx2.sf(b², 2, a²); I0 entra escalado (i0e) para não estourar em Eb/N0 alto.
    """
    g = _linear(ebn0_db)
    a = np.sqrt(2 * g * (1 - 1 / np.sqrt(2)))
    b = np.sqrt(2 * g * (1 + 1 / np.sqrt(2)))
    marcum = ncx2.sf(b**2, 2, a**2)
    return np.asarray(marcum - 0.5 * i0e(a * b) * np.exp(-((a - b) ** 2) / 2), dtype=np.float64)


GRAY_8PSK = (0, 1, 3, 2, 7, 6, 4, 5)  # o mesmo de sdrlink.modem (o teste confere)


def _densidade_da_fase(theta: float, es_n0: float) -> float:
    """Densidade da fase recebida de um ponto de PSK em ruído branco, com Es/N0 linear.

    e^(−γ)·e^(γ cos²θ) escrito como e^(−γ sen²θ): sem estouro em Eb/N0 alto (antes
    estourava acima de 24 dB), e erfc(−x) no lugar de 1 + erf(x).
    """
    c, s = np.cos(theta), np.sin(theta)
    raiz = np.sqrt(es_n0)
    return float(
        (np.exp(-es_n0) + np.sqrt(np.pi) * raiz * c * np.exp(-es_n0 * s**2) * erfc(-raiz * c))
        / (2 * np.pi)
    )


def _ber_8psk_um(ebn0_db: float) -> float:
    """BER exata da 8-PSK com Gray: probabilidade de cada setor de 45° × bits trocados."""
    es_n0 = 3 * float(_linear(ebn0_db))
    bits = np.argsort(GRAY_8PSK)  # os 3 bits de cada índice de fase
    total = 0.0
    for j in range(1, 8):  # setor j: a fase caiu j·45° adiante
        setor, _ = quad(
            _densidade_da_fase, (2 * j - 1) * np.pi / 8, (2 * j + 1) * np.pi / 8, args=(es_n0,)
        )
        trocados = np.mean(
            [bin(int(bits[i]) ^ int(bits[(i + j) % 8])).count("1") for i in range(8)]
        )
        total += setor * float(trocados)
    return total / 3


def ber_8psk(ebn0_db: ArrayLike) -> NDArray[np.float64]:
    """8-PSK coerente com Gray (exata, por integração da densidade da fase em cada setor).

    Com o mapa de Gray os erros vão quase sempre para um ponto vizinho, que troca um bit
    só: a aproximação (2/3)·Q(sqrt(6 Eb/N0)·sen(π/8)) coincide com a exata a 0,01% em 6 dB.
    """
    valores = [_ber_8psk_um(float(e)) for e in np.atleast_1d(ebn0_db).ravel()]
    return np.asarray(valores, dtype=np.float64).reshape(np.shape(ebn0_db))


def ber_fsk_nao_coerente(ebn0_db: ArrayLike) -> NDArray[np.float64]:
    """2-FSK ortogonal com detecção não coerente."""
    return np.asarray(0.5 * np.exp(-_linear(ebn0_db) / 2), dtype=np.float64)


def ber_fsk_coerente(ebn0_db: ArrayLike) -> NDArray[np.float64]:
    """2-FSK ortogonal com detecção coerente (limite de referência)."""
    return q(np.sqrt(_linear(ebn0_db)))


def _ber_ook_limiar(t2: float, e1_n0: float) -> float:
    """BER da OOK não coerente para o limiar T, com t2 = T²/s² e e1_n0 = E1/N0."""
    erro_0 = np.exp(-t2 / 2)  # ruído (Rayleigh) passa do limiar
    erro_1 = ncx2.cdf(t2, 2, 2 * e1_n0)  # sinal + ruído (Rice) fica abaixo: 1 - Q1
    return float(0.5 * (erro_0 + erro_1))


def ber_ook_nao_coerente(ebn0_db: ArrayLike, limiar: str = "otimo") -> NDArray[np.float64]:
    """OOK com detector de envoltória (exata), com limiar "otimo" ou no "meio" da amplitude.

    Raises:
        ValueError: tipo de limiar desconhecido.
    """
    if limiar not in ("otimo", "meio"):
        raise ValueError(f"limiar deve ser 'otimo' ou 'meio': {limiar}")
    resultado = []
    for e1_n0 in np.atleast_1d(2 * _linear(ebn0_db)):  # E1 = 2 Eb
        if limiar == "meio":
            resultado.append(_ber_ook_limiar(e1_n0 / 2, e1_n0))  # T = A/2: T²/s² = E1/(2 N0)
            continue
        busca = minimize_scalar(
            lambda t2, e=e1_n0: _ber_ook_limiar(t2, e), bounds=(1e-9, 4 * e1_n0), method="bounded"
        )
        resultado.append(float(busca.fun))
    return np.asarray(resultado, dtype=np.float64).reshape(np.shape(ebn0_db))


BER_TEORICA: dict[str, Callable[[ArrayLike], NDArray[np.float64]]] = {
    "ook": ber_ook_nao_coerente,
    "bpsk": ber_bpsk,
    "dbpsk": ber_dbpsk,
    "dqpsk": ber_dqpsk,
    "8psk": ber_8psk,
    "fsk": ber_fsk_nao_coerente,
}
