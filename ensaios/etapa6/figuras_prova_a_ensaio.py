"""Figuras da Etapa 6a a partir do registro da varredura (dados/logs/prova_a_<carimbo>.json).

Uso: python ensaios/etapa6/figuras_prova_a_ensaio.py [registro.json]   (padrão: o mais recente)
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parents[2]
FIGURAS = RAIZ / "docs" / "figuras"


def main():
    if len(sys.argv) > 1:
        registro = Path(sys.argv[1])
    else:
        registro = sorted((RAIZ / "dados" / "logs").glob("prova_a_2*.json"))[-1]
    dados = json.loads(registro.read_text(encoding="utf-8"))
    candidatas = dados["candidatas"]

    fig, (esq, dir_) = plt.subplots(1, 2, figsize=(11, 4.5))
    taxas = [c["taxa_bits"] / 1e3 for c in candidatas]
    bandas = [c["banda_99_khz"] for c in candidatas]
    cores = ["tab:blue" if c["cabe_em_1_mhz"] else "tab:red" for c in candidatas]
    esq.bar([f"{c['sps']} am./bit\n{t:.0f} k" for c, t in zip(candidatas, taxas)], bandas, color=cores)
    esq.axhline(1000, color="k", ls="--", lw=1)
    esq.text(0, 1015, "limite da prova: 1 MHz", fontsize=9)
    esq.set_ylabel("banda a 99% (kHz)")
    esq.set_title("Banda a 99% (DBPSK RRC, 2,048 MS/s)")
    validas = [c for c in candidatas if c["cabe_em_1_mhz"]]
    dir_.bar([f"{c['taxa_bits'] / 1e3:.0f} k" for c in validas], [c["goodput_sem_perda_kbps"] for c in validas])
    for k, c in enumerate(validas):
        dir_.text(k, c["goodput_sem_perda_kbps"] + 8, f"margem\n{c['margem_db']} dB", ha="center", fontsize=8)
    dir_.set_ylabel("goodput sem perdas (kbit/s)")
    dir_.set_xlabel("taxa de bits")
    dir_.set_title(f"Goodput e margem (C/N0 da bancada: {dados['cn0_bancada_dbhz']} dB-Hz)")
    dir_.set_ylim(0, 720)
    fig.tight_layout()
    fig.savefig(FIGURAS / "etapa6_prova_a.png", dpi=100)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    for c in validas:
        ebn0 = [float(e) for e in c["per_por_ebn0"]]
        per = [max(p, 1e-4) for p in c["per_por_ebn0"].values()]
        ax.semilogy(ebn0, per, "o-", label=f"{c['taxa_bits'] / 1e3:.1f} kbit/s ({c['sps']} amostras por bit)")
    ax.axhline(0.01, color="k", ls="--", lw=1)
    ax.text(5.1, 0.012, "PER de 1% (prova A)", fontsize=9)
    ax.set_ylim(5e-4, 1.5)
    ax.set_xlabel("Eb/N0 (dB)")
    ax.set_ylabel("PER (1000 quadros por ponto; 0 desenhado em 1e-4)")
    ax.set_title("DBPSK RRC, receptor completo, com offset, DC e imagem IQ medidos")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURAS / "etapa6_prova_a_per.png", dpi=100)
    print(f"figuras de {registro.name} em {FIGURAS}")


if __name__ == "__main__":
    sys.exit(main())
