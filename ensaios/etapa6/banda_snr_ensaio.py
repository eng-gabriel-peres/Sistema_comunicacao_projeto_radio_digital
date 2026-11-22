"""Banda a 99% medida na captura × SNR na captura, com o sinal estreito da prova B.

A medida (sdrlink.medicao) subtrai a DEP de um trecho só de ruído da DEP do trecho com
sinal. Com sinal estreito e fraco, o resíduo dessa subtração, somado nos 2 MHz da
captura, passa da potência do sinal e a banda perde o sentido (bloco 13). Este ensaio
mede a banda do perfil prova-b (30 kHz no TX) em vários Eb/N0, com 4 sementes e dois
tamanhos de captura (curta: 0,5 s de ruído e 60 quadros; longa: 1 s de ruído e 300
quadros), e registra a SNR na captura e a marcação de confiança.

Uso: python ensaios/etapa6/banda_snr_ensaio.py
"""

import json
import sys
from pathlib import Path

import numpy as np

from sdrlink import config, medicao, metricas, transmissor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor

RAIZ = Path(__file__).resolve().parents[2]
EBN0_DB = (6.0, 10.0, 15.0, 20.0, 30.0)
SEMENTES = (1, 2, 3, 4)
CAPTURAS = {"curta": (0.5, 60), "longa": (1.0, 300)}  # (segundos de ruído antes, quadros)


def main():
    perfil = config.perfil("prova-b")
    cm, fs = perfil.modem(), perfil.taxa_sps
    tx = ConfigTransmissor(cm, fs, perfil.deslocamento_hz, fec=perfil.fec)
    baixo, alto = tx.banda_99_hz()
    linhas = []
    for nome, (ruido_s, quadros) in CAPTURAS.items():
        pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(quadros)])
        s = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, tx, 1e4)]).astype(complex)
        s = s[: np.flatnonzero(s)[-1] + 1]
        potencia = np.mean(np.abs(s) ** 2)
        ruido = int(ruido_s * fs)
        for ebn0 in EBN0_DB:
            bandas, confiaveis, snrs = [], [], []
            for semente in SEMENTES:
                rng = np.random.default_rng(semente)
                n0 = potencia * (fs / perfil.taxa_bits) / 10 ** (ebn0 / 10)
                x = np.concatenate([np.zeros(ruido), s])
                x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))
                r = medicao.medir_captura(x, ruido, len(x), fs, perfil.taxa_bits)
                bandas.append(r["banda_99_khz"])
                confiaveis.append(r["banda_99_confiavel"])
                snrs.append(r["snr_na_captura_db"])
            linha = {
                "captura": nome, "ebn0_por_bit_db": ebn0, "snr_na_captura_db": round(float(np.median(snrs)), 1),
                "bandas_khz": bandas, "confiavel": confiaveis,
            }
            linhas.append(linha)
            print(json.dumps(linha, ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "banda a 99% medida × SNR na captura (perfil prova-b)",
        "banda_no_tx_khz": round((alto - baixo) / 1e3, 1), "limite_de_confianca_db": medicao.SNR_MIN_BANDA_DB,
        "pontos": linhas, "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"banda_snr_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
