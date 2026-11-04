"""Varredura da faixa autorizada (915 a 928 MHz) só com o RTL, sem transmitir nada.

Mostra onde já há sinais de terceiros e espúrios do próprio RTL, para escolher
a frequência do projeto (decisão D5). Cada passo captura 0,5 s com a leitura
contínua do projeto e guarda a densidade espectral (Welch) da parte central
da banda (±0,8 MHz, longe das bordas do filtro anti-aliasing).
Grava um JSON em dados/logs/ e a figura em docs/figuras/.

Uso: python ensaios/etapa3/varredura_faixa_ensaio.py
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import welch

from sdrlink.hw.rtl_rx import AMOSTRAS_POR_LEITURA, ConfigRtl, capturar
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
FS = 2.048e6
GANHO_DB = 40.0  # alto de propósito: o objetivo é enxergar sinais fracos de terceiros
MEIA_JANELA_HZ = 0.8e6
CENTROS_HZ = np.arange(915.8e6, 928e6, 1.6e6)  # passos de 1,6 MHz cobrem 915 a 928 MHz


def main():
    freqs, dens = [], []
    for centro in CENTROS_HZ:
        cap = capturar(ConfigRtl(float(centro), FS, GANHO_DB), 4 * AMOSTRAS_POR_LEITURA)
        f, p = welch(cap.amostras, fs=FS, nperseg=4096, return_onesided=False, detrend=False)
        f = np.fft.fftshift(f)
        p = np.fft.fftshift(p)
        sel = np.abs(f) <= MEIA_JANELA_HZ
        freqs.append(centro + f[sel])
        dens.append(10 * np.log10(p[sel]))
        print(f"{centro / 1e6:.1f} MHz: piso {np.median(dens[-1]):.1f} dB, pico {dens[-1].max():.1f} dB", flush=True)
    freqs = np.concatenate(freqs)
    dens = np.concatenate(dens)
    piso = float(np.median(dens))
    acima = dens > piso + 10
    picos = [(round(float(fr) / 1e6, 4), round(float(d - piso), 1)) for fr, d in zip(freqs[acima], dens[acima])]
    carimbo = carimbo_de_tempo()
    registro = {
        "ensaio": "varredura da faixa de 915 a 928 MHz, sem transmissão",
        "versao_do_codigo": versao_do_codigo(),
        "rtl": {"taxa_sps": FS, "ganho_pedido_db": GANHO_DB, "ganho_aplicado_db": cap.ganho_db, "correcao_ppm": cap.correcao_ppm},
        "centros_mhz": [round(c / 1e6, 3) for c in CENTROS_HZ],
        "piso_mediano_db": round(piso, 1),
        "pontos_10db_acima_do_piso_mhz_db": picos,
    }
    saida = RAIZ / "dados" / "logs" / f"varredura_faixa_{carimbo}.json"
    saida.write_text(json.dumps(registro, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(freqs / 1e6, dens - piso, lw=0.6)
    ax.axhline(10, color="r", ls="--", lw=0.8, label="10 dB acima do piso")
    ax.axvspan(915, 928, alpha=0.06, color="g", label="faixa autorizada")
    ax.set_xlabel("frequência (MHz)")
    ax.set_ylabel("dB acima do piso mediano")
    ax.set_title(f"Faixa de 915 a 928 MHz sem transmissão (RTL, ganho {cap.ganho_db:.1f} dB, {carimbo})")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(RAIZ / "docs" / "figuras" / "varredura_faixa_04nov.png", dpi=100)
    print(f"registro: {saida}; {len(picos)} pontos acima de 10 dB")


if __name__ == "__main__":
    sys.exit(main())
