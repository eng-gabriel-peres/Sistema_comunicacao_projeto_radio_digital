"""Processa uma captura IQ gravada: acha todos os quadros e grava o arquivo de saída da prova.

Saídas, ao lado da captura (ou na pasta --pasta):
    <nome>_saida.txt  uma linha por pacote aceito: "sequência<TAB>payload em hexadecimal"
    <nome>_rx.json    parâmetros, versão do código e números da recepção (seção 7 do enunciado)

O registro traz também a banda a 99% e o Eb/N0 medidos na captura, quando há pelo
menos 0,2 s de ruído antes do primeiro quadro (comece a gravar antes do TX), e,
com --ber, a BER com sequência conhecida (o TX precisa usar os payloads de
scripts/gerar_payloads.py --conhecidos).

Uso, com o mesmo perfil do TX (configs/perfis.toml) ou com os parâmetros soltos:
    python scripts/receber.py dados/capturas/<captura>.npy --perfil prova-a [--ber]
    python scripts/receber.py dados/capturas/<captura>.npy --modulacao dbpsk --pulso rrc \
        --taxa-bits 256e3 --deslocamento-hz 250e3 [--ber]

Requisitos: RX-01, RX-03 (arquivo de saída), MET-02 a MET-05; processa dentro dos 10 min.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

import numpy as np

from sdrlink import medicao, metricas, quadro, receptor, transmissor
from sdrlink.config import Perfil, argumentos_de_enlace, perfil_dos_argumentos
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import salvar_json, versao_do_codigo


def _argumentos() -> tuple[argparse.Namespace, Perfil]:
    """Lê os parâmetros da linha de comando."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("captura", type=Path, help="arquivo .npy (complex64) gravado pelo gravar_iq.py")
    argumentos_de_enlace(p)
    p.add_argument("--limiar", type=float, default=receptor.LIMIAR_PADRAO)
    p.add_argument("--offset-max-hz", type=float, default=receptor.OFFSET_MAX_PADRAO_HZ)
    p.add_argument("--pasta", type=Path, default=None, help="padrão: a pasta da captura")
    p.add_argument(
        "--ber", action="store_true", help="mede a BER (payloads com sequência conhecida)"
    )
    args = p.parse_args()
    return args, perfil_dos_argumentos(p, args)


def _mostrar_medidas(medidas: dict[str, object]) -> None:
    """Banda e Eb/N0 medidos na captura, com aviso se a banda não for confiável."""
    if not medidas.get("medido"):
        return
    print(f"Banda a 99%: {medidas['banda_99_khz']} kHz; Eb/N0: {medidas['ebn0_estimado_db']} dB")
    if not medidas.get("banda_99_confiavel", True):
        snr = medidas["snr_na_captura_db"]
        print(
            f"AVISO: banda não confiável (SNR na captura de {snr} dB): "
            "medir a banda numa posição com mais sinal"
        )


def main() -> int:
    """Lê a captura, recebe e grava a saída e o registro."""
    args, perfil = _argumentos()
    modem = perfil.modem()
    config = ConfigReceptor(
        modem,
        perfil.taxa_sps,
        perfil.deslocamento_hz,
        args.limiar,
        args.offset_max_hz,
        args.ber,
        perfil.fec,
    )
    amostras = np.load(args.captura, mmap_mode="r")  # 60 s a 2,048 MS/s = 1 GB: lê por blocos
    inicio = time.time()
    deteccoes = receptor.receber(amostras, config)
    tempo = time.time() - inicio
    periodo = transmissor.amostras_por_quadro(
        modem, fec=perfil.fec, emendar_caudas=perfil.emendar_caudas
    )
    medidas: dict[str, object] = {"medido": False, "motivo": "nenhum quadro detectado"}
    if deteccoes:
        fim = deteccoes[-1].inicio + periodo
        medidas = medicao.medir_captura(
            amostras, deteccoes[0].inicio, fim, perfil.taxa_sps, perfil.taxa_bits
        )
        ebn0 = medidas.get("ebn0_estimado_db")
        if perfil.fec and isinstance(ebn0, float):
            # o Eb/N0 medido é por bit no ar; por bit útil, soma a razão do código
            informacao = quadro.bits_apos_sync(transmissor.TAMANHO_PAYLOAD)
            no_ar = quadro.bits_no_ar_apos_sync(transmissor.TAMANHO_PAYLOAD, fec=True)
            medidas["ebn0_por_bit_util_db"] = round(ebn0 + 10 * np.log10(no_ar / informacao), 2)
    ber = metricas.medir_ber(deteccoes, periodo, 2 * modem.sps) if args.ber else None
    pasta = args.pasta or args.captura.parent
    nome = args.captura.stem
    saida = receptor.gravar_saida(receptor.pacotes_aceitos(deteccoes), pasta / f"{nome}_saida.txt")
    registro = {
        "captura": args.captura.name,
        "versao_do_codigo": versao_do_codigo(),
        "parametros": {k: str(v) for k, v in vars(args).items()},
        "perfil": dataclasses.asdict(perfil),
        "decimacao": config.decimacao,
        "tempo_de_processamento_s": round(tempo, 1),
        **receptor.resumo(deteccoes, len(amostras) / perfil.taxa_sps),
        "medidas_da_captura": medidas,
        "ber": ber,
    }
    caminho = salvar_json(pasta / f"{nome}_rx.json", registro)
    print(f"{registro['pacotes_aceitos']} pacotes aceitos em {tempo:.1f} s")
    _mostrar_medidas(medidas)
    if ber is not None:
        print(f"BER: {ber['bits_errados']}/{ber['bits_comparados']} = {ber['ber']:.2e}")
    print(f"Saída: {saida}\nRegistro: {caminho}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
