"""Emendar as caudas do RRC (bloco 12): quanto goodput ganha e quanto de sensibilidade custa.

Com a emenda, o quadro seguinte começa logo depois do último símbolo do anterior e as
caudas do pulso se somam; sem ela, cada quadro espera a cauda do anterior terminar
(12 símbolos a mais por quadro). Nos instantes de amostragem o RRC casado não tem
interferência entre símbolos, mas o modelo do prefixo que o RX procura começa do
silêncio, e agora os primeiros símbolos do prefixo dividem espaço com a cauda da
guarda do quadro anterior: a detecção pode perder alguma coisa em sinal fraco.

Mesmo canal da Etapa 6a (offset de −1,4 kHz, atraso de 0,37 amostra, DC, imagem IQ a
−45 dBc), 1000 quadros por ponto, receptor completo, nas duas configurações da prova A,
com e sem a emenda.

Uso: python ensaios/etapa6/emenda_caudas_ensaio.py
"""

import json
import sys
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
DESLOCAMENTO = 425e3
BITS_UTEIS = 1024
CANDIDATAS = [
    ("DQPSK 1365 kbit/s (prova-a)", ConfigModem("dqpsk", "rrc", 3, beta=0.25), np.arange(10.0, 14.5, 1.0)),
    ("DBPSK 682,7 kbit/s (prova-a-dbpsk)", ConfigModem("dbpsk", "rrc", 3, beta=0.25), np.arange(8.0, 12.5, 1.0)),
]


def captura(cm, emendar, ebn0_db, rng):
    """Quadros um atrás do outro entre 0,1 s de ruído, com os defeitos do RTL (Eb por bit no ar)."""
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(QUADROS)])
    config = ConfigTransmissor(cm, FS, DESLOCAMENTO, emendar_caudas=emendar)
    s = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, config, 1e3)]).astype(complex)
    s = s[: np.flatnonzero(s)[-1] + 1]
    potencia = np.mean(np.abs(s) ** 2)
    margem = np.zeros(int(0.1 * FS))
    x = base.defeitos_do_rtl(np.concatenate([margem, s, margem]), rng)
    n0 = potencia * cm.sps / cm.bits_por_simbolo / 10 ** (ebn0_db / 10)
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
    return x + base.DC_RELATIVO * np.sqrt(np.mean(np.abs(x) ** 2))


def medir(cm, emendar, ebn0_db, semente):
    """PER, quadros nunca detectados (sem nenhuma detecção perto do início) e errados aceitos."""
    x = captura(cm, emendar, ebn0_db, np.random.default_rng(semente))
    d = receptor.receber(x, ConfigReceptor(cm, FS, DESLOCAMENTO))
    aceitos = receptor.pacotes_aceitos(d)
    certos = {p.sequencia for p in aceitos if p.payload == metricas.payload_conhecido(p.sequencia)}
    periodo = transmissor.amostras_por_quadro(cm, emendar_caudas=emendar)
    inicio0 = int(0.1 * FS)
    tolerancia = 2 * cm.sps
    detectados = sum(
        any(abs(q.inicio - (inicio0 + k * periodo)) < tolerancia for q in d) for k in range(QUADROS)
    )
    return 1 - len(certos) / QUADROS, QUADROS - detectados, len(aceitos) - len(certos)


def main():
    linhas = []
    for nome, cm, grade in CANDIDATAS:
        for emendar in (False, True):
            periodo = transmissor.amostras_por_quadro(cm, emendar_caudas=emendar)
            pontos = [medir(cm, emendar, e, 1000 + k) for k, e in enumerate(grade)]  # mesmas sementes
            per = [p[0] for p in pontos]
            necessario = base.ebn0_para_per(grade, per)
            linha = {
                "nome": nome, "emendar_caudas": emendar,
                "simbolos_por_quadro_no_fluxo": periodo // cm.sps,
                "goodput_sem_perda_kbps": round(FS * BITS_UTEIS / periodo / 1e3, 1),
                "per_por_ebn0": {f"{e:.0f}": round(p[0], 4) for e, p in zip(grade, pontos)},
                "nao_detectados_por_ebn0": {f"{e:.0f}": p[1] for e, p in zip(grade, pontos)},
                "errados_aceitos": int(sum(p[2] for p in pontos)),
                "ebn0_per_1pct_db": None if necessario is None else round(necessario, 2),
            }
            linhas.append(linha)
            print(json.dumps(linha, ensure_ascii=False), flush=True)
    comparacao = []
    for k in range(0, len(linhas), 2):
        sem, com = linhas[k], linhas[k + 1]
        if sem["ebn0_per_1pct_db"] is not None and com["ebn0_per_1pct_db"] is not None:
            comparacao.append({
                "nome": sem["nome"],
                "ganho_de_goodput_pct": round(100 * (com["goodput_sem_perda_kbps"] / sem["goodput_sem_perda_kbps"] - 1), 2),
                "custo_em_ebn0_db": round(com["ebn0_per_1pct_db"] - sem["ebn0_per_1pct_db"], 2),
            })
    print(json.dumps(comparacao, ensure_ascii=False))
    resultado = {
        "ensaio": "emenda das caudas do RRC: goodput × sensibilidade", "quadros_por_ponto": QUADROS,
        "candidatas": linhas, "comparacao": comparacao,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"emenda_caudas_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
