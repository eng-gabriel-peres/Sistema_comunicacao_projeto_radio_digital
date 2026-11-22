"""Analisa uma sessão de bancada: tabela, gráficos e a perda do enlace em relação à teoria.

Lê, na pasta da sessão, os registros de cada ponto medido (<captura>_rx.json do
receber.py com --ber e <captura>_saida_avaliacao.json do avaliar.py) e grava:
    analise_bancada.md   tabela com ganho do RX, Eb/N0 medido, BER, PER, goodput, banda,
                         offset e a perda do enlace (dB a mais que a teoria para a BER medida)
    analise_bancada.png  BER e PER × Eb/N0 medido, com a curva teórica de cada modulação

É a base do relatório da Etapa 5 (comparação simulação × teoria × medição).

Uso: python scripts/analisar_bancada.py dados/capturas/sessao_<data>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
import numpy as np

from sdrlink import bancada, teoria
from sdrlink.registro import versao_do_codigo

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PER_MIN_GRAFICO = 1e-4  # PER zero aparece aqui no gráfico em escala logarítmica


def _figura(pontos: list[bancada.PontoMedido], caminho: Path) -> None:
    """BER e PER × Eb/N0 medido por perfil, com a BER teórica de cada modulação."""
    fig, (esq, dir_) = plt.subplots(1, 2, figsize=(12, 4.8))
    eixo = np.linspace(0, 20, 201)
    for modulacao in sorted({p.modulacao for p in pontos if p.modulacao in teoria.BER_TEORICA}):
        esq.semilogy(
            eixo, teoria.BER_TEORICA[modulacao](eixo), "--", lw=1, label=f"teoria {modulacao}"
        )
    for perfil in sorted({p.perfil for p in pontos}):
        do_perfil = sorted(
            (p for p in pontos if p.perfil == perfil and p.ebn0_db is not None),
            key=lambda p: p.ebn0_db or 0.0,
        )
        com_ber = [p for p in do_perfil if p.ber]
        if com_ber:
            esq.semilogy(
                [p.ebn0_db for p in com_ber],
                [p.ber for p in com_ber],
                "o-",
                label=f"medido {perfil}",
            )
        com_per = [p for p in do_perfil if p.per is not None]
        if com_per:
            dir_.semilogy(
                [p.ebn0_db for p in com_per],
                [max(p.per or 0.0, PER_MIN_GRAFICO) for p in com_per],
                "o-",
                label=perfil,
            )
    esq.set_ylim(1e-6, 0.5)
    esq.set_title("BER × Eb/N0 medido na captura")
    dir_.axhline(0.01, color="k", ls="--", lw=1)
    dir_.set_title("PER × Eb/N0 medido (PER 0 desenhada em 1e-4)")
    for ax in (esq, dir_):
        ax.set_xlabel("Eb/N0 medido (dB)")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(caminho, dpi=100)
    plt.close(fig)


def main() -> int:
    """Lê a sessão, grava a tabela e os gráficos."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("pasta", type=Path, help="pasta com os registros da sessão")
    args = p.parse_args()
    pontos = bancada.ler_sessao(args.pasta)
    if not pontos:
        p.error(f"nenhum registro *{bancada.SUFIXO_RX} em {args.pasta}")
    perdas = [v for v in (bancada.perda_db(ponto) for ponto in pontos) if v is not None]
    resumo = f"{len(pontos)} pontos; perda do enlace em relação à teoria: " + (
        f"mediana de {np.median(perdas):+.2f} dB ({len(perdas)} pontos com BER)"
        if perdas
        else "sem pontos com BER"
    )
    texto = (
        f"# Análise da sessão {args.pasta.name}\n\n"
        f"Versão do código: `{versao_do_codigo()}`. {resumo}.\n\n"
        + bancada.tabela_markdown(pontos)
        + "\n![BER e PER × Eb/N0](analise_bancada.png)\n"
    )
    (args.pasta / "analise_bancada.md").write_text(texto, encoding="utf-8", newline="\n")
    _figura(pontos, args.pasta / "analise_bancada.png")
    print(resumo)
    print(f"Análise: {args.pasta / 'analise_bancada.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
