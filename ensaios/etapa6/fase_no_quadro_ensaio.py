"""Quanto a fase real do par Pluto + RTL anda dentro de um quadro de cada perfil.

Uma detecção coerente estimaria a fase e o offset uma vez por quadro (no bloco 09 ela
ganharia 0,3 dB com FEC e 0,8 dB sem, com sincronismo ideal). O que sobra depois disso é
o desvio da fase em torno de uma reta (fase inicial + offset) ao longo do quadro. O
ensaio mede esse desvio na trajetória de fase real dos tons de 04/11/2026 (filtrada em
2 kHz, sem os saltos de emenda), em janelas do tamanho do quadro de cada perfil, e o
converte na perda de uma detecção coerente com esse erro de fase: 20·log10(cos θ).

Uso: python ensaios/etapa6/fase_no_quadro_ensaio.py   (cerca de 1 min)
"""

import json
import sys
from pathlib import Path

import numpy as np

from sdrlink import config, fase, transmissor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
TONS = ("calibracao_20261104_100631_depois", "calibracao_20261104_100917_depois")
FS = 2.048e6
BANDA_HZ = 2e3
PERFIS = ("prova-a", "prova-a-fec", "prova-a-dbpsk", "prova-b")


def desvios_no_quadro(ph, n):
    """Desvio eficaz da fase em torno da reta ajustada, em janelas de n amostras."""
    t = np.arange(n)
    saida = []
    for k in range(0, len(ph) - n, n):
        trecho = ph[k : k + n]
        saida.append(float(np.sqrt(np.mean((trecho - np.polyval(np.polyfit(t, trecho, 1), t)) ** 2))))
    return np.array(saida)


def main():
    resultado = {"ensaio": "desvio da fase real dentro de um quadro", "banda_hz": BANDA_HZ, "tons": {}}
    for nome in TONS:
        x = np.load(RAIZ / "dados" / "calibracao" / f"{nome}.npy")
        ph = fase.trajetoria(fase.fase_do_tom(x, FS, banda_hz=BANDA_HZ), len(x))
        por_perfil = {}
        for perfil in PERFIS:
            p = config.perfil(perfil)
            amostras = transmissor.amostras_por_quadro(p.modem(), fec=p.fec, emendar_caudas=p.emendar_caudas)
            n = int(amostras * FS / p.taxa_sps)
            d = desvios_no_quadro(ph, n)
            p95 = float(np.percentile(d, 95))
            por_perfil[perfil] = {
                "quadro_ms": round(1e3 * n / FS, 2), "janelas": len(d),
                "mediana_rad": round(float(np.median(d)), 4), "p95_rad": round(p95, 4),
                "maximo_rad": round(float(d.max()), 4),
                "perda_coerente_p95_db": round(float(-20 * np.log10(np.cos(p95))), 2),
                "perda_coerente_maximo_db": round(float(-20 * np.log10(np.cos(d.max()))), 2),
            }
            print(nome, perfil, por_perfil[perfil], flush=True)
        resultado["tons"][nome] = por_perfil
    resultado["versao_do_codigo"] = versao_do_codigo(ignorar=("dados/", "docs/"))
    saida = RAIZ / "dados" / "logs" / f"fase_no_quadro_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
