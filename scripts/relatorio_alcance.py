"""Prova B: junta as posições medidas numa tabela e num gráfico de goodput e PER por distância.

Uso, depois de rodar o prova_rx.py em cada posição (com --posicao P1, P2...):
    python scripts/relatorio_alcance.py dados/prova/<data> --distancias P1=10 P2=25 P3=40

A distância não precisa ser conhecida na hora do ensaio: quem mede (trena, mapa do
pátio) informa no fim, pelo nome da posição. O --distancias vale mais que o
--distancia-m dado ao prova_rx.py. Posições sem distância aparecem numa lista à parte.

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


def _distancias(itens: list[str]) -> dict[str, float]:
    """Lê P1=10 P2=25,5 em {"P1": 10.0, "P2": 25.5}.

    Raises:
        ValueError: item fora do formato NOME=METROS.
    """
    mapa: dict[str, float] = {}
    for item in itens:
        nome, _, valor = item.partition("=")
        if not nome.strip() or not valor.strip():
            raise ValueError(f"use NOME=METROS, por exemplo P1=10 (recebi {item!r})")
        mapa[nome.strip()] = float(valor.replace(",", "."))
    return mapa


def _posicoes(
    pasta: Path, distancias: dict[str, float]
) -> tuple[list[prova.Posicao], list[tuple[str, prova.Posicao]]]:
    """As posições com distância e, à parte, as sem distância (nome e resultado)."""
    posicoes: list[prova.Posicao] = []
    sem_distancia: list[tuple[str, prova.Posicao]] = []
    for arquivo in sorted(pasta.glob("*_resumo.json"))[: prova.MAX_POSICOES]:
        r = json.loads(arquivo.read_text(encoding="utf-8"))
        if r.get("prova") != "b":
            continue
        nome = str(r.get("posicao") or r.get("captura") or arquivo.stem)
        distancia = distancias.get(nome, r.get("distancia_m"))
        per = r.get("per")
        posicao = prova.Posicao(
            distancia_m=0.0 if distancia is None else float(distancia),
            goodput_bps=float(r.get("goodput_bps") or 0.0),
            per=1.0 if per is None else float(per),
            pacotes=int(r.get("transmitidos") or r.get("pacotes_unicos") or 0),
            ebn0_db=r.get("ebn0_db"),
        )
        if distancia is None:
            sem_distancia.append((nome, posicao))
        else:
            posicoes.append(posicao)
    return posicoes, sem_distancia


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
    p.add_argument("--distancias", nargs="*", default=[], help="P1=10 P2=25 ... (metros)")
    args = p.parse_args()
    try:
        posicoes, sem_distancia = _posicoes(args.pasta, _distancias(args.distancias))
    except ValueError as erro:
        p.error(str(erro))
    if not posicoes and not sem_distancia:
        p.error(f"nenhum resumo da prova B em {args.pasta}")
    ordenadas, maior = prova.alcance(posicoes)
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
    if sem_distancia:
        linhas += ["", "Posições sem distância (informe com --distancias NOME=METROS):", ""]
        for nome, q in sem_distancia:
            resultado = "passou" if q.passou else "não passou"
            linhas.append(f"- {nome}: {resultado}, {q.pacotes} pacotes, PER de {100 * q.per:.2f}%")
            print(f"Sem distância: {nome} ({resultado})")
    if ordenadas:
        linhas += ["", "![alcance](alcance.png)", ""]
        _figura(ordenadas, args.pasta / "alcance.png")
    (args.pasta / "alcance.md").write_text("\n".join(linhas), encoding="utf-8", newline="\n")
    print("\n".join(linhas[:3]))
    print(f"Relatório: {args.pasta / 'alcance.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
