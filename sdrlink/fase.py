"""Ruído de fase do par Pluto + RTL, medido na gravação de um tom.

Requisito: robustez do enlace às imperfeições do hardware (Etapas 4 e 6). Feito no
bloco 21, com as gravações reais do tom do Pluto da equipe de 04/11/2026.

Os receptores diferenciais (DBPSK e DQPSK) decidem pela variação de fase de um símbolo
para o seguinte. O que importa do ruído de fase dos osciladores é, portanto, quanto a
fase anda em um símbolo além do que o offset de frequência explica. Este módulo mede
isso num tom: mistura o tom para zero, filtra (o ruído branco de fora da banda sai),
desdobra a fase e calcula o valor eficaz da variação de fase em τ amostras, com o offset
de cada trecho curto retirado (o RX estima o offset em cada quadro). Mede também o
espectro L(f) em dBc/Hz em volta do tom.

Gravações feitas antes da leitura assíncrona (achado A17) têm saltos de fase nas emendas
de leitura: os trechos em volta de cada salto ficam fora da conta.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from numpy.typing import NDArray
from scipy import signal

BANDA_PADRAO_HZ = 50e3  # acima disso o tom real some no piso branco (bloco 21)
SALTO_RAD = 0.3  # salto mínimo; com ruído de fase forte o limiar sobe (SALTO_DESVIOS)
SALTO_DESVIOS = 8.0  # o limiar também fica a 8 desvios robustos da variação: ruído não passa
ATRASO_SALTO = 64  # o filtro espalha um salto por cerca de 40 amostras: olha a variação em 64
COEFICIENTES = 255  # filtro passa-baixas (ímpar); também a margem excluída em volta de um salto
SEGMENTO = 2**15  # trecho com offset próprio (16 ms a 2,048 MS/s, menos que um quadro)
AMOSTRAS_MIN = 2**16
TRECHO_MIN = 2**14  # trecho sem salto que entra na trajetória (8 ms a 2,048 MS/s)
NPERSEG = 2**16  # Welch: 31 Hz de resolução a 2,048 MS/s
DC_EXCLUIDO_HZ = 5e3  # o pico de DC do RTL não é o tom
TOM_MEIA_LARGURA_HZ = 500.0  # potência do tom: soma em ±500 Hz


@dataclass(frozen=True)
class FaseDoTom:
    """Fase de um tom gravado.

    Attributes:
        fase: fase desdobrada (rad), sem a rampa da frequência média.
        validas: amostras longe de saltos e das bordas do filtro.
        freq_hz: frequência média do tom na gravação.
        saltos: emendas com salto de fase encontradas.
        taxa_sps: taxa da gravação.
    """

    fase: NDArray[np.float64]
    validas: NDArray[np.bool_]
    freq_hz: float
    saltos: int
    taxa_sps: float


def _validar(amostras: NDArray[np.complexfloating], taxa_sps: float) -> None:
    if len(amostras) < AMOSTRAS_MIN or taxa_sps <= 0:
        raise ValueError(f"gravação curta demais ({len(amostras)} amostras) ou taxa inválida")


def _espectro(
    amostras: NDArray[np.complexfloating], taxa_sps: float
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Densidade espectral (Welch, dois lados), com as frequências em ordem crescente."""
    f, p = signal.welch(amostras, taxa_sps, nperseg=NPERSEG, return_onesided=False)
    return np.fft.fftshift(f), np.fft.fftshift(p)


def frequencia_do_tom(amostras: NDArray[np.complexfloating], taxa_sps: float) -> float:
    """Frequência (Hz, em banda base) do pico do espectro, fora do DC.

    Raises:
        ValueError: gravação curta demais ou taxa inválida.
    """
    _validar(amostras, taxa_sps)
    f, p = _espectro(amostras, taxa_sps)
    return float(f[np.argmax(np.where(np.abs(f) > DC_EXCLUIDO_HZ, p, 0.0))])


def fase_do_tom(
    amostras: NDArray[np.complexfloating], taxa_sps: float, banda_hz: float = BANDA_PADRAO_HZ
) -> FaseDoTom:
    """Fase do tom: misturado para zero, filtrado em ±banda_hz e desdobrado.

    Raises:
        ValueError: gravação curta demais, taxa ou banda inválidas.
    """
    _validar(amostras, taxa_sps)
    if not 0 < banda_hz < taxa_sps / 2:
        raise ValueError(f"banda inválida: {banda_hz} Hz")
    f0 = frequencia_do_tom(amostras, taxa_sps)
    n = len(amostras)
    misturado = np.asarray(amostras, dtype=np.complex128) * np.exp(
        -2j * np.pi * f0 * np.arange(n) / taxa_sps
    )
    filtrado = signal.filtfilt(signal.firwin(COEFICIENTES, banda_hz, fs=taxa_sps), 1.0, misturado)
    fase = np.unwrap(np.angle(filtrado))
    mediana = float(np.median(np.diff(fase)))
    variacao = fase[ATRASO_SALTO:] - fase[:-ATRASO_SALTO] - mediana * ATRASO_SALTO
    desvio = np.abs(variacao - np.median(variacao))
    limiar = max(SALTO_RAD, SALTO_DESVIOS * 1.4826 * float(np.median(desvio)))  # MAD → desvio
    indices = np.flatnonzero(desvio > limiar)
    validas = np.ones(n, dtype=bool)
    validas[:COEFICIENTES] = validas[-COEFICIENTES:] = False
    margem = COEFICIENTES + ATRASO_SALTO
    for i in indices:  # no máximo n - ATRASO_SALTO
        validas[max(0, i - margem) : i + margem + 1] = False
    saltos = int(np.sum(np.diff(indices) > margem)) + 1 if len(indices) else 0
    return FaseDoTom(
        fase=np.asarray(fase - mediana * np.arange(n), dtype=np.float64),
        validas=validas,
        freq_hz=f0 + mediana * taxa_sps / (2 * np.pi),
        saltos=saltos,
        taxa_sps=taxa_sps,
    )


def variacao_de_fase_rad(tom: FaseDoTom, atraso: int) -> float:
    """Valor eficaz da variação de fase em `atraso` amostras, sem o offset de cada trecho.

    Em cada trecho de SEGMENTO amostras retira a média da variação (o offset de
    frequência do trecho, que o RX estima por quadro) e só usa pares de amostras válidas.

    Raises:
        ValueError: atraso fora de 1 a SEGMENTO - 1, ou nenhum par válido.
    """
    if not 0 < atraso < SEGMENTO:
        raise ValueError(f"atraso fora de 1 a {SEGMENTO - 1}: {atraso}")
    variacao = tom.fase[atraso:] - tom.fase[:-atraso]
    ok = tom.validas[atraso:] & tom.validas[:-atraso]
    trechos = len(variacao) // SEGMENTO
    v = variacao[: trechos * SEGMENTO].reshape(trechos, SEGMENTO)
    m = ok[: trechos * SEGMENTO].reshape(trechos, SEGMENTO)
    uteis = m.sum(axis=1) > SEGMENTO // 2  # trechos com metade ou mais de pares válidos
    if not np.any(uteis):
        raise ValueError("nenhum trecho sem salto de fase")
    v, m = v[uteis], m[uteis]
    medias = np.sum(v * m, axis=1) / np.sum(m, axis=1)
    desvios = (v - medias[:, None])[m]
    return float(np.sqrt(np.mean(desvios**2)))


def ruido_de_fase_dbc_hz(
    amostras: NDArray[np.complexfloating], taxa_sps: float, afastamentos_hz: tuple[float, ...]
) -> dict[float, float]:
    """L(f): densidade a f Hz acima do tom (média em ±10% de f), relativa à potência do tom.

    Raises:
        ValueError: gravação curta demais, taxa inválida ou afastamento fora do espectro.
    """
    _validar(amostras, taxa_sps)
    f, p = _espectro(amostras, taxa_sps)
    f0 = float(f[np.argmax(np.where(np.abs(f) > DC_EXCLUIDO_HZ, p, 0.0))])
    df = float(f[1] - f[0])
    potencia_tom = float(np.sum(p[np.abs(f - f0) <= TOM_MEIA_LARGURA_HZ]) * df)
    resultado = {}
    for afastamento in afastamentos_hz:
        janela = np.abs(f - f0 - afastamento) <= 0.1 * afastamento
        if afastamento <= 0 or not np.any(janela):
            raise ValueError(f"afastamento fora do espectro: {afastamento} Hz")
        resultado[afastamento] = float(10 * np.log10(np.mean(p[janela]) / potencia_tom))
    return resultado


def largura_equivalente_hz(variacao_rad: float, atraso: int, taxa_sps: float) -> float:
    """Largura de linha de Wiener que daria essa variação de fase em `atraso` amostras.

    No modelo de Wiener a variância da variação em τ segundos é 2π·Δν·τ.
    """
    return variacao_rad**2 / (2 * np.pi * atraso / taxa_sps)


def variacao_do_ruido_branco_rad(
    piso_dbc_hz: float, atraso: int, taxa_sps: float, banda_hz: float = BANDA_PADRAO_HZ
) -> float:
    """Parte da variação de fase medida que vem do ruído branco da própria gravação.

    Com o piso N0 (relativo à potência do tom) e o filtro de fase_do_tom (ida e volta,
    resposta h_ef com autocorrelação R), a fase do tom ganha um ruído com variância
    N0·taxa·R(0)/2 e correlação R(τ)/R(0): a variação em τ amostras tem variância
    N0·taxa·(R(0) − R(τ)). É o que se desconta da medida.

    Raises:
        ValueError: atraso, taxa ou banda inválidos.
    """
    if atraso <= 0 or taxa_sps <= 0 or not 0 < banda_hz < taxa_sps / 2:
        raise ValueError(
            f"parâmetros inválidos: atraso={atraso}, taxa={taxa_sps}, banda={banda_hz}"
        )
    h = signal.firwin(COEFICIENTES, banda_hz, fs=taxa_sps)
    h_ef = np.convolve(h, h[::-1])
    r0 = float(np.sum(h_ef**2))
    r_tau = float(np.sum(h_ef[:-atraso] * h_ef[atraso:])) if atraso < len(h_ef) else 0.0
    return float(np.sqrt(10 ** (piso_dbc_hz / 10) * taxa_sps * (r0 - r_tau)))


def descontar(medida_rad: float, branco_rad: float) -> float:
    """Variação só do ruído de fase: a medida sem a parte do ruído branco (somas de variâncias)."""
    return float(np.sqrt(max(0.0, medida_rad**2 - branco_rad**2)))


def trajetoria(tom: FaseDoTom, n: int) -> NDArray[np.float64]:
    """Trajetória de fase medida, com n amostras, para aplicar a um sinal simulado.

    Junta os trechos sem salto (cada um sem a própria rampa de frequência, que o RX
    trata como offset), um depois do outro e sem degrau, e repete o conjunto se precisar.

    Raises:
        ValueError: n inválido ou nenhum trecho de TRECHO_MIN amostras sem salto.
    """
    if n <= 0:
        raise ValueError(f"tamanho inválido: {n}")
    mudancas = np.flatnonzero(np.diff(tom.validas.astype(np.int8))) + 1
    limites = np.concatenate([[0], mudancas, [len(tom.validas)]])
    pedacos = []
    ultimo = 0.0
    for a, b in pairwise(limites):  # no máximo len(validas) trechos
        if not tom.validas[a] or b - a < TRECHO_MIN:
            continue
        t = np.arange(b - a, dtype=np.float64)
        trecho = tom.fase[a:b] - np.polyval(np.polyfit(t, tom.fase[a:b], 1), t)
        pedacos.append(trecho - trecho[0] + ultimo)
        ultimo = float(pedacos[-1][-1])
    if not pedacos:
        raise ValueError(f"nenhum trecho de {TRECHO_MIN} amostras sem salto de fase")
    base = np.concatenate(pedacos)
    saida = [base]
    for _ in range(-(-n // len(base)) - 1):  # repete o conjunto, sem degrau
        saida.append(base - base[0] + saida[-1][-1])
    return np.asarray(np.concatenate(saida)[:n], dtype=np.float64)
