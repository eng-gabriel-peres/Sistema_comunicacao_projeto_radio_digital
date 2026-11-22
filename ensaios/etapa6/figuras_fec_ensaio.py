"""Figura da Etapa 6c: PER × Eb/N0 por bit útil, com e sem FEC (receptor completo e sincronismo ideal).

Lê os registros mais recentes de prova_b_ensaio.py, prova_b_fec_ensaio.py e
fec_sincronismo_ideal_ensaio.py.

Uso: python ensaios/etapa6/figuras_fec_ensaio.py
"""

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sdrlink import quadro

RAIZ = Path(__file__).resolve().parents[2]
LOGS = RAIZ / "dados" / "logs"
# bits no ar / bits úteis depois do sync (taxa 1/2 + cauda), pelo formato do quadro em vigor
UTIL_POR_AR_DB = 10 * np.log10(quadro.bits_no_ar_apos_sync(128, fec=True) / quadro.bits_apos_sync(128))


def ultimo(padrao):
    """Registro mais recente com esse padrão."""
    return json.loads(sorted(LOGS.glob(padrao))[-1].read_text(encoding="utf-8"))


def main():
    sem = ultimo("prova_b_2*.json")
    com = ultimo("prova_b_fec_2*.json")
    genio = ultimo("fec_sincronismo_ideal_2*.json")
    fig, (esq, dir_) = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for c in sem["candidatas"]:
        if c["nome"] == "DBPSK 12,8 kbit/s":
            x = [float(e) for e in c["per_por_ebn0"]]
            esq.semilogy(x, [max(p, 1e-3) for p in c["per_por_ebn0"].values()], "o-", label="sem FEC, 12,8 kbit/s")
    for c in com["candidatas"]:
        x = [float(e) + UTIL_POR_AR_DB for e in c["per_por_ebn0_no_ar"]]
        y = [max(p, 1e-3) for p in c["per_por_ebn0_no_ar"].values()]
        esq.semilogy(x, y, "s-", label=f"com FEC, {c['taxa_no_ar'] / 1e3:.1f} kbit/s no ar")
    esq.set_title("Receptor completo (offset com deriva, DC, imagem IQ)")
    for nome, curva in genio["curvas"].items():
        x = [float(e) for e in curva["per"]]
        estilo = "s-" if nome.startswith("com") else "o-"
        dir_.semilogy(x, [max(p, 1e-3) for p in curva["per"].values()], estilo, label=nome)
    dir_.set_title("Sincronismo ideal: código e detectores")
    for ax in (esq, dir_):
        ax.axhline(0.01, color="k", ls="--", lw=1)
        ax.set_xlabel("Eb/N0 por bit útil (dB)")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
        ax.set_ylim(5e-4, 1.5)
    esq.set_ylabel("PER (0 desenhado em 1e-3)")
    fig.tight_layout()
    fig.savefig(RAIZ / "docs" / "figuras" / "etapa6_fec.png", dpi=100)
    print("figura gerada")


if __name__ == "__main__":
    sys.exit(main())
