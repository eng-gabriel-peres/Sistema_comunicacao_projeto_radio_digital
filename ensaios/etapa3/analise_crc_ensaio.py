"""Compara a detecção de erros do CRC-8 da referência com o CRC-16 e o CRC-32 no quadro de 128 bytes.

Evidência do requisito PKT-02 (justificar a escolha do CRC).

Método exato: o CRC é linear, então um padrão de erro e passa sem ser detectado
quando crc0(erro nos dados) XOR (erro no campo do CRC) = 0, onde crc0 é o CRC
com valor inicial 0 (o valor inicial só soma uma constante, que se cancela).
Cada bit do quadro tem uma "síndrome": o resto x^e mod g para um bit de dado, o
próprio bit para o campo do CRC, e 0 para um bit que o CRC não cobre. Um erro
de w bits passa quando o XOR das w síndromes é 0. Isso permite contar TODOS os
erros de 1, 2 e 3 bits, sem amostragem. Para 4 a 8 bits e rajadas, Monte Carlo.

Os três casos usam o mesmo cabeçalho do quadro v2 (comprimento 8 + sequência 16)
e payload de 128 bytes:
    A. CRC-8 (0x07, como na referência), cobrindo só o payload;
    B. CRC-16/CCITT (0x1021), cobrindo cabeçalho e payload (sdrlink.quadro);
    C. CRC-32 (0x04C11DB7), cobrindo cabeçalho e payload.

Uso: python ensaios/etapa3/analise_crc_ensaio.py
"""

import bisect
import collections
import json
import sys
from pathlib import Path

import numpy as np

from sdrlink import quadro
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
BITS_CAB = 24
BITS_PAYLOAD = 1024
SEMENTE = 20261104
N_MONTE_CARLO = 200_000

CASOS = {
    "A: CRC-8 so no payload (referencia)": {"largura": 8, "poli": 0x07, "cobre_cabecalho": False},
    "B: CRC-16/CCITT em cabecalho+payload (projeto)": {"largura": 16, "poli": 0x1021, "cobre_cabecalho": True},
    "C: CRC-32 em cabecalho+payload": {"largura": 32, "poli": 0x04C11DB7, "cobre_cabecalho": True},
}


def restos_de_potencias(largura, poli, n):
    """r[e] = x^e mod g, para e = 0..n-1 (g = x^largura + poli)."""
    topo = 1 << largura
    r, atual = [], 1
    for _ in range(n):
        r.append(atual)
        atual <<= 1
        if atual & topo:
            atual ^= topo | poli
    return r


def sindromes(caso):
    """Síndrome de cada bit do quadro depois do sync: cabeçalho, payload, CRC."""
    largura = caso["largura"]
    n_dados = BITS_CAB + BITS_PAYLOAD if caso["cobre_cabecalho"] else BITS_PAYLOAD
    pot = restos_de_potencias(largura, caso["poli"], n_dados + largura)
    # bit de dado na posição k (0 = primeiro transmitido) vale x^(n_dados-1-k) * x^largura
    dados = [pot[n_dados - 1 - k + largura] for k in range(n_dados)]
    crc = [1 << (largura - 1 - k) for k in range(largura)]
    cab = [] if caso["cobre_cabecalho"] else [0] * BITS_CAB  # cabeçalho sem proteção
    return np.array(cab + dados + crc, dtype=np.uint64)


def conferir_com_crc16_real(s):
    """Confere o método com o CRC-16 de verdade do sdrlink.quadro, em erros aleatórios."""
    rng = np.random.default_rng(SEMENTE)
    pacote = quadro.Pacote(4321, rng.integers(0, 256, 128, dtype=np.uint8).tobytes())
    bits = quadro.montar_quadro(pacote)[29:-16]
    for _ in range(2000):
        pos = rng.choice(len(bits), rng.integers(1, 6), replace=False)
        errado = bits.copy()
        errado[pos] ^= 1
        previsto_passa = int(np.bitwise_xor.reduce(s[pos])) == 0
        if previsto_passa != (quadro.interpretar(errado).pacote is not None):
            raise AssertionError("o método das síndromes não bate com o CRC real")


def contar_exato(s):
    """Erros de 1, 2 e 3 bits que passam sem ser detectados (contagem exata)."""
    n = len(s)
    lista = [int(v) for v in s]
    um = sum(1 for v in lista if v == 0)
    posicoes = collections.defaultdict(list)
    for k, v in enumerate(lista):
        posicoes[v].append(k)
    dois = sum(len(p) * (len(p) - 1) // 2 for p in posicoes.values())
    tres = 0
    for i in range(n):
        for j in range(i + 1, n):
            p = posicoes.get(lista[i] ^ lista[j])
            if p:
                tres += len(p) - bisect.bisect_right(p, j)
    return {"n_bits": n, "1 bit": um, "2 bits": dois, "3 bits": tres}


def monte_carlo(s, rng):
    """Fração de padrões aleatórios que passam: w = 4..8 bits e rajadas de 9 a 40 bits."""
    n = len(s)
    res = {}
    for w in (4, 6, 8):
        passa = 0
        for _ in range(N_MONTE_CARLO // 4):
            passa += int(np.bitwise_xor.reduce(s[rng.choice(n, w, replace=False)])) == 0
        res[f"{w} bits aleatorios"] = passa / (N_MONTE_CARLO // 4)
    passa = 0
    for _ in range(N_MONTE_CARLO // 4):
        comp = int(rng.integers(9, 41))
        ini = int(rng.integers(0, n - comp))
        padrao = rng.integers(0, 2, comp).astype(bool)
        padrao[0] = padrao[-1] = True
        passa += int(np.bitwise_xor.reduce(s[ini : ini + comp][padrao])) == 0
    res["rajadas de 9 a 40 bits"] = passa / (N_MONTE_CARLO // 4)
    return res


def main():
    rng = np.random.default_rng(SEMENTE)
    resultado = {}
    for nome, caso in CASOS.items():
        s = sindromes(caso)
        if caso["largura"] == 16:
            conferir_com_crc16_real(s)
        resultado[nome] = {"exato": contar_exato(s), "monte_carlo": monte_carlo(s, rng)}
        print(nome, json.dumps(resultado[nome], ensure_ascii=False), flush=True)
    registro = {
        "ensaio": "deteccao de erros do CRC no quadro v2 com payload de 128 bytes",
        "versao_do_codigo": versao_do_codigo(),
        "semente": SEMENTE,
        "amostras_monte_carlo_por_item": N_MONTE_CARLO // 4,
        "resultado": resultado,
    }
    saida = RAIZ / "dados" / "logs" / f"analise_crc_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
