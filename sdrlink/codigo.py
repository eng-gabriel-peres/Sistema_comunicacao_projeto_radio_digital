"""Código convolucional K = 7, taxa 1/2 (geradores 171 e 133 em octal) e decodificador de Viterbi.

Requisito: o enunciado (seção 7) permite FEC, com o custo dele no goodput. Usado na
prova B (alcance, bloco 09), em que o goodput mínimo de 10 kbit/s impede baixar mais
a taxa e só um código dá mais margem, e na reserva da prova A com DQPSK (bloco 11).

É o código padrão do CCSDS e da NASA desde as sondas Voyager: distância livre 10,
ganho de cerca de 5 dB sobre a BPSK sem código, com decisão suave, a BER de 1e-5.

Convenções:
    - o codificador começa e termina no estado zero: recebe n bits e devolve
      2 (n + 6) bits (6 zeros de cauda fecham a treliça);
    - os dois bits de saída de cada entrada vêm em sequência (G1, depois G2);
    - o decodificador recebe valores suaves, um por bit codificado, positivos
      quando o bit provável é 1 e com módulo proporcional à confiança. Decisão
      dura é o caso particular de valores +1 e -1.
"""

from __future__ import annotations

import functools
from typing import Any

import numpy as np
from numpy.typing import NDArray

RESTRICAO = 7  # comprimento de restrição K
MEMORIA = RESTRICAO - 1
ESTADOS = 2**MEMORIA  # 64
GERADORES = (0o171, 0o133)
TAXA_INVERSA = len(GERADORES)  # 2 bits codificados por bit de entrada
BITS_MAX = 1_000_000
LOTE_MAX = 256  # palavras por lote do Viterbi
DIMENSOES_LOTE = 2  # matriz de palavras × bits codificados


def _paridade(valor: int) -> int:
    """Paridade (XOR de todos os bits) de um inteiro não negativo."""
    return bin(valor).count("1") % 2


@functools.cache
def _trelica() -> tuple[NDArray[np.intp], NDArray[np.float64]]:
    """Antecessores de cada estado e os sinais (+1/-1) das duas saídas de cada ramo.

    Estado = os 6 últimos bits de entrada, o mais recente no bit 5. Com a entrada b
    no estado s, o registro completo é r = (b << 6) | s, as saídas são as paridades
    de r com cada gerador e o próximo estado é r >> 1. Cada próximo estado ns tem
    dois antecessores, (ns << 1) & 63 e ((ns << 1) & 63) | 1, ambos com b = ns >> 5.
    """
    antecessores = np.zeros((ESTADOS, 2), dtype=np.intp)
    sinais = np.zeros((ESTADOS, 2, TAXA_INVERSA))
    for proximo in range(ESTADOS):
        entrada = proximo >> (MEMORIA - 1)
        for k in range(2):
            estado = ((proximo << 1) & (ESTADOS - 1)) | k
            registro = (entrada << MEMORIA) | estado
            antecessores[proximo, k] = estado
            for g, gerador in enumerate(GERADORES):
                sinais[proximo, k, g] = 2.0 * _paridade(registro & gerador) - 1.0
    antecessores.setflags(write=False)
    sinais.setflags(write=False)
    return antecessores, sinais


def codificar(bits: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Bits codificados: 2 por bit de entrada, mais 12 da cauda que volta ao estado zero.

    Raises:
        ValueError: bits vazios, com valores diferentes de 0 e 1, ou longos demais.
    """
    if not 0 < len(bits) <= BITS_MAX or np.any(bits > 1):
        raise ValueError(f"esperada uma sequência de 1 a {BITS_MAX} bits 0 e 1")
    entrada = np.concatenate([bits.astype(np.int64), np.zeros(MEMORIA, dtype=np.int64)])
    # registro em cada instante: o bit atual no bit 6 e os 6 anteriores abaixo dele
    atrasados = np.concatenate([np.zeros(MEMORIA, dtype=np.int64), entrada])
    registro = np.zeros(len(entrada), dtype=np.int64)
    for atraso in range(RESTRICAO):
        registro |= atrasados[MEMORIA - atraso : MEMORIA - atraso + len(entrada)] << (
            MEMORIA - atraso
        )
    saida = np.zeros((len(entrada), TAXA_INVERSA), dtype=np.uint8)
    for g, gerador in enumerate(GERADORES):
        mascarado = registro & gerador
        paridade = np.zeros(len(entrada), dtype=np.int64)
        for bit in range(RESTRICAO):
            paridade ^= (mascarado >> bit) & 1
        saida[:, g] = paridade
    return saida.ravel()


def bits_codificados(n_bits: int) -> int:
    """Quantos bits o codificador produz para n_bits de entrada (com a cauda)."""
    return TAXA_INVERSA * (n_bits + MEMORIA)


def decodificar(suaves: NDArray[np.floating[Any]], n_bits: int) -> NDArray[np.uint8]:
    """Viterbi com decisão suave: os n_bits de entrada mais prováveis.

    Args:
        suaves: um valor por bit codificado (positivo = 1), pelo menos
            bits_codificados(n_bits) valores; os de sobra são ignorados.
        n_bits: bits de entrada a recuperar (sem a cauda).

    Raises:
        ValueError: n_bits inválido ou valores suaves de menos.
    """
    if not 0 < n_bits <= BITS_MAX:
        raise ValueError(f"quantidade de bits inválida: {n_bits}")
    if len(suaves) < bits_codificados(n_bits):
        raise ValueError(f"{len(suaves)} valores suaves; são precisos {bits_codificados(n_bits)}")
    lote = decodificar_lote(np.asarray(suaves)[None, : bits_codificados(n_bits)], n_bits)
    return np.asarray(lote[0], dtype=np.uint8)


def decodificar_lote(suaves: NDArray[np.floating[Any]], n_bits: int) -> NDArray[np.uint8]:
    """Viterbi de várias palavras do mesmo tamanho de uma vez (uma por linha de `suaves`).

    O laço é sobre os passos da treliça; em cada passo, os 64 estados de todas as
    palavras são atualizados na mesma operação do NumPy. Decodificar um quadro por vez
    deixava o laço em Python com só 64 estados por passo: na DQPSK com FEC a 1,4 Mbit/s
    o RX levava 6,9 s por segundo de captura (bloco 10). As palavras vão em lotes de
    até LOTE_MAX, para a memória das decisões (passos × lote × 64 bytes) ficar limitada.

    Raises:
        ValueError: n_bits inválido, matriz vazia ou com colunas de menos.
    """
    if not 0 < n_bits <= BITS_MAX:
        raise ValueError(f"quantidade de bits inválida: {n_bits}")
    matriz = np.asarray(suaves, dtype=np.float64)
    if (
        matriz.ndim != DIMENSOES_LOTE
        or len(matriz) == 0
        or matriz.shape[1] < bits_codificados(n_bits)
    ):
        raise ValueError(f"esperada uma matriz com {bits_codificados(n_bits)} colunas ou mais")
    partes = [
        _viterbi(matriz[k : k + LOTE_MAX, : bits_codificados(n_bits)], n_bits)
        for k in range(0, len(matriz), LOTE_MAX)
    ]
    return np.concatenate(partes)


def _viterbi(matriz: NDArray[np.float64], n_bits: int) -> NDArray[np.uint8]:
    """Viterbi de um lote: matriz (palavras × bits codificados) já conferida."""
    antecessores, sinais = _trelica()
    palavras = len(matriz)
    passos = n_bits + MEMORIA
    pares = matriz.reshape(palavras, passos, TAXA_INVERSA)
    ramos_por_par = sinais.reshape(ESTADOS * 2, TAXA_INVERSA).T  # (2, 128)
    metrica = np.full((palavras, ESTADOS), -np.inf)
    metrica[:, 0] = 0.0  # o codificador começa no estado zero
    decisoes = np.zeros((passos, palavras, ESTADOS), dtype=np.uint8)
    for t in range(passos):
        ramos = (pares[:, t, :] @ ramos_por_par).reshape(palavras, ESTADOS, 2)
        candidatos = metrica[:, antecessores] + ramos
        escolha = candidatos[:, :, 1] > candidatos[:, :, 0]
        decisoes[t] = escolha
        metrica = np.where(escolha, candidatos[:, :, 1], candidatos[:, :, 0])
        metrica -= metrica.max(axis=1, keepdims=True)  # evita crescer sem limite
    linhas = np.arange(palavras)
    estado = np.zeros(palavras, dtype=np.intp)  # a cauda leva o codificador de volta ao estado zero
    saida = np.zeros((palavras, passos), dtype=np.uint8)
    for t in range(passos - 1, -1, -1):
        saida[:, t] = estado >> (MEMORIA - 1)
        estado = antecessores[estado, decisoes[t, linhas, estado]]
    return saida[:, :n_bits]
