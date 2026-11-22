"""Processa uma captura IQ gravada: acha todos os quadros e grava o arquivo de saída da prova.

Saídas, ao lado da captura (ou na pasta --pasta):
    <nome>_saida.txt  uma linha por pacote aceito: "sequência<TAB>payload em hexadecimal"
    <nome>_rx.json    parâmetros, versão do código e números da recepção (seção 7 do enunciado)

Uso:
    python scripts/receber.py dados/capturas/<captura>.npy --modulacao dbpsk --pulso rrc \
        --taxa-bits 256e3 --deslocamento-hz 250e3

Requisitos: RX-01, RX-03 (arquivo de saída), MET-02 e MET-05; processa dentro dos 10 min da prova.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from sdrlink import receptor
from sdrlink.modem import MODULACOES, ConfigModem
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import salvar_json, versao_do_codigo

TOLERANCIA_SPS = 1e-9  # folga numérica ao conferir que a razão das taxas é inteira


def _argumentos() -> argparse.Namespace:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("captura", type=Path, help="arquivo .npy (complex64) gravado pelo gravar_iq.py")
    p.add_argument("--modulacao", choices=MODULACOES, required=True)
    p.add_argument("--pulso", choices=("rrc", "retangular", "gaussiano"), required=True)
    p.add_argument("--taxa-bits", type=float, required=True)
    p.add_argument("--taxa-sps", type=float, default=2.048e6, help="taxa da captura")
    p.add_argument(
        "--deslocamento-hz", type=float, default=250e3, help="sinal em relação ao centro"
    )
    p.add_argument("--limiar", type=float, default=receptor.LIMIAR_PADRAO)
    p.add_argument("--offset-max-hz", type=float, default=receptor.OFFSET_MAX_PADRAO_HZ)
    p.add_argument("--pasta", type=Path, default=None, help="padrão: a pasta da captura")
    args = p.parse_args()
    sps = args.taxa_sps / args.taxa_bits
    if abs(sps - round(sps)) > TOLERANCIA_SPS:
        p.error(f"taxa da captura / taxa de bits = {sps:.4f}: precisa ser inteiro")
    return args


def main() -> int:
    """Lê a captura, recebe e grava a saída e o registro."""
    args = _argumentos()
    modem = ConfigModem(args.modulacao, args.pulso, round(args.taxa_sps / args.taxa_bits))
    config = ConfigReceptor(
        modem, args.taxa_sps, args.deslocamento_hz, args.limiar, args.offset_max_hz
    )
    amostras = np.load(args.captura, mmap_mode="r")  # 60 s a 2,048 MS/s = 1 GB: lê por blocos
    inicio = time.time()
    deteccoes = receptor.receber(amostras, config)
    tempo = time.time() - inicio
    pasta = args.pasta or args.captura.parent
    nome = args.captura.stem
    saida = receptor.gravar_saida(receptor.pacotes_aceitos(deteccoes), pasta / f"{nome}_saida.txt")
    registro = {
        "captura": args.captura.name,
        "versao_do_codigo": versao_do_codigo(),
        "parametros": {k: str(v) for k, v in vars(args).items()},
        "decimacao": config.decimacao,
        "tempo_de_processamento_s": round(tempo, 1),
        **receptor.resumo(deteccoes, len(amostras) / args.taxa_sps),
    }
    caminho = salvar_json(pasta / f"{nome}_rx.json", registro)
    print(f"{registro['pacotes_aceitos']} pacotes aceitos em {tempo:.1f} s")
    print(f"Saída: {saida}\nRegistro: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
