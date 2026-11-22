"""Prova B com FEC: quanto o código convolucional (sdrlink.codigo) reduz o C/N0 necessário.

Mesmo canal do ensaio sem código (prova_b_ensaio.py): 400 quadros de 128 bytes um
atrás do outro, receptor completo, offset de −1,4 kHz com deriva de 35 Hz/s (A18),
DC de 0,008 do valor eficaz, imagem IQ a −45 dBc. O Eb/N0 da varredura é por bit
no ar; o C/N0 necessário é Eb/N0 (no ar) para PER de 1% + 10 log10(taxa no ar).

Candidatas (DBPSK RRC com FEC, a 2,048 MS/s), as duas taxas que dão 10 kbit/s:
    25,6 kbit/s no ar (80 amostras por bit): goodput sem perdas de 11,9 kbit/s
    23,3 kbit/s no ar (88 amostras por bit): goodput sem perdas de 10,8 kbit/s
A comparação sem código vem do registro mais recente de prova_b_ensaio.py.

Uso: python ensaios/etapa6/prova_b_fec_ensaio.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

from sdrlink import metricas, receptor, transmissor
from sdrlink.modem import ConfigModem
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor

RAIZ = Path(__file__).resolve().parents[2]
FS = 2.048e6
DESLOCAMENTO = 250e3
QUADROS = 400
EBN0_AR_DB = np.arange(2.0, 10.5, 1.0)
OFFSET_HZ = -1400.0
DERIVA_HZ_POR_S = -35.0
DC_RELATIVO = 0.008
IMAGEM_DBC = -45.0
PER_ALVO = 0.01
GOODPUT_MIN = 10e3
PACOTES_MIN = 500
BITS_UTEIS = 1024
BLOCO = 2**22
CANDIDATAS = [
    ("DBPSK 25,6 kbit/s no ar, FEC 1/2", ConfigModem("dbpsk", "rrc", 80)),
    ("DBPSK 23,3 kbit/s no ar, FEC 1/2", ConfigModem("dbpsk", "rrc", 88)),
]


def captura(cm, ebn0_db, rng):
    """0,1 s de ruído e os quadros codificados, com os defeitos do enlace, em blocos (complex64)."""
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(QUADROS)])
    config = ConfigTransmissor(cm, FS, DESLOCAMENTO, fec=True)
    s = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, config, 1e4)])
    s = s[: np.flatnonzero(s)[-1] + 1]
    potencia = float(np.mean(np.abs(s) ** 2))
    n0 = potencia * cm.sps / 10 ** (ebn0_db / 10)
    antes = depois = int(0.1 * FS)  # ruído antes e depois, como numa gravação real
    x = np.zeros(antes + len(s) + depois, dtype=np.complex64)
    x[antes : antes + len(s)] = s
    del s
    fase0 = rng.uniform(0, 2 * np.pi)
    dc = DC_RELATIVO * np.sqrt(potencia + n0)
    for k in range(0, len(x), BLOCO):
        t = np.arange(k, min(k + BLOCO, len(x))) / FS
        fase = 2 * np.pi * (OFFSET_HZ * t + 0.5 * DERIVA_HZ_POR_S * t**2) + fase0
        y = x[k : k + len(t)] * np.exp(1j * fase)
        y = y + 10 ** (IMAGEM_DBC / 20) * np.conj(y)
        y = y + np.sqrt(n0 / 2) * (rng.standard_normal(len(t)) + 1j * rng.standard_normal(len(t))) + dc
        x[k : k + len(t)] = y
    return x


def per_do_receptor(cm, ebn0_db, rng):
    """PER, pacotes errados aceitos, detecções e tempo do RX por segundo de captura."""
    x = captura(cm, ebn0_db, rng)
    t0 = time.perf_counter()
    deteccoes = receptor.receber(x, ConfigReceptor(cm, FS, DESLOCAMENTO, fec=True))
    tempo = (time.perf_counter() - t0) / (len(x) / FS)
    aceitos = receptor.pacotes_aceitos(deteccoes)
    certos = sum(p.sequencia < QUADROS and p.payload == metricas.payload_conhecido(p.sequencia) for p in aceitos)
    return 1 - certos / QUADROS, len(aceitos) - certos, len(deteccoes), tempo


def ebn0_para_per(ebn0, per):
    """Eb/N0 em que a PER cruza 1% (interpolação de log10 da PER)."""
    for k in range(1, len(per)):
        if per[k] <= PER_ALVO < per[k - 1]:
            a, b = np.log10(max(per[k - 1], 1e-4)), np.log10(max(per[k], 1e-4))
            return float(ebn0[k - 1] + (np.log10(PER_ALVO) - a) / (b - a) * (ebn0[k] - ebn0[k - 1]))
    return None


def sem_codigo():
    """Resultados da prova B sem código (registro mais recente de prova_b_ensaio.py)."""
    registros = sorted((RAIZ / "dados" / "logs").glob("prova_b_2*.json"))
    if not registros:
        return None, []
    return registros[-1].name, json.loads(registros[-1].read_text(encoding="utf-8"))["candidatas"]


def main():
    rng = np.random.default_rng(20261124)
    linhas = []
    for nome, cm in CANDIDATAS:
        rb = FS / cm.sps
        periodo_s = transmissor.amostras_por_quadro(cm, fec=True) / FS
        goodput_max = BITS_UTEIS / periodo_s
        pontos, per = [], []
        for e in EBN0_AR_DB:  # para depois de dois pontos sem nenhum erro
            pontos.append(per_do_receptor(cm, e, rng))
            per.append(pontos[-1][0])
            if len(per) >= 2 and per[-1] == 0 and per[-2] == 0:
                break
        necessario = ebn0_para_per(EBN0_AR_DB, per)
        linha = {
            "nome": nome, "sps": cm.sps, "taxa_no_ar": round(rb, 1),
            "bits_por_quadro_no_fluxo": round(periodo_s * rb, 1),
            "goodput_max_kbps": round(goodput_max / 1e3, 2),
            "folga_sobre_10_kbps_pct": round(100 * (goodput_max * (1 - PER_ALVO) / GOODPUT_MIN - 1), 1),
            "tempo_para_500_pacotes_s": round(PACOTES_MIN * periodo_s, 1),
            "per_por_ebn0_no_ar": {f"{e:.0f}": round(p[0], 4) for e, p in zip(EBN0_AR_DB, pontos)},
            "deteccoes_por_ebn0_no_ar": {f"{e:.0f}": p[2] for e, p in zip(EBN0_AR_DB, pontos)},
            "errados_aceitos": int(sum(p[1] for p in pontos)),
            "ebn0_no_ar_per_1pct_db": None if necessario is None else round(necessario, 2),
            "cn0_necessario_dbhz": None if necessario is None else round(necessario + 10 * np.log10(rb), 2),
            "rx_s_por_s": round(float(np.median([p[3] for p in pontos])), 2),
        }
        linhas.append(linha)
        print(json.dumps(linha, ensure_ascii=False), flush=True)
    origem, referencias = sem_codigo()
    melhor_sem = min((c["cn0_necessario_dbhz"] for c in referencias if c.get("cn0_necessario_dbhz")), default=None)
    for linha in linhas:
        if melhor_sem is not None and linha["cn0_necessario_dbhz"] is not None:
            linha["ganho_sobre_o_melhor_sem_codigo_db"] = round(melhor_sem - linha["cn0_necessario_dbhz"], 2)
    resultado = {
        "ensaio": "prova B com FEC: C/N0 necessário com o código convolucional K = 7, taxa 1/2",
        "taxa_sps": FS, "quadros_por_ponto": QUADROS, "offset_hz": OFFSET_HZ,
        "deriva_hz_por_s": DERIVA_HZ_POR_S, "dc_relativo": DC_RELATIVO, "imagem_dbc": IMAGEM_DBC,
        "referencia_sem_codigo": origem, "melhor_cn0_sem_codigo_dbhz": melhor_sem,
        "candidatas": linhas, "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"prova_b_fec_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
