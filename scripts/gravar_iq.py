"""Grava uma captura IQ do RTL-SDR em .npy, com um JSON de metadados ao lado.

Uso:
    python scripts/gravar_iq.py --perfil prova-a --segundos 62 --nome prova_a
    python scripts/gravar_iq.py --centro-hz 914.95e6 --segundos 4 --nome fundo_pluto_desligado

Com --perfil, o centro é o LO do perfil e a taxa é a do perfil (as mesmas do TX).

Requisitos: RX-02 (gravar IQ para processar depois), PRC-03 (capturas auditáveis).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

from sdrlink.config import correcao_rtl_ppm_padrao, perfil
from sdrlink.hw.rtl_rx import (
    AMOSTRAS_POR_LEITURA,
    ConfigRtl,
    aviso_de_nivel,
    capturar,
    fracao_saturada,
    nivel_eficaz_dbfs,
)
from sdrlink.registro import RAIZ, carimbo_de_tempo, salvar_json, versao_do_codigo

SEGUNDOS_MAX = 70.0  # 60 s de prova com folga antes e depois; 70 s a 2,4 MS/s = 1,3 GB
TAXA_PADRAO_SPS = 2.048e6


def _argumentos() -> argparse.Namespace:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--perfil", default=None, help="perfil de configs/perfis.toml (centro e taxa)")
    p.add_argument("--centro-hz", type=float, default=None, help="padrão: o LO do perfil")
    p.add_argument("--taxa-sps", type=float, default=None, help="padrão: a do perfil ou 2,048 MS/s")
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
    if args.perfil is not None:
        try:
            escolhido = perfil(args.perfil)
        except ValueError as erro:
            p.error(str(erro))
        args.centro_hz = escolhido.lo_hz if args.centro_hz is None else args.centro_hz
        args.taxa_sps = escolhido.taxa_sps if args.taxa_sps is None else args.taxa_sps
    if args.centro_hz is None:
        p.error("informe --centro-hz ou --perfil")
    args.taxa_sps = TAXA_PADRAO_SPS if args.taxa_sps is None else args.taxa_sps
    if not 0 < args.segundos <= SEGUNDOS_MAX:
        p.error(f"--segundos deve ficar entre 0 e {SEGUNDOS_MAX}")
    return args


def caminho_base(pasta: Path, nome: str, carimbo: str) -> Path:
    """Caminho sem extensão da gravação; o ponto do nome vira "_".

    Um nome com ponto (var_919.12) perdia o resto para o with_suffix, e duas gravações
    caíam no mesmo arquivo (bancada de 25/11).
    """
    return pasta / f"{nome}_{carimbo}".replace(".", "_")


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
    base = caminho_base(args.pasta, args.nome, carimbo_de_tempo())
    np.save(base.with_suffix(".npy"), captura.amostras)
    metadados: dict[str, object] = {
        "versao_codigo": versao_do_codigo(),
        "arquivo_iq": base.with_suffix(".npy").name,
        "centro_hz": captura.centro_hz,
        "taxa_sps": captura.taxa_sps,
        "ganho_db": captura.ganho_db,
        "correcao_ppm": captura.correcao_ppm,
        "perfil": args.perfil,
        "amostras": len(captura.amostras),
        "fracao_saturada": fracao_saturada(captura.amostras),
        "nivel_eficaz_dbfs": round(nivel_eficaz_dbfs(captura.amostras), 1),
    }
    print(f"Gravado: {base.with_suffix('.npy')} ({len(captura.amostras)} amostras)")
    print(f"Nível eficaz: {metadados['nivel_eficaz_dbfs']} dBFS")
    aviso = aviso_de_nivel(nivel_eficaz_dbfs(captura.amostras))
    if aviso:
        print(f"AVISO: {aviso}")
    print(f"Metadados: {salvar_json(base.with_suffix('.json'), metadados)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
