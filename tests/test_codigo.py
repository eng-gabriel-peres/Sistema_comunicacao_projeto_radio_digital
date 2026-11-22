"""Testes do código convolucional e do decodificador de Viterbi (sdrlink.codigo)."""

import itertools

import numpy as np
import pytest
from scipy.special import erfc

from sdrlink import codigo


def _codificar_direto(bits: np.ndarray) -> np.ndarray:
    """Referência bit a bit: registro de deslocamento, paridade com cada gerador."""
    estado, saida = 0, []
    for b in [*bits.tolist(), 0, 0, 0, 0, 0, 0]:
        registro = (int(b) << 6) | estado
        saida += [bin(registro & g).count("1") % 2 for g in codigo.GERADORES]
        estado = registro >> 1
    return np.array(saida, dtype=np.uint8)


@pytest.mark.parametrize("n", [1, 2, 7, 64, 1070])
def test_codificador_igual_a_referencia_bit_a_bit(n: int) -> None:
    bits = np.random.default_rng(n).integers(0, 2, n).astype(np.uint8)
    codificado = codigo.codificar(bits)
    assert np.array_equal(codificado, _codificar_direto(bits))
    assert len(codificado) == codigo.bits_codificados(n) == 2 * (n + 6)


def test_resposta_ao_impulso_tem_peso_10() -> None:
    # resposta do 171/133 a um único 1: 7 pares de saída com peso 10, a distância livre do código
    impulso = codigo.codificar(np.array([1], dtype=np.uint8))
    assert impulso.reshape(-1, 2).tolist() == [
        [1, 1],
        [1, 0],
        [1, 1],
        [1, 1],
        [0, 0],
        [0, 1],
        [1, 1],
    ]
    assert int(impulso.sum()) == 10


def test_ida_e_volta_sem_ruido_e_valores_sobrando_ignorados() -> None:
    bits = np.random.default_rng(1).integers(0, 2, 1070).astype(np.uint8)
    suaves = 2.0 * codigo.codificar(bits) - 1
    sobrando = np.concatenate([suaves, np.random.default_rng(2).standard_normal(500)])
    assert np.array_equal(codigo.decodificar(sobrando, 1070), bits)


def test_corrige_erros_duros_espalhados() -> None:
    rng = np.random.default_rng(3)
    bits = rng.integers(0, 2, 1070).astype(np.uint8)
    duros = np.asarray(2.0 * codigo.codificar(bits) - 1, dtype=np.float64)
    duros[np.arange(5, len(duros), 25)] *= -1  # 86 bits trocados, um a cada 25
    assert np.array_equal(codigo.decodificar(duros, 1070), bits)


def test_ber_com_decisao_suave_bate_com_a_curva_do_codigo() -> None:
    # K = 7, taxa 1/2, decisão suave: BER perto de 4e-4 a 3 dB (sem código, a BPSK dá 2,3e-2)
    rng = np.random.default_rng(4)
    ebn0 = 10 ** (3.0 / 10)
    sigma = float(np.sqrt(1 / (2 * 0.5 * ebn0)))  # cada bit codificado leva metade do Eb
    erros = total = 0
    for _ in range(60):
        bits = rng.integers(0, 2, 1070).astype(np.uint8)
        x = 2.0 * codigo.codificar(bits) - 1
        erros += int(
            np.sum(codigo.decodificar(x + sigma * rng.standard_normal(len(x)), 1070) != bits)
        )
        total += 1070
    sem_codigo = 0.5 * erfc(np.sqrt(ebn0))
    assert 5e-5 < erros / total < 2e-3 < sem_codigo / 10


def test_entradas_invalidas() -> None:
    with pytest.raises(ValueError, match="sequência"):
        codigo.codificar(np.array([], dtype=np.uint8))
    with pytest.raises(ValueError, match="sequência"):
        codigo.codificar(np.array([0, 2], dtype=np.uint8))
    with pytest.raises(ValueError, match="quantidade"):
        codigo.decodificar(np.zeros(20), 0)
    with pytest.raises(ValueError, match="são precisos"):
        codigo.decodificar(np.zeros(20), 10)


def test_palavra_de_um_bit_corrige_quaisquer_4_erros() -> None:
    # com início e fim no estado zero, 1 bit de entrada só tem duas palavras possíveis, a
    # distância 10 uma da outra: qualquer combinação de até 4 bits errados entre os 14 é
    # corrigida. Sem impor o estado inicial ou o final, centenas dessas combinações falham.
    for bit in (0, 1):
        palavra = np.asarray(2.0 * codigo.codificar(np.array([bit], dtype=np.uint8)) - 1)
        for posicoes in itertools.combinations(range(len(palavra)), 4):
            recebido = palavra.copy()
            recebido[list(posicoes)] *= -1
            assert codigo.decodificar(recebido, 1)[0] == bit, posicoes
