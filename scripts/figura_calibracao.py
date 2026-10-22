"""Figura-resumo da calibração de 22/10 para apresentação (só usa arquivos gravados).

Painel A: espectro sem correção (10:48): pente do tx_test.py longe do esperado e
          espúrios do próprio RTL na grade de 100 kHz.
Painel B: calibração ao vivo (11:19, professor já transmitindo a OOK): antes (+1 ppm)
          e depois (+77 ppm); o reprocessamento com a referência da OOK dá +78 ppm.
Painel C: erro do próprio RTL medido nas emissoras FM.

Uso:
    python scripts/figura_calibracao.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from sdrlink.calibracao import espectro_medio, raia_principal_tx_test
from sdrlink.registro import RAIZ

PASTA = RAIZ / "dados" / "calibracao"
CENTRO_HZ = 914.95e6  # sintonia de todas as capturas usadas
TAXA_SPS = 2.048e6
ESPERADA_MHZ = raia_principal_tx_test(915e6, 200e3, 2e6, 1024) / 1e6  # tx_test.py (painel A)
PORTADORA_OOK_MHZ = 915.2  # pluto_tx_ook_v2.py: 20 ciclos inteiros por bit (painel B)
COR_1, COR_2 = "#2a78d6", "#eb6834"  # paleta categórica validada, slots 1 e 2
TINTA, TINTA_2, GRADE, FUNDO = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
PONTOS_POR_CURVA = 2500
SETA = {"arrowstyle": "-", "color": TINTA_2, "lw": 0.8}


def _argumentos() -> argparse.Namespace:
    """Arquivos de entrada e de saída."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--sem-correcao", type=Path, default=PASTA / "calibracao_20261022_104830.npy")
    p.add_argument("--antes", type=Path, default=PASTA / "calibracao_20261022_111918_antes.npy")
    p.add_argument("--depois", type=Path, default=PASTA / "calibracao_20261022_111918_depois.npy")
    p.add_argument("--fm", type=Path, default=PASTA / "fm_20261022_111611.json")
    p.add_argument("--saida", type=Path, default=RAIZ / "docs" / "figuras" / "calibracao_22out.png")
    return p.parse_args()


def _br(valor: float, casas: int = 1) -> str:
    """Número com vírgula decimal e sinal explícito."""
    return f"{valor:+.{casas}f}".replace(".", ",")


def _espectro(arquivo: Path, f0: float, f1: float) -> tuple[np.ndarray, np.ndarray]:
    """Espectro médio (dB sobre o piso) em [f0, f1] MHz, reduzido guardando os picos."""
    freqs, potencia = espectro_medio(np.load(arquivo).astype(np.complex64), TAXA_SPS)
    ordem = np.argsort(freqs)
    f = (CENTRO_HZ + freqs[ordem]) / 1e6
    db = 10 * np.log10(potencia[ordem] / np.median(potencia))
    m = (f >= f0) & (f <= f1)
    grupo = max(1, int(m.sum()) // PONTOS_POR_CURVA)
    n = int(m.sum()) // grupo * grupo
    return f[m][:n].reshape(-1, grupo).mean(1), db[m][:n].reshape(-1, grupo).max(1)


def _estilo(ax: Axes, titulo: str, xlabel: str, ylabel: str) -> None:
    """Grade discreta, eixos recessivos, texto em tinta neutra, sem notação científica."""
    ax.set_facecolor(FUNDO)
    ax.grid(color=GRADE, lw=0.6)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(TINTA_2)
    ax.tick_params(colors=TINTA_2, labelsize=8)
    ax.ticklabel_format(axis="x", useOffset=False, style="plain")
    ax.set_title(titulo, loc="left", fontsize=10, color=TINTA, fontweight="bold")
    ax.set_xlabel(xlabel, fontsize=8.5, color=TINTA_2)
    ax.set_ylabel(ylabel, fontsize=8.5, color=TINTA_2)


def _painel_a(ax: Axes, arquivo: Path) -> None:
    """Pente do tx_test.py longe do esperado; espúrios do RTL na grade de 100 kHz."""
    f, db = _espectro(arquivo, 915.10, 915.32)
    ax.plot(f, db, color=COR_1, lw=0.9)
    ax.axvline(ESPERADA_MHZ, color=TINTA_2, ls="--", lw=0.9)
    ax.annotate(
        "",
        (915.1301, 47),
        xytext=(ESPERADA_MHZ, 47),
        arrowprops={"arrowstyle": "<->", "color": TINTA, "lw": 0.9},
    )
    ax.text(915.1647, 49, "−69 kHz  ≈  −75 ppm", fontsize=8.5, color=TINTA, ha="center")
    ax.annotate(
        "sinal do Pluto do professor\n(pente do tx_test.py)",
        (915.1301, 41),
        xytext=(915.140, 33),
        fontsize=8,
        color=TINTA,
        arrowprops=SETA,
    )
    ax.text(
        ESPERADA_MHZ + 0.002,
        40,
        "onde o tom deveria\naparecer: 915,1992 MHz",
        fontsize=8,
        color=TINTA,
    )
    ax.annotate(
        "espúrios do próprio RTL\n(grade de 100 kHz do cristal)",
        (915.30, 31),
        xytext=(915.232, 20),
        fontsize=8,
        color=TINTA,
        arrowprops=SETA,
    )
    ax.annotate("", (915.2, 22), xytext=(915.232, 20), arrowprops=SETA)
    ax.set_xlim(915.10, 915.32)
    ax.set_ylim(-3, 54)
    _estilo(
        ax,
        "A  Antes de calibrar: correção 0 ppm (10:48)",
        "Frequência indicada pelo RTL (MHz)",
        "dB acima do ruído",
    )


def _painel_b(ax: Axes, antes: Path, depois: Path) -> None:
    """Calibração ao vivo: o sinal vai para a frequência esperada."""
    for arquivo, cor, nome in (
        (antes, COR_1, "antes: correção +1 ppm"),
        (depois, COR_2, "depois: correção +77 ppm"),
    ):
        f, db = _espectro(arquivo, 915.115, 915.215)
        ax.plot(f, db, color=cor, lw=0.9, label=nome)
    ax.axvline(PORTADORA_OOK_MHZ, color=TINTA_2, ls="--", lw=0.9)
    ax.text(
        PORTADORA_OOK_MHZ - 0.002,
        49,
        "portadora da OOK\n915,2000 MHz",
        fontsize=8,
        color=TINTA_2,
        ha="right",
    )
    ax.text(
        0.33,
        0.52,
        "com +77 sobram −0,6 kHz;\ncom +78, cerca de +0,4 kHz",
        transform=ax.transAxes,
        fontsize=7.5,
        color=TINTA_2,
    )
    ax.set_xlim(915.115, 915.215)
    ax.set_ylim(-3, 56)
    _estilo(
        ax,
        "B  Ao vivo com a OOK (11:19): antes e depois",
        "Frequência indicada pelo RTL (MHz)",
        "dB acima do ruído",
    )
    ax.legend(fontsize=8, frameon=False, loc="upper left", labelcolor=TINTA)


def _painel_c(ax: Axes, arquivo_fm: Path) -> None:
    """Erro do próprio RTL nas emissoras FM (independe do Pluto)."""
    registro = json.loads(arquivo_fm.read_text(encoding="utf-8"))
    medidas = registro["medidas"]
    ppm = [m["ppm"] for m in medidas]
    y = np.arange(len(ppm))
    ax.hlines(y, 0, ppm, color=COR_1, lw=2)
    ax.plot(ppm, y, "o", color=COR_1, ms=8)
    for yi, valor in zip(y, ppm, strict=True):
        ax.text(valor, yi + 0.22, _br(valor), fontsize=8, color=TINTA, ha="center")
    mediana = registro["erro_mediano_ppm"]
    ax.axvline(mediana, color=TINTA_2, ls="--", lw=0.9)
    ax.text(mediana + 2, -0.5, f"mediana {_br(mediana)} ppm", fontsize=8, color=TINTA_2)
    ax.set_yticks(y, [f"FM {m['estacao_hz'] / 1e6:.1f}".replace(".", ",") for m in medidas])
    ax.set_xlim(-90, 5)
    ax.set_ylim(-0.7, len(ppm) - 0.3)
    _estilo(ax, "C  Erro do próprio RTL (rádios FM)", "Erro de frequência (ppm)", "")


def main() -> int:
    """Monta e salva a figura."""
    args = _argumentos()
    for arquivo in (args.sem_correcao, args.antes, args.depois, args.fm):
        if not arquivo.exists():
            raise SystemExit(f"Arquivo não encontrado: {arquivo}")
    fig = Figure(figsize=(12, 8), facecolor=FUNDO)
    grade = fig.add_gridspec(2, 2, height_ratios=(1.15, 1), hspace=0.45, wspace=0.22)
    _painel_a(fig.add_subplot(grade[0, :]), args.sem_correcao)
    _painel_b(fig.add_subplot(grade[1, 0]), args.antes, args.depois)
    _painel_c(fig.add_subplot(grade[1, 1]), args.fm)
    fig.suptitle(
        "Calibração RTL-SDR x Pluto do professor (22/10/2026): correção adotada +77 ppm",
        x=0.065,
        ha="left",
        fontsize=12,
        color=TINTA,
        fontweight="bold",
    )
    nota = (
        "Correção do par ao longo da manhã: +75,5 ppm (10:48, tx_test), +78 a +79 (11:05, "
        "tx_test), +77,9 e +77,5 (11:18 e 11:19, OOK).\n"
        "O Pluto deriva de 1 a 3 ppm: repetir a calibração em cada sessão e estimar o "
        "resíduo no receptor."
    )
    fig.text(0.065, 0.012, nota, fontsize=8, color=TINTA_2)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.saida, dpi=130)
    print(f"Figura: {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
