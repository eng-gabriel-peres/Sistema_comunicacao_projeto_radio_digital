"""Faixa plana do RTL a partir de uma captura só de ruído (Pluto desligado).

Mostra até onde o piso de ruído não cai mais que 1 dB abaixo do centro: o sinal dos perfis precisa
caber nessa faixa (prova-a: de +50 a +800 kHz a 2,048 MS/s; prova-a-24: de +50 a
+900 kHz a 2,4 MS/s). Grava um JSON ao lado da captura.

Uso:
    python scripts/gravar_iq.py --perfil prova-a-24 --segundos 2 --nome ruido_24
    python scripts/resposta_rtl.py dados/capturas/ruido_24_<carimbo>.npy --taxa-sps 2.4e6
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from sdrlink import medicao
from sdrlink.registro import salvar_json, versao_do_codigo


def main() -> int:
    """Lê a captura, mede a faixa plana e grava o resultado."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("captura", type=Path, help="captura .npy só de ruído")
    p.add_argument("--taxa-sps", type=float, required=True)
    p.add_argument("--tolerancia-db", type=float, default=medicao.TOLERANCIA_PLANA_DB)
    args = p.parse_args()
    ruido = np.load(args.captura, mmap_mode="r")[: medicao.SINAL_MAX]
    baixo, alto = medicao.faixa_plana(np.asarray(ruido), args.taxa_sps, args.tolerancia_db)
    registro = {
        "versao_do_codigo": versao_do_codigo(),
        "captura": args.captura.name,
        "taxa_sps": args.taxa_sps,
        "tolerancia_db": args.tolerancia_db,
        "faixa_plana_khz": [round(baixo / 1e3, 1), round(alto / 1e3, 1)],
        "fracao_de_nyquist": round(min(-baixo, alto) / (args.taxa_sps / 2), 3),
    }
    caminho = salvar_json(args.captura.with_name(args.captura.stem + "_faixa_plana.json"), registro)
    print(
        f"Faixa plana (queda de até {args.tolerancia_db} dB): "
        f"{baixo / 1e3:.0f} a {alto / 1e3:.0f} kHz"
    )
    print(f"Registro: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
