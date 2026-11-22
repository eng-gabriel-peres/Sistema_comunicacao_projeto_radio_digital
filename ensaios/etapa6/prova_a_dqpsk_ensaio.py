"""Prova A com DQPSK: o corpo com 2 bits por símbolo dobra a taxa na mesma banda; quanto custa?

Mesmo canal do ensaio da Etapa 6a (prova_a_ensaio.py): 1000 quadros de 128 bytes por
ponto, um atrás do outro, receptor completo, com os defeitos medidos na captura real
de 04/11 (offset de −1,4 kHz, atraso de 0,37 amostra, DC de 0,008 do valor eficaz,
imagem IQ a −45 dBc). O Eb/N0 é por bit no ar (na DQPSK, Eb = Es/2).

Candidatas a 2,048 MS/s, RRC com β = 0,25 e o sinal de +50 a +800 kHz do LO:
    DBPSK, 3 amostras por símbolo (o perfil prova-a, referência)
    DQPSK, 3 amostras por símbolo: 1365 kbit/s no corpo, mesma banda
    DQPSK, 4 amostras por símbolo: 1024 kbit/s no corpo, 563 kHz de banda
    DQPSK com FEC, 3 amostras por símbolo: o goodput da DBPSK com menos C/N0?

Para cada uma: banda a 99%, goodput sem perdas pelo período real do quadro, Eb/N0 e
C/N0 para PER de 1%, margem diante da bancada de 04/11 e tempo do RX.

Uso: python ensaios/etapa6/prova_a_dqpsk_ensaio.py
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prova_a_ensaio as base  # noqa: E402

from sdrlink import metricas, receptor, transmissor  # noqa: E402
from sdrlink.modem import ConfigModem  # noqa: E402
from sdrlink.receptor import ConfigReceptor  # noqa: E402
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo  # noqa: E402
from sdrlink.transmissor import ConfigTransmissor  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
FS = base.FS
QUADROS = 1000
EBN0_DB = np.arange(6.0, 16.5, 1.0)
EBN0_FEC_DB = np.arange(2.0, 10.5, 1.0)  # com FEC a PER já é zero a 6 dB (primeira rodada)
DESLOCAMENTO = 425e3  # o do perfil prova-a
BITS_UTEIS = 1024
CANDIDATAS = [
    ("DBPSK 682,7 kbit/s (prova-a)", ConfigModem("dbpsk", "rrc", 3, beta=0.25), False),
    ("DQPSK 1365 kbit/s", ConfigModem("dqpsk", "rrc", 3, beta=0.25), False),
    ("DQPSK 1024 kbit/s", ConfigModem("dqpsk", "rrc", 4, beta=0.25), False),
    ("DQPSK 1365 kbit/s no ar, FEC 1/2", ConfigModem("dqpsk", "rrc", 3, beta=0.25), True),
]


def captura(cm, fec, ebn0_db, rng):
    """Quadros um atrás do outro entre 0,1 s de ruído, com os defeitos do RTL (Eb por bit no ar)."""
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(QUADROS)])
    blocos = transmissor.fluxo(pacotes, ConfigTransmissor(cm, FS, DESLOCAMENTO, fec=fec), 1e3)
    s = np.concatenate([b for b, _ in blocos]).astype(complex)
    s = s[: np.flatnonzero(s)[-1] + 1]
    potencia = np.mean(np.abs(s) ** 2)
    margem = np.zeros(int(0.1 * FS))
    x = base.defeitos_do_rtl(np.concatenate([margem, s, margem]), rng)
    n0 = potencia * cm.sps / cm.bits_por_simbolo / 10 ** (ebn0_db / 10)
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    return x + base.DC_RELATIVO * np.sqrt(np.mean(np.abs(x) ** 2))


def per_do_receptor(cm, fec, ebn0_db, rng):
    """PER, pacotes errados aceitos e tempo do RX por segundo de captura."""
    x = captura(cm, fec, ebn0_db, rng)
    t0 = time.perf_counter()
    d = receptor.receber(x, ConfigReceptor(cm, FS, DESLOCAMENTO, fec=fec))
    tempo = (time.perf_counter() - t0) / (len(x) / FS)
    aceitos = receptor.pacotes_aceitos(d)
    certos = sum(p.sequencia < QUADROS and p.payload == metricas.payload_conhecido(p.sequencia) for p in aceitos)
    return 1 - certos / QUADROS, len(aceitos) - certos, tempo


def main():
    cn0 = base.cn0_da_bancada()
    rng = np.random.default_rng(20261125)
    linhas = []
    for nome, cm, fec in CANDIDATAS:
        rb_ar = FS / cm.sps * cm.bits_por_simbolo
        baixo, alto = ConfigTransmissor(cm, FS, DESLOCAMENTO).banda_99_hz()
        goodput = FS * BITS_UTEIS / transmissor.amostras_por_quadro(cm, fec=fec)
        grade = EBN0_FEC_DB if fec else EBN0_DB
        pontos, per = [], []
        for e in grade:  # para depois de dois pontos sem nenhum erro
            pontos.append(per_do_receptor(cm, fec, e, rng))
            per.append(pontos[-1][0])
            if len(per) >= 2 and per[-1] == 0 and per[-2] == 0:
                break
        necessario = base.ebn0_para_per(grade, per)
        cn0_necessario = None if necessario is None else necessario + 10 * np.log10(rb_ar)
        linha = {
            "nome": nome, "modulacao": cm.modulacao, "sps": cm.sps, "fec": fec,
            "taxa_no_ar": round(rb_ar, 1), "banda_99_khz": round((alto - baixo) / 1e3, 1),
            "faixa_khz": [round(baixo / 1e3, 1), round(alto / 1e3, 1)],
            "goodput_sem_perda_kbps": round(goodput / 1e3, 1),
            "per_por_ebn0_no_ar": {f"{e:.0f}": round(p[0], 4) for e, p in zip(grade, pontos)},
            "errados_aceitos": int(sum(p[1] for p in pontos)),
            "ebn0_no_ar_per_1pct_db": None if necessario is None else round(necessario, 2),
            "cn0_necessario_dbhz": None if cn0_necessario is None else round(cn0_necessario, 2),
            "margem_na_bancada_db": None if cn0_necessario is None else round(cn0 - cn0_necessario, 1),
            "rx_s_por_s": round(float(np.median([p[2] for p in pontos])), 2),
        }
        linhas.append(linha)
        print(json.dumps(linha, ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "prova A com DQPSK: taxa, banda, PER do receptor completo e margem",
        "taxa_sps": FS, "quadros_por_ponto": QUADROS, "deslocamento_hz": DESLOCAMENTO,
        "offset_hz": base.OFFSET_HZ, "dc_relativo": base.DC_RELATIVO, "imagem_dbc": base.IMAGEM_DBC,
        "cn0_bancada_dbhz": round(cn0, 1), "candidatas": linhas,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"prova_a_dqpsk_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
