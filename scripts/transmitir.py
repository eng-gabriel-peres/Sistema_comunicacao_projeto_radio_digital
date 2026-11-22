"""Transmissor de prova: lê os payloads do avaliador, numera, modula e transmite (ou simula).

Saídas em --pasta (padrão dados/logs):
    tx_<carimbo>.txt   log do TX, uma linha por pacote: "sequência<TAB>payload em hex"
    tx_<carimbo>.json  parâmetros, versão do código, horário, banda a 99% e contagens

Uso (na bancada):
    python scripts/transmitir.py payloads.bin --modulacao dbpsk --pulso rrc --taxa-bits 256e3
Sem hardware (grava o sinal para o scripts/receber.py ou para um canal simulado):
    python scripts/transmitir.py payloads.bin --modulacao dbpsk --pulso rrc --taxa-bits 256e3 \
        --simular dados/capturas/tx_simulado.npy

Requisitos: PKT-04, TX-01 (log do TX), PLT-05 (faixa de 915 a 928 MHz), banda a 99% até 1 MHz.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from sdrlink import transmissor
from sdrlink.hw import pluto_tx
from sdrlink.modem import MODULACOES, ConfigModem
from sdrlink.quadro import Pacote
from sdrlink.registro import RAIZ, carimbo_de_tempo, salvar_json, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor, RegistroTx

BANDA_MAX_HZ = 1e6  # limite da prova (seção 8)
LO_PADRAO_HZ = 919.5e6  # trecho limpo da varredura de 04/11, longe de 921,6 MHz (decisão D5)
TOLERANCIA_SPS = 1e-9


def _argumentos() -> argparse.Namespace:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("payloads", type=Path, help="arquivo do avaliador (.bin ou .txt em hex)")
    p.add_argument("--modulacao", choices=MODULACOES, required=True)
    p.add_argument("--pulso", choices=("rrc", "retangular", "gaussiano"), required=True)
    p.add_argument("--taxa-bits", type=float, required=True)
    p.add_argument("--taxa-sps", type=float, default=2.048e6, help="taxa do DAC (a mesma do RX)")
    p.add_argument("--lo-hz", type=float, default=LO_PADRAO_HZ)
    p.add_argument("--deslocamento-hz", type=float, default=250e3)
    p.add_argument("--ganho-db", type=float, default=-30.0, help="atenuação de TX (0 = máximo)")
    p.add_argument("--duracao-s", type=float, default=60.0, help="janela da prova")
    p.add_argument("--uri", default=pluto_tx.URI_PADRAO)
    p.add_argument(
        "--simular", type=Path, default=None, help="grava o sinal em .npy em vez de transmitir"
    )
    p.add_argument("--pasta", type=Path, default=RAIZ / "dados" / "logs")
    args = p.parse_args()
    sps = args.taxa_sps / args.taxa_bits
    if abs(sps - round(sps)) > TOLERANCIA_SPS:
        p.error(f"taxa do DAC / taxa de bits = {sps:.4f}: precisa ser inteiro")
    return args


def _conferir_banda(config: ConfigTransmissor, lo_hz: float) -> tuple[float, float]:
    """Banda a 99% do sinal: até 1 MHz e, com LO e imagem, dentro de 915 a 928 MHz.

    Raises:
        ValueError: banda larga demais ou fora da faixa autorizada.
    """
    baixo, alto = config.banda_99_hz()
    if alto - baixo > BANDA_MAX_HZ:
        raise ValueError(f"banda a 99% de {(alto - baixo) / 1e3:.0f} kHz passa do limite de 1 MHz")
    pluto_tx.conferir_faixa_autorizada(lo_hz, (alto + baixo) / 2, (alto - baixo) / 2)
    return baixo, alto


def _blocos(
    pacotes: list[Pacote],
    config: ConfigTransmissor,
    duracao_s: float,
    log: list[RegistroTx],
) -> Iterator[NDArray[np.complex64]]:
    """Os blocos do fluxo, guardando no log os pacotes à medida que são entregues."""
    for bloco, registros in transmissor.fluxo(pacotes, config, duracao_s):
        log.extend(registros)
        yield bloco


def main() -> int:
    """Confere a banda, transmite (ou simula) e grava o log do TX."""
    args = _argumentos()
    modem = ConfigModem(args.modulacao, args.pulso, round(args.taxa_sps / args.taxa_bits))
    config = ConfigTransmissor(modem, args.taxa_sps, args.deslocamento_hz)
    baixo, alto = _conferir_banda(config, args.lo_hz)
    pacotes = transmissor.numerar(transmissor.ler_payloads(args.payloads))
    log: list[RegistroTx] = []
    inicio = datetime.now().astimezone()
    t0 = time.time()
    if args.simular is not None:
        sinal = np.concatenate(list(_blocos(pacotes, config, args.duracao_s, log)))
        args.simular.parent.mkdir(parents=True, exist_ok=True)
        np.save(args.simular, (sinal / pluto_tx.FUNDO_ESCALA_DAC).astype(np.complex64))
    else:
        pluto = pluto_tx.ConfigPluto(args.lo_hz, args.taxa_sps, args.ganho_db, args.uri)
        pluto_tx.transmitir_fluxo(pluto, _blocos(pacotes, config, args.duracao_s, log))
    nome = f"tx_{carimbo_de_tempo()}"
    caminho_log = transmissor.gravar_log(log, args.pasta / f"{nome}.txt")
    registro = {
        "versao_do_codigo": versao_do_codigo(),
        "inicio": inicio.isoformat(timespec="seconds"),
        "tempo_real_s": round(time.time() - t0, 2),
        "modo": "simulado" if args.simular else "pluto",
        "parametros": {k: str(v) for k, v in vars(args).items()},
        "banda_99_em_relacao_ao_lo_khz": [round(baixo / 1e3, 1), round(alto / 1e3, 1)],
        "payloads_no_arquivo": len(pacotes),
        "pacotes_transmitidos": len(log),
        "ultimo_inicio_s": round(log[-1].amostra_inicio / args.taxa_sps, 4) if log else None,
    }
    salvar_json(args.pasta / f"{nome}.json", registro)
    print(
        f"{len(log)} pacotes ({registro['modo']}), banda a 99%: "
        f"{baixo / 1e3:.0f} a {alto / 1e3:.0f} kHz do LO"
    )
    print(f"Log do TX: {caminho_log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
