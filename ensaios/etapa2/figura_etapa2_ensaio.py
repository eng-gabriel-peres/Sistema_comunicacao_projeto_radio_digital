"""Figura da Etapa 2: continuidade da captura (achado A17) e um quadro OOK recebido.

Uso: python ensaios/etapa2/figura_etapa2_ensaio.py <captura_referencia.npy> <captura_continua.npy> <saida.png>
"""

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from decodificar_quadros_ensaio import DESLOC_HZ, FS, QUADRO, SPB, SYNC, bits_to_levels, passa_baixas
from scipy.signal import fftconvolve, find_peaks

BLOCO = 256 * 1024  # amostras por leitura síncrona da referência


def envoltoria_e_picos(arquivo):
    x = np.load(arquivo).astype(np.complex128)
    t = np.arange(len(x)) / FS
    env = passa_baixas(np.abs(passa_baixas(x * np.exp(-2j * np.pi * DESLOC_HZ * t), 10e3)), 30e3)
    cor = fftconvolve(env - env.mean(), bits_to_levels(SYNC).repeat(int(round(SPB)))[::-1], "valid")
    picos, _ = find_peaks(cor, height=0.7 * cor.max(), distance=int(0.8 * QUADRO))
    return env, picos


def main():
    env_ref, pk_ref = envoltoria_e_picos(sys.argv[1])
    env_nova, pk_nova = envoltoria_e_picos(sys.argv[2])
    fig, eixos = plt.subplots(3, 1, figsize=(10, 9))
    for ax, pk, titulo, emendas in (
        (eixos[0], pk_ref, "Leitura síncrona em blocos (capture_chunks da referência), 0,5 s", True),
        (eixos[1], pk_nova, "Leitura assíncrona (sdrlink.hw.rtl_rx.capturar), 4,1 s", False),
    ):
        desvio = np.diff(pk) - QUADRO
        ax.plot(pk[1:] / FS * 1e3, desvio, "o-", ms=3)
        if emendas:
            for k in range(1, int(pk[-1] // BLOCO) + 1):
                ax.axvline(k * BLOCO / FS * 1e3, color="r", ls="--", lw=0.8)
        saltos = int(np.sum(np.abs(desvio) > 20))
        ax.set_title(f"{titulo}: {saltos} saltos em {len(desvio)} intervalos")
        ax.set_ylabel("intervalo − 46 899\n(amostras)")
        ax.set_xlabel("tempo (ms)")
        ax.grid(alpha=0.3)
    eixos[0].text(0.01, 0.85, "tracejado vermelho: emendas de bloco (128 ms)", transform=eixos[0].transAxes, color="r")
    p = pk_nova[5]
    ini, fim = int(p - 16 * SPB), int(p + 229 * SPB * 0.9)
    eixos[2].plot((np.arange(ini, fim) - p) / SPB, env_nova[ini:fim])
    eixos[2].axvspan(-16, 0, alpha=0.15, label="preâmbulo")
    eixos[2].axvspan(0, 13, alpha=0.15, color="g", label="Barker-13")
    eixos[2].set_title("Um quadro recebido: 'HELLO WORLD MANDRIAUM', CRC-8 OK")
    eixos[2].set_xlabel("bits a partir do início do sync")
    eixos[2].set_ylabel("envoltória")
    eixos[2].legend(loc="upper right")
    eixos[2].grid(alpha=0.3)
    fig.suptitle("Etapa 2, 04/11/2026: OOK de referência, Pluto da equipe → RTL (84 ppm, ganho 10 dB)")
    fig.tight_layout()
    fig.savefig(sys.argv[3], dpi=100)


if __name__ == "__main__":
    main()
