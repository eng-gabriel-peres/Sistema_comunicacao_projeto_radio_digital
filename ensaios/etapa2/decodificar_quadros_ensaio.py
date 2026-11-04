"""Decodifica TODOS os quadros OOK de uma captura e conta quantos passam no CRC-8.

Análise do ensaio da Etapa 2 (achado A17). Usa as funções crc8, bits_to_levels
e read_bits do receptor de referência (referencia/Tx_Rx_OOK/rtl_rx_ook_v2.py),
extraídas pelo nome e sem alteração; o resto (filtro, sincronismo por
correlação com o Barker-13 e limiar pelo preâmbulo) segue a mesma ideia da
referência, mas aplicada a cada quadro da captura e não só ao primeiro.

Uso: python ensaios/etapa2/decodificar_quadros_ensaio.py dados/capturas/<arquivo>.npy
"""

import ast
import collections
import sys
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve, find_peaks

RAIZ = Path(__file__).resolve().parents[2]
REF = RAIZ / "referencia" / "Tx_Rx_OOK" / "rtl_rx_ook_v2.py"
FS = 2.048e6
DESLOC_HZ = 200e3
SPB = FS / 10e3  # amostras por bit
SYNC = "1111100110101"
N_PREAMBULO = 16
QUADRO = 229 * SPB  # duração de um quadro + pausa, em amostras (período medido)


def funcoes_da_referencia(nomes):
    """Carrega só as funções pedidas do receptor de referência (o módulo abre o rádio ao importar)."""
    arvore = ast.parse(REF.read_text(encoding="utf-8"))
    defs = [n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name in nomes]
    ns = {"np": np}
    exec(compile(ast.Module(body=defs, type_ignores=[]), str(REF), "exec"), ns)
    return [ns[n] for n in nomes]


crc8, bits_to_levels, read_bits = funcoes_da_referencia(["crc8", "bits_to_levels", "read_bits"])


def passa_baixas(x, fc):
    n = int(np.ceil(3.3 * FS / (fc / 4)))
    n += n % 2 == 0
    k = np.arange(n) - (n - 1) / 2
    h = 2 * fc / FS * np.sinc(2 * fc / FS * k) * np.hamming(n)
    return fftconvolve(x, h / h.sum(), "same")


def decodificar(p, env):
    """Decodifica o quadro cujo sync começa na amostra p; devolve (situação, mensagem)."""
    pre = p - N_PREAMBULO * SPB
    if pre < 0:
        return "sem preâmbulo", None
    niveis = [env[int(pre + k * SPB) : int(pre + (k + 1) * SPB)].mean() for k in range(N_PREAMBULO)]
    limiar = (np.mean(niveis[0::2]) + np.mean(niveis[1::2])) / 2
    bits_len, ini = read_bits(env, p + len(SYNC) * SPB, 8, SPB, limiar)
    if bits_len is None:
        return "cortado no fim", None
    bits_pl, ini_crc = read_bits(env, ini, int(bits_len, 2) * 8, SPB, limiar)
    if bits_pl is None:
        return "cortado no fim", None
    carga = bytes(int(bits_pl[i : i + 8], 2) for i in range(0, len(bits_pl), 8))
    bits_crc, _ = read_bits(env, ini_crc, 8, SPB, limiar)
    if bits_crc is None:
        return "cortado no fim", None
    if int(bits_crc, 2) != crc8(carga):
        return "CRC falhou", None
    return "CRC OK", carga.decode("ascii", "replace")


def main():
    x = np.load(sys.argv[1]).astype(np.complex128)
    t = np.arange(len(x)) / FS
    env = passa_baixas(np.abs(passa_baixas(x * np.exp(-2j * np.pi * DESLOC_HZ * t), 10e3)), 30e3)
    modelo = bits_to_levels(SYNC).repeat(int(round(SPB)))
    cor = fftconvolve(env - env.mean(), modelo[::-1], "valid")
    picos, _ = find_peaks(cor, height=0.7 * cor.max(), distance=int(0.8 * QUADRO))
    saltos = int(np.sum(np.abs(np.diff(picos) - QUADRO) > 20))
    situacoes, mensagens = collections.Counter(), collections.Counter()
    for p in picos:
        situacao, msg = decodificar(p, env)
        situacoes[situacao] += 1
        if msg is not None:
            mensagens[msg] += 1
    print(f"{len(x) / FS:.2f} s, {len(picos)} quadros, {saltos} saltos de intervalo")
    print(dict(situacoes))
    print(dict(mensagens))


if __name__ == "__main__":
    main()
