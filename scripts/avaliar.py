"""Compara o log do TX com a saída do RX e calcula PER e goodput (seção 7 do enunciado).

É a conta que o avaliador faz na prova. Grava um JSON ao lado da saída do RX.

Uso:
    python scripts/avaliar.py dados/logs/tx_<carimbo>.txt <captura>_saida.txt --duracao-s 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sdrlink import metricas
from sdrlink.registro import salvar_json, versao_do_codigo


def main() -> int:
    """Lê os dois arquivos, avalia e grava o resultado."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("log_tx", type=Path, help="log do TX (tx_<carimbo>.txt)")
    p.add_argument("saida_rx", type=Path, help="saída do RX (<captura>_saida.txt)")
    p.add_argument("--duracao-s", type=float, required=True, help="janela do ensaio")
    args = p.parse_args()
    r = metricas.avaliar(
        metricas.ler_pacotes(args.log_tx), metricas.ler_pacotes(args.saida_rx), args.duracao_s
    )
    registro = {
        "versao_do_codigo": versao_do_codigo(),
        "log_tx": args.log_tx.name,
        "saida_rx": args.saida_rx.name,
        **r,
    }
    caminho = salvar_json(args.saida_rx.with_name(args.saida_rx.stem + "_avaliacao.json"), registro)
    print(
        f"{r['recebidos_certos']}/{r['transmitidos']} certos | PER {100 * r['per']:.2f}% | "
        f"goodput {r['goodput_bps'] / 1e3:.1f} kbit/s | "
        f"conteúdo diferente {r['conteudo_diferente']} | espúrios {r['espurios']} | "
        f"duplicados {r['duplicados']}"
    )
    print(f"Registro: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
