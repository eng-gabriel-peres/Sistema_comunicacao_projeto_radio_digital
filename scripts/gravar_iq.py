"""Grava uma captura IQ do RTL-SDR em .npy, com um JSON de metadados ao lado.

Uso:
    python scripts/gravar_iq.py --centro-hz 914.95e6 --segundos 4 --nome fundo_pluto_desligado

Requisitos: RX-02 (gravar IQ para processar depois), PRC-03 (capturas auditáveis).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

from sdrlink.config import correcao_rtl_ppm_padrao
from sdrlink.hw.rtl_rx import AMOSTRAS_POR_LEITURA, ConfigRtl, capturar, fracao_saturada
from sdrlink.registro import RAIZ, carimbo_de_tempo, salvar_json, versao_do_codigo

SEGUNDOS_MAX = 60.0  # 60 s a 2,4 MS/s = 1,15 GB em complex64


def _argumentos() -> argparse.Namespace:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--centro-hz", type=float, required=True)
    p.add_argument("--taxa-sps", type=float, default=2.048e6)
    p.add_argument("--ganho-db", type=float, default=40.0)
    p.add_argument(
        "--correcao-ppm",
        type=int,
        default=correcao_rtl_ppm_padrao(),
        help="padrão: configs/rtl.toml",
    )
    p.add_argument("--segundos", type=float, default=4.0)
    p.add_argument("--nome", default="captura", help="prefixo do arquivo")
    p.add_argument("--pasta", type=Path, default=RAIZ / "dados" / "capturas")
    args = p.parse_args()
    if not 0 < args.segundos <= SEGUNDOS_MAX:
        p.error(f"--segundos deve ficar entre 0 e {SEGUNDOS_MAX}")
    return args


def main() -> int:
    """Captura, grava o .npy e o JSON de metadados."""
    args = _argumentos()
    config = ConfigRtl(args.centro_hz, args.taxa_sps, args.ganho_db, args.correcao_ppm)
    leituras = math.ceil(args.segundos * args.taxa_sps / AMOSTRAS_POR_LEITURA)
    try:
        captura = capturar(config, leituras * AMOSTRAS_POR_LEITURA)
    except RuntimeError as erro:
        raise SystemExit(f"Erro: {erro}") from erro
    args.pasta.mkdir(parents=True, exist_ok=True)
    base = args.pasta / f"{args.nome}_{carimbo_de_tempo()}"
    np.save(base.with_suffix(".npy"), captura.amostras)
    metadados: dict[str, object] = {
        "versao_codigo": versao_do_codigo(),
        "arquivo_iq": base.with_suffix(".npy").name,
        "centro_hz": captura.centro_hz,
        "taxa_sps": captura.taxa_sps,
        "ganho_db": captura.ganho_db,
        "correcao_ppm": captura.correcao_ppm,
        "amostras": len(captura.amostras),
        "fracao_saturada": fracao_saturada(captura.amostras),
    }
    print(f"Gravado: {base.with_suffix('.npy')} ({len(captura.amostras)} amostras)")
    print(f"Metadados: {salvar_json(base.with_suffix('.json'), metadados)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
