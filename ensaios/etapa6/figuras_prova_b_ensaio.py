"""Figura da Etapa 6b a partir do registro da varredura (dados/logs/prova_b_<carimbo>.json).

Uso: python ensaios/etapa6/figuras_prova_b_ensaio.py [registro.json]   (padrão: o mais recente)
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parents[2]


def main():
    if len(sys.argv) > 1:
        registro = Path(sys.argv[1])
    else:
        registro = sorted((RAIZ / "dados" / "logs").glob("prova_b_2*.json"))[-1]
    dados = json.loads(registro.read_text(encoding="utf-8"))
    fig, (esq, dir_) = plt.subplots(1, 2, figsize=(12, 4.8))
    for c in dados["candidatas"]:
        ebn0 = [float(e) for e in c["per_por_ebn0"]]
        per = [max(p, 1e-3) for p in c["per_por_ebn0"].values()]
        esq.semilogy(ebn0, per, "o-", label=c["nome"])
    esq.axhline(0.01, color="k", ls="--", lw=1)
    esq.text(6.1, 0.012, "PER de 1%", fontsize=9)
    esq.set_ylim(5e-4, 1.5)
    esq.set_xlabel("Eb/N0 (dB)")
    esq.set_ylabel("PER (400 quadros por ponto; 0 desenhado em 1e-3)")
    esq.set_title("Receptor completo, offset com deriva de 35 Hz/s")
    esq.grid(True, which="both", alpha=0.3)
    esq.legend(fontsize=8)
    validas = [c for c in dados["candidatas"] if c["cn0_necessario_dbhz"] is not None]
    nomes = [c["nome"].replace(" kbit/s", "k") for c in validas]
    cn0 = [c["cn0_necessario_dbhz"] for c in validas]
    cores = ["tab:blue" if c["modulacao"] == "dbpsk" else "tab:gray" for c in validas]
    dir_.barh(nomes, cn0, color=cores)
    for k, valor in enumerate(cn0):
        dir_.text(valor + 0.1, k, f"{valor:.1f}", va="center", fontsize=9)
    dir_.axvline(dados["cn0_prova_a_dbhz"], color="tab:red", ls="--", lw=1)
    dir_.text(dados["cn0_prova_a_dbhz"] - 0.2, len(validas) - 0.5, "prova-a", color="tab:red", ha="right", fontsize=9)
    dir_.set_xlim(48, 70)
    dir_.set_xlabel("C/N0 necessário para PER de 1% (dB-Hz): menor = mais alcance")
    dir_.set_title("Sensibilidade das candidatas")
    dir_.invert_yaxis()
    fig.tight_layout()
    fig.savefig(RAIZ / "docs" / "figuras" / "etapa6_prova_b.png", dpi=100)
    print(f"figura de {registro.name}")


if __name__ == "__main__":
    sys.exit(main())
