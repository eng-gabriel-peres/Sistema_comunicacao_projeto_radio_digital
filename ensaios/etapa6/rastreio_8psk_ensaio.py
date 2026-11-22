"""Ganho da malha de fase da 8-PSK: tolerância ao ruído de fase contra a perda no ruído branco.

A 8-PSK coerente decide pela fase absoluta, e a fase dos osciladores anda dentro do
quadro. O receptor rastreia a fase símbolo a símbolo (sdrlink.modem._rastrear_8psk), com
o ganho GANHO_RASTREIO_8PSK; ganho 0 é não rastrear (uma reta só por quadro, pela fase
do prefixo e a frequência da potência 8).

Com sincronismo ideal, 3 amostras por símbolo (prova A), quadros de 128 bytes, offset
residual de até ±300 Hz e fase inicial qualquer:
    PER com ruído de fase de Wiener de 0 a 1 kHz, 1 dB acima do ponto de PER 1% (13,9 dB)
    PER só com ruído branco em 12,9 dB (o custo do rastreio)

Uso: python ensaios/etapa6/rastreio_8psk_ensaio.py   (cerca de 5 min)
"""

import json
import sys
from pathlib import Path

import numpy as np

from sdrlink import canal, modem, quadro
from sdrlink.modem import ConfigModem
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
CM = ConfigModem("8psk", "rrc", 3, beta=0.25)
GANHOS = (0.0, 0.05, 0.1, 0.2)
LARGURAS_HZ = (0.0, 10.0, 30.0, 100.0, 300.0, 1000.0)
QUADROS = 400
QUADROS_RUIDO_BRANCO = 2000


def per(largura_hz, ebn0_db, quadros):
    rng = np.random.default_rng(8)  # o mesmo sinal e o mesmo ruído para todos os ganhos
    falhos = 0
    for _ in range(quadros):
        bits = np.concatenate([quadro.PREFIXO, rng.integers(0, 2, 1072).astype(np.uint8)])
        x = modem.modular(bits, CM, quadro.BITS_PREFIXO)
        fase = canal.ruido_de_fase(len(x), largura_hz, 2.048e6, rng) + rng.uniform(0, 2 * np.pi)
        x = canal.girar(x * np.exp(1j * fase), rng.uniform(-300, 300), 2.048e6)
        y = canal.awgn(x, ebn0_db, 1.0, rng)
        recebidos = modem.demodular(y, CM, len(bits), prefixo=quadro.BITS_PREFIXO)
        falhos += bool(np.any(recebidos[quadro.BITS_PREFIXO :] != bits[quadro.BITS_PREFIXO :]))
    return round(falhos / quadros, 4)


def main():
    linhas = []
    for ganho in GANHOS:
        modem.GANHO_RASTREIO_8PSK = ganho
        linha = {
            "ganho": ganho,
            "per_wiener_13_9_db": {f"{w:g}": per(w, 13.9, QUADROS) for w in LARGURAS_HZ},
            "per_ruido_branco_12_9_db": per(0.0, 12.9, QUADROS_RUIDO_BRANCO),
        }
        linhas.append(linha)
        print(json.dumps(linha), flush=True)
    resultado = {
        "ensaio": "ganho da malha de fase da 8-PSK", "quadros": QUADROS,
        "quadros_ruido_branco": QUADROS_RUIDO_BRANCO, "linhas": linhas,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"rastreio_8psk_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
