"""Transmite um tom limpo no ADALM-Pluto por um tempo fixo (para calibração).

O tom fica em LO + deslocamento e fecha ciclos inteiros no buffer cíclico, então
o espectro é uma raia única. O buffer é sempre desligado no final.

Uso:
    python scripts/transmitir_tom.py --freq-tom-hz 921.25e6 --duracao-s 120

Escolha um tom fora das grades de espúrios do RTL (múltiplos de 100 kHz e de
taxa/8). O tom, o vazamento do LO e a imagem IQ precisam ficar na faixa
autorizada de 915 a 928 MHz (PLT-05); o script confere antes de transmitir.
"""

from __future__ import annotations

import argparse
import sys

from sdrlink.hw.pluto_tx import (
    URI_PADRAO,
    ConfigPluto,
    conferir_faixa_autorizada,
    n_amostras_ciclos_inteiros,
    tom_complexo,
    transmitir,
)


def _argumentos() -> argparse.Namespace:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--freq-tom-hz", type=float, default=921.25e6, help="frequência RF do tom")
    p.add_argument("--deslocamento-hz", type=float, default=250e3, help="tom = LO + deslocamento")
    p.add_argument("--taxa-sps", type=float, default=2e6)
    p.add_argument("--ganho-db", type=float, default=-30.0, help="atenuação de TX (0 = máximo)")
    p.add_argument("--duracao-s", type=float, default=120.0)
    p.add_argument("--uri", default=URI_PADRAO)
    args = p.parse_args()
    try:
        conferir_faixa_autorizada(
            args.freq_tom_hz - args.deslocamento_hz, args.deslocamento_hz, 0.0
        )
    except ValueError as erro:
        p.error(str(erro))
    return args


def main() -> int:
    """Monta o tom e transmite."""
    args = _argumentos()
    config = ConfigPluto(
        args.freq_tom_hz - args.deslocamento_hz, args.taxa_sps, args.ganho_db, args.uri
    )
    n = n_amostras_ciclos_inteiros(args.deslocamento_hz, args.taxa_sps)
    tom = tom_complexo(args.deslocamento_hz, args.taxa_sps, n)
    print(
        f"Transmitindo {args.freq_tom_hz / 1e6:.6f} MHz (LO {config.lo_hz / 1e6:.6f} MHz + "
        f"{args.deslocamento_hz / 1e3:.0f} kHz), ganho {args.ganho_db} dB, buffer de {n} amostras, "
        f"{args.duracao_s:.0f} s",
        flush=True,
    )
    try:
        transmitir(config, tom, args.duracao_s)
    except (RuntimeError, ValueError) as erro:
        raise SystemExit(f"Erro: {erro}") from erro
    print("Transmissão encerrada e buffer desligado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
