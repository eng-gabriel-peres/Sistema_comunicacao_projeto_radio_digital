"""Gera um arquivo de payloads de 128 bytes para o transmissor (.bin corrido).

Dois tipos:
    --conhecidos  o payload do pacote k é sdrlink.metricas.payload_conhecido(k): a
                  sequência pseudoaleatória conhecida do ensaio de BER (MET-03).
    --aleatorios  payloads aleatórios, como o arquivo do avaliador na prova.

Uso:
    python scripts/gerar_payloads.py --conhecidos 20000 dados/capturas/payloads_ber.bin
    python scripts/gerar_payloads.py --aleatorios 20000 dados/capturas/payloads_prova.bin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from sdrlink import metricas
from sdrlink.transmissor import TAMANHO_PAYLOAD

PACOTES_MAX = 1_000_000


def main() -> int:
    """Lê os argumentos e grava o arquivo."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    tipo = p.add_mutually_exclusive_group(required=True)
    tipo.add_argument("--conhecidos", type=int, metavar="N", help="N payloads da sequência do BER")
    tipo.add_argument("--aleatorios", type=int, metavar="N", help="N payloads aleatórios")
    p.add_argument("saida", type=Path, help="arquivo .bin")
    p.add_argument("--semente", type=int, default=None, help="só para --aleatorios")
    args = p.parse_args()
    n = args.conhecidos if args.conhecidos is not None else args.aleatorios
    if not 0 < n <= PACOTES_MAX or args.saida.suffix != ".bin":
        p.error(f"N entre 1 e {PACOTES_MAX} e saída .bin")
    if args.conhecidos is not None:
        dados = b"".join(metricas.payload_conhecido(k, TAMANHO_PAYLOAD) for k in range(n))
    else:
        gerador = np.random.default_rng(args.semente)
        dados = gerador.integers(0, 256, n * TAMANHO_PAYLOAD, dtype=np.uint8).tobytes()
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_bytes(dados)
    print(f"{n} payloads de {TAMANHO_PAYLOAD} bytes em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
