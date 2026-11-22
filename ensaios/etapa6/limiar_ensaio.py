"""Limiar de detecção na prova B com FEC: 0,5 (o padrão) contra 0,4.

Com FEC cada bit no ar leva metade da energia e o prefixo de 29 bits, que não é
codificado, fica 3 dB mais fraco: a detecção vira o gargalo (bloco 09). Uma detecção
falsa só custa processamento, porque o CRC a rejeita. O ensaio mede, no canal da prova B
(offset de −1,4 kHz com deriva de 35 Hz/s, DC, imagem IQ), a PER com os dois limiares,
o C/N0 necessário de cada um e as detecções falsas em 30 s só de ruído.

Uso: python ensaios/etapa6/limiar_ensaio.py
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prova_b_fec_ensaio as base  # noqa: E402

from sdrlink import config, metricas, receptor  # noqa: E402
from sdrlink.receptor import ConfigReceptor  # noqa: E402
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
LIMIARES = (0.5, 0.4)
EBN0_AR_DB = np.arange(2.5, 6.5, 0.5)
QUADROS = 400
RUIDO_S = 30.0


def main():
    p = config.perfil("prova-b")
    cm = p.modem()
    base.QUADROS = QUADROS
    curvas = {f"{lim}": [] for lim in LIMIARES}
    deteccoes = {f"{lim}": [] for lim in LIMIARES}
    for k, ebn0 in enumerate(EBN0_AR_DB):
        x = base.captura(cm, ebn0, np.random.default_rng(3000 + k))  # o mesmo sinal para os dois limiares
        for lim in LIMIARES:
            d = receptor.receber(x, ConfigReceptor(cm, p.taxa_sps, p.deslocamento_hz, fec=True, limiar=lim))
            aceitos = receptor.pacotes_aceitos(d)
            certos = sum(q.sequencia < QUADROS and q.payload == metricas.payload_conhecido(q.sequencia) for q in aceitos)
            assert len(aceitos) == certos, "pacote errado aceito"
            curvas[f"{lim}"].append(round(1 - certos / QUADROS, 4))
            deteccoes[f"{lim}"].append(len(d))
        print(f"{ebn0} dB: " + ", ".join(f"limiar {lim}: PER {curvas[f'{lim}'][-1]:.3f}" for lim in LIMIARES), flush=True)
    necessario = {lim: base.ebn0_para_per(EBN0_AR_DB, curvas[lim]) for lim in curvas}
    rng = np.random.default_rng(7)
    n = int(RUIDO_S * p.taxa_sps)
    ruido = (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex64)
    falsas = {}
    for lim in LIMIARES:
        d = receptor.receber(ruido, ConfigReceptor(cm, p.taxa_sps, p.deslocamento_hz, fec=True, limiar=lim))
        falsas[f"{lim}"] = {"deteccoes": len(d), "aceitas": len(receptor.pacotes_aceitos(d))}
    resultado = {
        "ensaio": "limiar de detecção na prova B com FEC", "perfil": "prova-b", "quadros_por_ponto": QUADROS,
        "ebn0_no_ar_db": [float(e) for e in EBN0_AR_DB], "per": curvas, "deteccoes": deteccoes,
        "ebn0_per_1pct_db": {lim: None if v is None else round(v, 2) for lim, v in necessario.items()},
        "cn0_necessario_dbhz": {lim: None if v is None else round(v + 10 * np.log10(p.taxa_bits), 2)
                                for lim, v in necessario.items()},
        "so_ruido_30_s": falsas,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    print(json.dumps({k: resultado[k] for k in ("ebn0_per_1pct_db", "cn0_necessario_dbhz", "so_ruido_30_s")}, ensure_ascii=False))
    saida = RAIZ / "dados" / "logs" / f"limiar_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
