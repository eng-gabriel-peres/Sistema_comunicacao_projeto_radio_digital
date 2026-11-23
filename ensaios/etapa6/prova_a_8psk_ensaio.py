"""Prova A com 8-PSK coerente no receptor completo (bloco 24): quanto C/N0 ela pede de verdade?

O mesmo canal da DQPSK (prova_a_dqpsk_ensaio.py): 1000 quadros de 128 bytes por ponto,
um atrás do outro, com os defeitos medidos na captura real de 04/11 (offset de −1,4 kHz,
atraso de 0,37 amostra, DC, imagem IQ a −45 dBc). Agora o instante, o offset e a fase
são estimados pelo receptor de produção. Três casos, a 2,048 MS/s, RRC β = 0,25, 3
amostras por símbolo:
    DQPSK 1365 kbit/s (a referência, o prova-a)
    8-PSK 2048 kbit/s
    8-PSK 2048 kbit/s com a trajetória de fase real dos tons de 04/11 somada

Para cada um: Eb/N0 e C/N0 para PER de 1%, margem diante da bancada de 04/11, goodput
sem perdas pelo período do quadro (com as caudas emendadas, como nos perfis) e tempo do RX.

Uso: python ensaios/etapa6/prova_a_8psk_ensaio.py   (cerca de 10 min)
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prova_a_dqpsk_ensaio as dq  # noqa: E402
import prova_a_ensaio as base  # noqa: E402

from sdrlink import fase, metricas, receptor, transmissor  # noqa: E402
from sdrlink.modem import ConfigModem  # noqa: E402
from sdrlink.receptor import ConfigReceptor  # noqa: E402
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
FS = base.FS
QUADROS = 1000
EBN0_DB = np.arange(10.0, 17.5, 0.5)
TOM = "calibracao_20261104_100631_depois"
CASOS = [
    ("DQPSK 1365 kbit/s (prova-a)", ConfigModem("dqpsk", "rrc", 3, beta=0.25), False),
    ("8-PSK 2048 kbit/s (prova-a-8psk)", ConfigModem("8psk", "rrc", 3, beta=0.25), False),
    ("8-PSK 2048 kbit/s com a fase real", ConfigModem("8psk", "rrc", 3, beta=0.25), True),
]


def per_do_receptor(cm, ebn0_db, rng, trajetoria):
    """PER, pacotes errados aceitos e tempo do RX por segundo de captura."""
    x = dq.captura(cm, False, ebn0_db, rng)
    if trajetoria is not None:
        x = x * np.exp(1j * trajetoria[: len(x)])
    t0 = time.perf_counter()
    d = receptor.receber(x, ConfigReceptor(cm, FS, dq.DESLOCAMENTO))
    tempo = (time.perf_counter() - t0) / (len(x) / FS)
    aceitos = receptor.pacotes_aceitos(d)
    certos = sum(p.sequencia < QUADROS and p.payload == metricas.payload_conhecido(p.sequencia) for p in aceitos)
    return 1 - certos / QUADROS, len(aceitos) - certos, tempo


def main():
    dq.QUADROS = QUADROS
    cn0 = base.cn0_da_bancada()
    tom = fase.fase_do_tom(np.load(RAIZ / "dados" / "calibracao" / f"{TOM}.npy"), FS, banda_hz=2e3)
    trajetoria = fase.trajetoria(tom, 2**23)
    rng = np.random.default_rng(20261124)
    linhas = []
    for nome, cm, com_fase in CASOS:
        rb = FS / cm.sps * cm.bits_por_simbolo
        goodput = FS * dq.BITS_UTEIS / transmissor.amostras_por_quadro(cm, emendar_caudas=True)
        pontos, per = [], []
        for e in EBN0_DB:  # para depois de dois pontos sem nenhum erro
            pontos.append(per_do_receptor(cm, e, rng, trajetoria if com_fase else None))
            per.append(pontos[-1][0])
            if len(per) >= 2 and per[-1] == 0 and per[-2] == 0:
                break
        necessario = base.ebn0_para_per(EBN0_DB[: len(per)], per)
        cn0_necessario = None if necessario is None else necessario + 10 * np.log10(rb)
        linha = {
            "nome": nome, "modulacao": cm.modulacao, "fase_real": com_fase, "taxa_no_ar": round(rb, 1),
            "goodput_sem_perda_kbps": round(goodput / 1e3, 1),
            "per_por_ebn0_no_ar": {f"{e:.1f}": round(p[0], 4) for e, p in zip(EBN0_DB, pontos)},
            "errados_aceitos": int(sum(p[1] for p in pontos)),
            "ebn0_no_ar_per_1pct_db": None if necessario is None else round(necessario, 2),
            "cn0_necessario_dbhz": None if cn0_necessario is None else round(cn0_necessario, 2),
            "margem_na_bancada_db": None if cn0_necessario is None else round(cn0 - cn0_necessario, 1),
            "rx_s_por_s": round(float(np.median([p[2] for p in pontos])), 2),
        }
        linhas.append(linha)
        print(json.dumps(linha, ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "prova A com 8-PSK coerente no receptor completo",
        "taxa_sps": FS, "quadros_por_ponto": QUADROS, "deslocamento_hz": dq.DESLOCAMENTO,
        "offset_hz": base.OFFSET_HZ, "dc_relativo": base.DC_RELATIVO, "imagem_dbc": base.IMAGEM_DBC,
        "cn0_bancada_dbhz": round(cn0, 1), "casos": linhas,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"prova_a_8psk_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
