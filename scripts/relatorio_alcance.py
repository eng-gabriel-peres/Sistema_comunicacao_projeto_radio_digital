"""Prova B: junta as posições medidas numa tabela e num gráfico de goodput e PER por distância.

Uso, depois de rodar o prova_rx.py em cada posição (com --distancia-m):
    python scripts/relatorio_alcance.py dados/prova/<data>

Lê os <nome>_resumo.json da prova B na pasta e grava alcance.md e alcance.png: goodput
e PER × distância com os critérios da prova (10 kbit/s, PER de 1%, 500 pacotes) e a
maior distância validada.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

from sdrlink import prova

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PER_MIN_GRAFICO = 1e-4


def _posicoes(pasta: Path) -> list[prova.Posicao]:
    posicoes = []
    for arquivo in sorted(pasta.glob("*_resumo.json"))[: prova.MAX_POSICOES]:
        r = json.loads(arquivo.read_text(encoding="utf-8"))
        if r.get("prova") != "b" or r.get("distancia_m") is None:
            continue
        pacotes = int(r.get("transmitidos") or r.get("pacotes_unicos") or 0)
        per = r.get("per")
        posicoes.append(
            prova.Posicao(
                distancia_m=float(r["distancia_m"]),
                goodput_bps=float(r.get("goodput_bps") or 0.0),
                per=1.0 if per is None else float(per),
                pacotes=pacotes,
                ebn0_db=r.get("ebn0_db"),
            )
        )
    return posicoes


def _figura(posicoes: list[prova.Posicao], caminho: Path) -> None:
    d = [p.distancia_m for p in posicoes]
    fig, (esq, dir_) = plt.subplots(1, 2, figsize=(11, 4))
    esq.plot(d, [p.goodput_bps / 1e3 for p in posicoes], "o-")
    esq.axhline(prova.GOODPUT_MIN_BPS / 1e3, color="C3", ls="--", lw=1, label="mínimo 10 kbit/s")
    esq.set_ylabel("goodput (kbit/s)")
    dir_.semilogy(d, [max(p.per, PER_MIN_GRAFICO) for p in posicoes], "o-")
    dir_.axhline(prova.PER_MAX, color="C3", ls="--", lw=1, label="PER máxima 1%")
    dir_.set_ylabel("PER (0 desenhada em 1e-4)")
    for ax in (esq, dir_):
        ax.set_xlabel("distância (m)")
        ax.grid(alpha=0.3, which="both")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(caminho, dpi=100)
    plt.close(fig)


def main() -> int:
    """Lê os resumos da prova B e grava a tabela e o gráfico."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("pasta", type=Path, help="pasta da prova (dados/prova/<data>)")
    args = p.parse_args()
    ordenadas, maior = prova.alcance(_posicoes(args.pasta))
    if not ordenadas:
        p.error(f"nenhum resumo da prova B com distância em {args.pasta}")
    linhas = [
        "# Prova B: alcance",
        "",
        f"Maior distância validada: **{'nenhuma' if maior is None else f'{maior:g} m'}**.",
        "",
        "| Distância (m) | Goodput (kbit/s) | PER | Pacotes | Eb/N0 (dB) | Passou |",
        "|---|---|---|---|---|---|",
    ]
    for q in ordenadas:
        ebn0 = "-" if q.ebn0_db is None else f"{q.ebn0_db:.1f}"
        linhas.append(
            f"| {q.distancia_m:g} | {q.goodput_bps / 1e3:.1f} | {100 * q.per:.2f}% | {q.pacotes} "
            f"| {ebn0} | {'sim' if q.passou else 'não'} |"
        )
    linhas += ["", "![alcance](alcance.png)", ""]
    (args.pasta / "alcance.md").write_text("\n".join(linhas), encoding="utf-8", newline="\n")
    _figura(ordenadas, args.pasta / "alcance.png")
    print("\n".join(linhas[:3]))
    print(f"Relatório: {args.pasta / 'alcance.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
