"""Transmissor de prova: lê os payloads do avaliador, numera, modula e transmite (ou simula).

Saídas em --pasta (padrão dados/logs):
    tx_<carimbo>.txt   log do TX, uma linha por pacote: "sequência<TAB>payload em hex"
    tx_<carimbo>.json  parâmetros, versão do código, horário, banda a 99% e contagens

Uso (na bancada), com um perfil de configs/perfis.toml ou com os parâmetros soltos:
    python scripts/transmitir.py payloads.bin --perfil prova-a
    python scripts/transmitir.py payloads.bin --modulacao dbpsk --pulso rrc --taxa-bits 256e3
Sem hardware (grava o sinal para o scripts/receber.py ou para um canal simulado):
    python scripts/transmitir.py payloads.bin --perfil prova-a --simular dados/capturas/tx.npy

Requisitos: PKT-04, TX-01 (log do TX), PLT-05 (faixa de 915 a 928 MHz), banda a 99% até 1 MHz.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from sdrlink import prova, transmissor
from sdrlink.config import Perfil, argumentos_de_enlace, perfil_dos_argumentos
from sdrlink.hw import pluto_tx
from sdrlink.quadro import Pacote
from sdrlink.registro import RAIZ, carimbo_de_tempo, salvar_json, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor, RegistroTx

BANDA_MAX_HZ = 1e6  # limite da prova (seção 8)


def _argumentos() -> tuple[argparse.Namespace, Perfil]:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument(
        "payloads",
        type=Path,
        help="arquivo do avaliador: .txt (hex por linha) ou qualquer outro, fatiado em 128 bytes",
    )
    argumentos_de_enlace(p)
    p.add_argument("--ganho-db", type=float, default=-30.0, help="atenuação de TX (0 = máximo)")
    p.add_argument("--duracao-s", type=float, default=60.0, help="janela da prova")
    p.add_argument("--uri", default=pluto_tx.URI_PADRAO)
    p.add_argument(
        "--pre-gerar",
        action="store_true",
        help="gera o sinal inteiro antes de abrir o Pluto (risco R1; 60 s ocupam cerca de 1 GB)",
    )
    p.add_argument(
        "--simular", type=Path, default=None, help="grava o sinal em .npy em vez de transmitir"
    )
    p.add_argument(
        "--atraso-s",
        type=float,
        default=0.0,
        help="espera depois do sinal pronto e antes de entrar no ar (para começar a gravação)",
    )
    p.add_argument(
        "--repetir",
        action="store_true",
        help="repete o arquivo em ciclo até encher a janela (arquivo menor que a janela)",
    )
    p.add_argument("--pasta", type=Path, default=RAIZ / "dados" / "logs")
    args = p.parse_args()
    if args.atraso_s < 0:
        p.error("--atraso-s não pode ser negativo")
    return args, perfil_dos_argumentos(p, args)


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


def fonte_de_blocos(
    pacotes: list[Pacote],
    config: ConfigTransmissor,
    duracao_s: float,
    log: list[RegistroTx],
    pre_gerar: bool,
) -> Iterable[NDArray[np.complex64]]:
    """Os blocos para o Pluto: gerados enquanto ele transmite, ou todos antes (pre_gerar).

    Gerando durante a transmissão, o Python precisa entregar cada bloco antes de o
    Pluto acabar o anterior; com folga de cerca de 2 vezes em simulação, isso nunca foi
    medido no hardware (risco R1). Gerando antes, o Pluto só recebe blocos prontos, ao
    custo de memória: 60 s a 2,048 MS/s em complex64 ocupam cerca de 1 GB.
    """
    blocos = _blocos(pacotes, config, duracao_s, log)
    return list(blocos) if pre_gerar else blocos


def _pacotes(args: argparse.Namespace, config: ConfigTransmissor) -> tuple[list[Pacote], int]:
    """Os pacotes do arquivo (repetidos se --repetir) e quantos cabem na janela."""
    payloads, aviso = prova.ler_arquivo(args.payloads)
    if aviso:
        print(f"AVISO: {aviso}")
    cabem = transmissor.pacotes_que_cabem(config, args.duracao_s)
    if args.repetir and len(payloads) < cabem:
        print(f"Repetindo o arquivo ({len(payloads)} payloads) até {cabem} pacotes")
        payloads = prova.repetir_ate(payloads, cabem)
    return transmissor.numerar(payloads), cabem


def main() -> int:
    """Confere a banda, transmite (ou simula) e grava o log do TX."""
    args, perfil = _argumentos()
    config = ConfigTransmissor(
        perfil.modem(),
        perfil.taxa_sps,
        perfil.deslocamento_hz,
        fec=perfil.fec,
        emendar_caudas=perfil.emendar_caudas,
    )
    baixo, alto = _conferir_banda(config, perfil.lo_hz)
    pacotes, cabem = _pacotes(args, config)
    if len(pacotes) < cabem:
        print(
            f"AVISO: o arquivo tem {len(pacotes)} payloads, mas cabem {cabem} em "
            f"{args.duracao_s:g} s: o TX vai parar antes do fim da janela e o goodput cai"
        )
    log: list[RegistroTx] = []
    inicio = datetime.now().astimezone()
    tempo_no_ar: float | None = None
    t0 = time.time()
    if args.simular is not None:
        sinal = np.concatenate(list(_blocos(pacotes, config, args.duracao_s, log)))
        args.simular.parent.mkdir(parents=True, exist_ok=True)
        np.save(args.simular, (sinal / pluto_tx.FUNDO_ESCALA_DAC).astype(np.complex64))
    else:
        pluto = pluto_tx.ConfigPluto(perfil.lo_hz, perfil.taxa_sps, args.ganho_db, args.uri)
        blocos = fonte_de_blocos(pacotes, config, args.duracao_s, log, args.pre_gerar)
        print(f"Sinal pronto; no ar em {args.atraso_s:g} s", flush=True)
        time.sleep(args.atraso_s)
        no_ar = time.time()
        print(f"No ar desde {datetime.now().strftime('%H:%M:%S')}", flush=True)
        pluto_tx.transmitir_fluxo(pluto, blocos)
        tempo_no_ar = round(time.time() - no_ar, 2)
    nome = f"tx_{carimbo_de_tempo()}"
    caminho_log = transmissor.gravar_log(log, args.pasta / f"{nome}.txt")
    registro = {
        "versao_do_codigo": versao_do_codigo(),
        "inicio": inicio.isoformat(timespec="seconds"),
        "tempo_real_s": round(time.time() - t0, 2),
        # bancada de 25/11: sem --pre-gerar, 60 s de conteúdo levaram 99 s para sair (risco R1)
        "tempo_no_ar_s": tempo_no_ar,
        "modo": "simulado" if args.simular else "pluto",
        "parametros": {k: str(v) for k, v in vars(args).items()},
        "perfil": dataclasses.asdict(perfil),
        "banda_99_em_relacao_ao_lo_khz": [round(baixo / 1e3, 1), round(alto / 1e3, 1)],
        "payloads_no_arquivo": len(pacotes),
        "pacotes_que_cabem_na_janela": cabem,
        "payloads_suficientes": len(pacotes) >= cabem,
        "pacotes_transmitidos": len(log),
        "ultimo_inicio_s": round(log[-1].amostra_inicio / perfil.taxa_sps, 4) if log else None,
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
