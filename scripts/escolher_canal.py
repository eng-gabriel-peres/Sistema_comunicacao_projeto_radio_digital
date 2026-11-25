"""Escolhe o deslocamento mais limpo para a prova B, com o TX desligado.

A faixa de 915 a 928 MHz tem aparelhos ISM que transmitem em surtos (na bancada de
25/11, numa grade de 500 kHz: 919,25 e 919,75 MHz), e um surto em cima da portadora
derruba a prova B com sinal fraco. Este script grava alguns segundos sem o nosso TX e
mede, para cada deslocamento candidato, o pior surto na faixa do sinal.

Uso (no PC do RX, com o Pluto parado):
    python scripts/escolher_canal.py --perfil prova-b
    python scripts/escolher_canal.py --captura <gravação sem TX .npy> --perfil prova-b

Mostra os melhores deslocamentos; use o escolhido com --deslocamento-hz no prova_tx.py e
no prova_rx.py (os dois lados iguais).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

from sdrlink import config, prova

RAIZ = Path(__file__).resolve().parents[1]
PASSO_HZ = 25e3
DESLOCAMENTO_MIN_HZ = 100e3  # longe do DC do RTL
DESLOCAMENTO_MAX_HZ = 800e3  # dentro da faixa plana do RTL
MARGEM_HZ = 5e3
MELHORES = 5


def main() -> int:
    """Grava sem o TX (ou usa a gravação dada) e lista os deslocamentos mais limpos."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--perfil", default="prova-b")
    p.add_argument("--segundos", type=float, default=10.0)
    p.add_argument("--ganho-db", type=float, default=30.0)
    p.add_argument("--captura", type=Path, default=None, help="gravação já feita, sem o TX")
    args = p.parse_args()
    perfil = config.perfil(args.perfil)
    captura = args.captura
    if captura is None:
        pasta = RAIZ / "dados" / "capturas"
        subprocess.run(  # noqa: S603 (só o script do projeto)
            [sys.executable, str(RAIZ / "scripts" / "gravar_iq.py"), "--perfil", args.perfil,
             "--segundos", str(args.segundos), "--ganho-db", str(args.ganho_db),
             "--nome", "canal", "--pasta", str(pasta)],
            check=True,
        )  # fmt: skip
        captura = max(pasta.glob("canal_*.npy"), key=lambda c: c.stat().st_mtime)
    meia = perfil.taxa_sps / perfil.sps * (1 + perfil.beta) / 2 + MARGEM_HZ
    candidatos = list(np.arange(DESLOCAMENTO_MIN_HZ, DESLOCAMENTO_MAX_HZ + 1, PASSO_HZ))
    candidatos += [-c for c in candidatos]
    ocupacao = prova.ocupacao_dos_canais(np.load(captura), perfil.taxa_sps, candidatos, meia)
    atual = prova.ocupacao_dos_canais(
        np.load(captura), perfil.taxa_sps, [perfil.deslocamento_hz], meia
    )
    melhores = sorted(ocupacao.items(), key=lambda kv: kv[1])[:MELHORES]
    print(f"Pior surto no deslocamento do perfil ({perfil.deslocamento_hz / 1e3:+.0f} kHz): "
          f"{atual[perfil.deslocamento_hz]:.1f} dB (um canal limpo dá cerca de 9 dB)")  # fmt: skip
    print("Mais limpos:")
    for c, v in melhores:
        print(f"  --deslocamento-hz {c:.0f}   pior surto {v:.1f} dB   "
              f"({(perfil.lo_hz + c) / 1e6:.4f} MHz)")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
