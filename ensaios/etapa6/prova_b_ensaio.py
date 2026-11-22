"""Prova B em simulação: a configuração que alcança mais longe com goodput >= 10 kbit/s e PER <= 1%.

Alcance é sensibilidade: a configuração que funciona com o menor C/N0 vai mais longe
(no espaço livre, cada 6 dB a menos de C/N0 necessário dobram a distância). O C/N0
necessário é Eb/N0 para PER de 1% + 10 log10(Rb), então ganha quem combina a
modulação mais sensível com a menor taxa que ainda dá 10 kbit/s de goodput.

Candidatas a 2,048 MS/s: DBPSK RRC em 16, 12,8 e 11,6 kbit/s; GFSK e OOK a 12,8 kbit/s.
Cada ponto: 400 quadros de 128 bytes um atrás do outro, receptor completo, com os
defeitos medidos do enlace real (offset de −1,4 kHz que deriva 35 Hz/s, achado A18;
atraso fracionário; DC de 0,008 do valor eficaz; imagem IQ a −45 dBc).

Uso: python ensaios/etapa6/prova_b_ensaio.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

from sdrlink import canal, metricas, receptor, transmissor
from sdrlink.modem import ConfigModem
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor

RAIZ = Path(__file__).resolve().parents[2]
FS = 2.048e6
DESLOCAMENTO = 250e3
QUADROS = 400
EBN0_DB = np.arange(6.0, 16.5, 1.0)
OFFSET_HZ = -1400.0
DERIVA_HZ_POR_S = -35.0  # pior deriva medida dentro de uma transmissão (A18)
DC_RELATIVO = 0.008
IMAGEM_DBC = -45.0
PER_ALVO = 0.01
GOODPUT_MIN = 10e3
PACOTES_MIN = 500
BITS_UTEIS = 1024
CN0_PROVA_A_DBHZ = 10.31 + 10 * np.log10(FS / 3)  # Eb/N0 para PER 1% do perfil prova-a (Etapa 6a)
CANDIDATAS = [
    ("DBPSK 16 kbit/s", ConfigModem("dbpsk", "rrc", 128)),
    ("DBPSK 12,8 kbit/s", ConfigModem("dbpsk", "rrc", 160)),
    ("DBPSK 11,6 kbit/s", ConfigModem("dbpsk", "rrc", 176)),
    ("GFSK 12,8 kbit/s", ConfigModem("fsk", "gaussiano", 160)),
    ("OOK 12,8 kbit/s", ConfigModem("ook", "rrc", 160)),
]


def defeitos(x, rng):
    """Atraso fracionário, offset com deriva linear, imagem IQ."""
    t = np.arange(len(x)) / FS
    fase = 2 * np.pi * (OFFSET_HZ * t + 0.5 * DERIVA_HZ_POR_S * t**2) + rng.uniform(0, 2 * np.pi)
    y = canal.atrasar(x, 0.37) * np.exp(1j * fase)
    return y + 10 ** (IMAGEM_DBC / 20) * np.conj(y)


def per_do_receptor(cm, ebn0_db, rng):
    """PER, pacotes errados aceitos e tempo do RX por segundo de captura."""
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(QUADROS)])
    s = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, ConfigTransmissor(cm, FS, DESLOCAMENTO), 1e4)])
    s = s[: np.flatnonzero(s)[-1] + 1].astype(complex)
    potencia = np.mean(np.abs(s) ** 2)
    x = defeitos(np.concatenate([np.zeros(int(0.1 * FS)), s]), rng)
    n0 = potencia * cm.sps / 10 ** (ebn0_db / 10)
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    x = (x + DC_RELATIVO * np.sqrt(np.mean(np.abs(x) ** 2))).astype(np.complex64)
    del s
    t0 = time.perf_counter()
    aceitos = receptor.pacotes_aceitos(receptor.receber(x, ConfigReceptor(cm, FS, DESLOCAMENTO)))
    tempo = (time.perf_counter() - t0) / (len(x) / FS)
    certos = sum(p.sequencia < QUADROS and p.payload == metricas.payload_conhecido(p.sequencia) for p in aceitos)
    return 1 - certos / QUADROS, len(aceitos) - certos, tempo


def ebn0_para_per(ebn0, per):
    """Eb/N0 em que a PER cruza 1% (interpolação de log10 da PER)."""
    for k in range(1, len(per)):
        if per[k] <= PER_ALVO < per[k - 1]:
            a, b = np.log10(max(per[k - 1], 1e-4)), np.log10(max(per[k], 1e-4))
            return float(ebn0[k - 1] + (np.log10(PER_ALVO) - a) / (b - a) * (ebn0[k] - ebn0[k - 1]))
    return None


def main():
    rng = np.random.default_rng(20261123)
    linhas = []
    for nome, cm in CANDIDATAS:
        rb = FS / cm.sps
        periodo_s = transmissor.amostras_por_quadro(cm) / FS
        goodput_max = BITS_UTEIS / periodo_s
        baixo, alto = ConfigTransmissor(cm, FS, DESLOCAMENTO).banda_99_hz()
        pontos, per = [], []
        for e in EBN0_DB:  # para depois de dois pontos sem nenhum erro
            pontos.append(per_do_receptor(cm, e, rng))
            per.append(pontos[-1][0])
            if len(per) >= 2 and per[-1] == 0 and per[-2] == 0:
                break
        necessario = ebn0_para_per(EBN0_DB, per)
        cn0 = None if necessario is None else necessario + 10 * np.log10(rb)
        linha = {
            "nome": nome, "modulacao": cm.modulacao, "pulso": cm.pulso, "sps": cm.sps,
            "taxa_bits": round(rb, 1), "banda_99_khz": round((alto - baixo) / 1e3, 1),
            "goodput_max_kbps": round(goodput_max / 1e3, 2),
            "goodput_com_per_1pct_kbps": round(goodput_max * (1 - PER_ALVO) / 1e3, 2),
            "folga_sobre_10_kbps_pct": round(100 * (goodput_max * (1 - PER_ALVO) / GOODPUT_MIN - 1), 1),
            "tempo_para_500_pacotes_s": round(PACOTES_MIN * periodo_s, 1),
            "per_por_ebn0": {f"{e:.0f}": round(p, 4) for e, p in zip(EBN0_DB, per)},
            "errados_aceitos": int(sum(p[1] for p in pontos)),
            "ebn0_per_1pct_db": None if necessario is None else round(necessario, 2),
            "cn0_necessario_dbhz": None if cn0 is None else round(cn0, 2),
            "ganho_sobre_prova_a_db": None if cn0 is None else round(CN0_PROVA_A_DBHZ - cn0, 2),
            "rx_s_por_s": round(float(np.median([p[2] for p in pontos])), 2),
        }
        linhas.append(linha)
        print(json.dumps(linha, ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "prova B em simulação: sensibilidade (C/N0 necessário) com goodput >= 10 kbit/s",
        "taxa_sps": FS, "quadros_por_ponto": QUADROS, "offset_hz": OFFSET_HZ,
        "deriva_hz_por_s": DERIVA_HZ_POR_S, "dc_relativo": DC_RELATIVO, "imagem_dbc": IMAGEM_DBC,
        "cn0_prova_a_dbhz": round(CN0_PROVA_A_DBHZ, 2), "candidatas": linhas,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"prova_b_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
