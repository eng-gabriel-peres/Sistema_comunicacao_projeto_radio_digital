"""Decodifica TODOS os quadros OOK de uma captura: CRC-8, PER, BER e offset residual.

Análise do ensaio da Etapa 2 (achado A17). Usa as funções crc8, bits_to_levels
e read_bits do receptor de referência (referencia/Tx_Rx_OOK/rtl_rx_ook_v2.py),
extraídas pelo nome e sem alteração; o resto (filtro, sincronismo por
correlação com o Barker-13 e limiar pelo preâmbulo) segue a mesma ideia da
referência, mas aplicada a cada quadro da captura e não só ao primeiro.

Métricas (definições da seção 7 do enunciado, aqui com um quadro repetido):
- quadros esperados: pelo período fixo do TX, do primeiro ao último sync achado;
- PER = (esperados − CRC OK) / esperados, com não detectados e CRC falho contando como
  falha; o quadro cortado pelo fim da janela de captura não entra (limite da captura, não
  do enlace) e é informado à parte;
- BER = bits de payload errados / bits comparados com a mensagem conhecida, só nos
  quadros detectados com o comprimento certo (os perdidos ficam fora e são contados à parte);
- offset residual: posição da raia da portadora em relação aos 200 kHz nominais.

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
MENSAGEM = b"HELLO WORLD MANDRIAUM"  # payload fixo do pluto_tx_ook_v2.py
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
        return "CRC falhou", carga
    return "CRC OK", carga


def erros_de_bit(carga):
    """Bits diferentes da mensagem conhecida, ou None se o comprimento não bate."""
    if len(carga) != len(MENSAGEM):
        return None
    return sum(bin(a ^ b).count("1") for a, b in zip(carga, MENSAGEM))


def offset_residual_hz(x):
    """Frequência da raia da portadora menos os 200 kHz nominais (FFT longa + interpolação)."""
    dec = 64
    y = passa_baixas(x * np.exp(-2j * np.pi * DESLOC_HZ * np.arange(len(x)) / FS), 10e3)[::dec]
    espectro = np.abs(np.fft.fft(y * np.hanning(len(y)))) ** 2
    f = np.fft.fftfreq(len(y), dec / FS)
    janela = np.abs(f) < 5e3
    k = np.flatnonzero(janela)[np.argmax(espectro[janela])]
    a, b, c = np.log(espectro[k - 1 : k + 2])
    return f[k] + (a - c) / (2 * (a - 2 * b + c)) * (f[1] - f[0])


def main():
    x = np.load(sys.argv[1]).astype(np.complex128)
    t = np.arange(len(x)) / FS
    env = passa_baixas(np.abs(passa_baixas(x * np.exp(-2j * np.pi * DESLOC_HZ * t), 10e3)), 30e3)
    modelo = bits_to_levels(SYNC).repeat(int(round(SPB)))
    cor = fftconvolve(env - env.mean(), modelo[::-1], "valid")
    picos, _ = find_peaks(cor, height=0.7 * cor.max(), distance=int(0.8 * QUADRO))
    saltos = int(np.sum(np.abs(np.diff(picos) - QUADRO) > 20))
    situacoes, mensagens = collections.Counter(), collections.Counter()
    bits_errados = bits_comparados = 0
    for p in picos:
        situacao, carga = decodificar(p, env)
        situacoes[situacao] += 1
        if situacao == "CRC OK":
            mensagens[carga.decode("ascii", "replace")] += 1
        erros = None if carga is None else erros_de_bit(carga)
        if erros is not None:
            bits_errados += erros
            bits_comparados += 8 * len(MENSAGEM)
    esperados = int(round((picos[-1] - picos[0]) / QUADRO)) + 1
    perdidos = esperados - len(picos)
    esperados -= situacoes["cortado no fim"] + situacoes["sem preâmbulo"]
    per = (esperados - situacoes["CRC OK"]) / esperados
    print(f"{len(x) / FS:.2f} s, {len(picos)} quadros achados de {esperados} esperados, {saltos} saltos de intervalo")
    print(dict(situacoes), f"não detectados: {perdidos}")
    print(dict(mensagens))
    print(f"PER = {esperados - situacoes['CRC OK']}/{esperados} = {100 * per:.2f}%")
    print(f"BER = {bits_errados}/{bits_comparados} bits = {bits_errados / max(bits_comparados, 1):.2e}")
    print(f"offset residual da portadora: {offset_residual_hz(x):+.1f} Hz")


if __name__ == "__main__":
    main()
