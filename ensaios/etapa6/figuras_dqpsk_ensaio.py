"""Figura da Etapa 6d a partir do registro mais recente de prova_a_dqpsk_ensaio.py.

Uso: python ensaios/etapa6/figuras_dqpsk_ensaio.py
"""

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sdrlink import teoria

RAIZ = Path(__file__).resolve().parents[2]


def main():
    registro = sorted((RAIZ / "dados" / "logs").glob("prova_a_dqpsk_2*.json"))[-1]
    dados = json.loads(registro.read_text(encoding="utf-8"))
    fig, (esq, dir_) = plt.subplots(1, 2, figsize=(12, 4.8))
    for c in dados["candidatas"]:
        x = [float(e) for e in c["per_por_ebn0_no_ar"]]
        y = [max(p, 1e-3) for p in c["per_por_ebn0_no_ar"].values()]
        esq.semilogy(x, y, "o-", label=c["nome"].replace("(prova-a)", "(prova-a-dbpsk)"))
    esq.axhline(0.01, color="k", ls="--", lw=1)
    esq.set_ylim(5e-4, 1.5)
    esq.set_xlabel("Eb/N0 por bit no ar (dB)")
    esq.set_ylabel("PER (1000 quadros por ponto; 0 desenhado em 1e-3)")
    esq.set_title("Receptor completo, defeitos do RTL medidos")
    esq.grid(True, which="both", alpha=0.3)
    esq.legend(fontsize=8)
    ebn0 = np.linspace(0, 14, 141)
    dir_.semilogy(ebn0, teoria.ber_dbpsk(ebn0), label="DBPSK diferencial")
    dir_.semilogy(ebn0, teoria.ber_dqpsk(ebn0), label="DQPSK diferencial (Gray, exata)")
    dir_.semilogy(ebn0, teoria.ber_bpsk(ebn0), "--", label="BPSK/QPSK coerente (referência)")
    dir_.set_ylim(1e-7, 0.5)
    dir_.set_xlabel("Eb/N0 (dB)")
    dir_.set_ylabel("BER teórica")
    dir_.set_title("Teoria: a DQPSK custa cerca de 1,4 dB sobre a DBPSK")
    dir_.grid(True, which="both", alpha=0.3)
    dir_.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(RAIZ / "docs" / "figuras" / "etapa6_dqpsk.png", dpi=100)
    print(f"figura de {registro.name}")


if __name__ == "__main__":
    sys.exit(main())
