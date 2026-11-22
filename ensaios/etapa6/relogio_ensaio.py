"""Diferença de relógio de amostragem entre o Pluto e o RTL: quanto cada perfil final aguenta.

O RX estima o instante uma vez por quadro e não acompanha a deriva dentro dele (como a
referência, que o enunciado descreve sem malha de recuperação de relógio). Com relógios
diferentes, o último símbolo de um quadro chega deslocado de ppm·10⁻⁶ × duração do quadro.
O quadro mais longo é o da prova B (177 mil amostras). A correção de ppm do RTL ajusta o
oscilador e a taxa de amostragem juntos (o mesmo cristal), então depois da calibração a
diferença de relógio é a do offset residual: 1,6 kHz em 919,5 MHz, cerca de 2 ppm.

Cada perfil é recebido com o sinal reamostrado (sdrlink.canal.reamostrar), 2 dB acima do
Eb/N0 necessário para PER de 1%, com várias diferenças de relógio.

Uso: python ensaios/etapa6/relogio_ensaio.py
"""

import json
import sys
from pathlib import Path

import numpy as np

from sdrlink import canal, config, metricas, receptor, transmissor
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor

RAIZ = Path(__file__).resolve().parents[2]
PPM = (0.0, 2.0, 20.0, 50.0, 100.0, -100.0, 200.0)
CASOS = [  # (perfil, Eb/N0 por bit no ar, quadros)
    ("prova-a", 14.0, 300),
    ("prova-a-fec", 6.0, 300),
    ("prova-a-dbpsk", 12.0, 300),
    ("prova-b", 6.0, 60),
]


def main():
    linhas = []
    for nome, ebn0, quadros in CASOS:
        p = config.perfil(nome)
        cm = p.modem()
        ct = ConfigTransmissor(cm, p.taxa_sps, p.deslocamento_hz, fec=p.fec, emendar_caudas=p.emendar_caudas)
        pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(quadros)])
        s = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, ct, 1e4)]).astype(complex)
        s = s[: np.flatnonzero(s)[-1] + 1]
        s = np.concatenate([np.zeros(20_000), s, np.zeros(20_000)])
        n0 = np.mean(np.abs(s) ** 2) * cm.sps / cm.bits_por_simbolo / 10 ** (ebn0 / 10)
        certos = {}
        for ppm in PPM:
            rng = np.random.default_rng(1)
            y = canal.reamostrar(s, ppm)
            y = y + np.sqrt(n0 / 2) * (rng.standard_normal(len(y)) + 1j * rng.standard_normal(len(y)))
            d = receptor.receber(y, ConfigReceptor(cm, p.taxa_sps, p.deslocamento_hz, fec=p.fec))
            aceitos = receptor.pacotes_aceitos(d)
            certos[f"{ppm:+g}"] = sum(q.payload == metricas.payload_conhecido(q.sequencia) for q in aceitos)
        quadro_amostras = transmissor.amostras_por_quadro(cm, fec=p.fec, emendar_caudas=p.emendar_caudas)
        linha = {
            "perfil": nome, "ebn0_no_ar_db": ebn0, "quadros": quadros, "amostras_por_quadro": quadro_amostras,
            "deriva_no_quadro_a_50_ppm_amostras": round(50e-6 * quadro_amostras, 2),
            "amostras_por_simbolo": cm.sps, "certos_por_ppm": certos,
        }
        linhas.append(linha)
        print(json.dumps(linha, ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "diferença de relógio de amostragem × perfis finais", "ppm": PPM, "casos": linhas,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"relogio_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
