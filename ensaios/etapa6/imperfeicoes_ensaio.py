"""Imperfeições do hardware nos perfis finais: ruído de fase do par Pluto + RTL e o ADC de 8 bits.

1. Ruído de fase **medido**: nas duas gravações do tom do Pluto da equipe (04/11/2026,
   RTL aquecido), L(f) e a variação de fase em um símbolo de cada perfil, com a parte
   do ruído branco da própria gravação descontada (sdrlink.fase).
2. A trajetória de fase **real** (filtrada em 2 kHz, onde o ruído de fase aparece acima
   do piso) aplicada aos sinais simulados de cada perfil, 0,5 dB abaixo do Eb/N0 de PER
   1%: a PER com e sem ela, no mesmo ruído.
3. Margem: ruído de fase de Wiener cada vez maior, 1 dB acima do Eb/N0 de PER 1%, até a
   PER passar de 1%.
4. ADC de 8 bits do RTL: nível eficaz na entrada do ADC de −60 a −3 dBFS, 1 dB acima do
   Eb/N0 de PER 1%: a janela de ganho do RX.

Uso: python ensaios/etapa6/imperfeicoes_ensaio.py   (cerca de 15 min)
"""

import json
import sys
from pathlib import Path

import numpy as np

from sdrlink import canal, config, fase, metricas, receptor, transmissor
from sdrlink.hw import rtl_rx
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor

RAIZ = Path(__file__).resolve().parents[2]
TONS = ("calibracao_20261104_100631_depois", "calibracao_20261104_100917_depois")
FS_TOM = 2.048e6
AFASTAMENTOS_HZ = (300.0, 1e3, 3e3, 10e3, 30e3, 100e3, 300e3)
ATRASOS_LONGOS = (800, 3200)
BANDA_TRAJETORIA_HZ = 2e3
CASOS = [  # (perfil, Eb/N0 por bit no ar de PER 1%, quadros)
    ("prova-a", 12.0, 400),
    ("prova-a-24", 12.2, 400),
    ("prova-a-fec", 4.0, 300),
    ("prova-a-dbpsk", 10.4, 300),
    ("prova-b", 4.1, 120),
]
LARGURAS_HZ = (0.0, 10.0, 30.0, 100.0, 300.0, 1e3, 3e3, 10e3, 30e3)
NIVEIS_DBFS = (-60.0, -50.0, -40.0, -30.0, -20.0, -12.0, -6.0, -3.0)
OFFSET_HZ = -1400.0
PER_ALVO = 0.01


def sinal_do_perfil(p, quadros):
    cm = p.modem()
    ct = ConfigTransmissor(cm, p.taxa_sps, p.deslocamento_hz, fec=p.fec, emendar_caudas=p.emendar_caudas)
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(quadros)])
    s = np.concatenate([b for b, _ in transmissor.fluxo(pacotes, ct, 1e4)]).astype(complex)
    s = s[: np.flatnonzero(s)[-1] + 1]
    s = np.concatenate([np.zeros(20_000), s, np.zeros(20_000)])
    return canal.girar(s, OFFSET_HZ, p.taxa_sps), cm


def per(p, cm, y, quadros):
    d = receptor.receber(y, ConfigReceptor(cm, p.taxa_sps, p.deslocamento_hz, limiar=p.limiar, fec=p.fec))
    aceitos = receptor.pacotes_aceitos(d)
    certos = sum(q.sequencia < quadros and q.payload == metricas.payload_conhecido(q.sequencia) for q in aceitos)
    assert len(aceitos) == certos, "pacote errado aceito"
    return round(1 - certos / quadros, 4)


def ruido(s, cm, ebn0_db, semente):
    rng = np.random.default_rng(semente)
    n0 = np.mean(np.abs(s[s != 0]) ** 2) * cm.sps / cm.bits_por_simbolo / 10 ** (ebn0_db / 10)
    return np.sqrt(n0 / 2) * (rng.standard_normal(len(s)) + 1j * rng.standard_normal(len(s)))


def medir_tons():
    medidas, trajetorias = {}, []
    for nome in TONS:
        x = np.load(RAIZ / "dados" / "calibracao" / f"{nome}.npy")
        tom = fase.fase_do_tom(x, FS_TOM)
        l_f = fase.ruido_de_fase_dbc_hz(x, FS_TOM, AFASTAMENTOS_HZ)
        piso = l_f[300e3]
        atrasos = {f"símbolo de {n}": round(FS_TOM / (config.perfil(n).taxa_sps / config.perfil(n).sps))
                   for n, _, _ in CASOS}
        atrasos.update({f"{a} amostras": a for a in ATRASOS_LONGOS})
        variacoes = {}
        for rotulo, a in atrasos.items():
            m = fase.variacao_de_fase_rad(tom, a)
            b = fase.variacao_do_ruido_branco_rad(piso, a, FS_TOM)
            variacoes[rotulo] = {"atraso_amostras": a, "medida_rad": round(m, 4), "ruido_branco_rad": round(b, 4),
                                 "ruido_de_fase_rad": round(fase.descontar(m, b), 4)}
        medidas[nome] = {"freq_hz": round(tom.freq_hz, 1), "saltos_de_emenda": tom.saltos,
                         "l_dbc_hz": {f"{k:g}": round(v, 1) for k, v in l_f.items()}, "variacoes": variacoes}
        print(nome, json.dumps(medidas[nome], ensure_ascii=False), flush=True)
        trajetorias.append(fase.fase_do_tom(x, FS_TOM, banda_hz=BANDA_TRAJETORIA_HZ))
    return medidas, trajetorias


def main():
    medidas, tons = medir_tons()
    resultados = {}
    for nome, ebn0, quadros in CASOS:
        p = config.perfil(nome)
        s, cm = sinal_do_perfil(p, quadros)
        r = {"ebn0_per_1pct_db": ebn0, "quadros": quadros}
        # 2. trajetória real (reamostrada no tempo para a taxa do perfil), 0,5 dB abaixo do ponto de 1%
        w = ruido(s, cm, ebn0 - 0.5, 11)
        r["fase_real"] = {"sem": per(p, cm, s + w, quadros)}
        for k, tom in enumerate(tons):
            ph = fase.trajetoria(tom, int(len(s) * FS_TOM / p.taxa_sps) + 2)
            ph = np.interp(np.arange(len(s)) * FS_TOM / p.taxa_sps, np.arange(len(ph)), ph)
            r["fase_real"][f"tom {k + 1}"] = per(p, cm, s * np.exp(1j * ph) + w, quadros)
        # 3. margem: Wiener 1 dB acima do ponto de 1%
        w = ruido(s, cm, ebn0 + 1.0, 12)
        r["wiener"] = {}
        for largura in LARGURAS_HZ:
            ph = canal.ruido_de_fase(len(s), largura, p.taxa_sps, np.random.default_rng(13))
            r["wiener"][f"{largura:g}"] = per(p, cm, s * np.exp(1j * ph) + w, quadros)
            if r["wiener"][f"{largura:g}"] > 0.5:
                break
        toleradas = [float(k) for k, v in r["wiener"].items() if v <= PER_ALVO]
        r["largura_tolerada_hz"] = max(toleradas) if toleradas else None
        # 4. ADC de 8 bits, 1 dB acima do ponto de 1%
        r["adc"] = {}
        for nivel in NIVEIS_DBFS:
            q = canal.quantizar_8_bits(s + w, nivel)
            r["adc"][f"{nivel:g}"] = {"per": per(p, cm, q, quadros),
                                     "saturadas": round(rtl_rx.fracao_saturada(q.astype(np.complex64)), 5)}
        resultados[nome] = r
        print(nome, json.dumps(r, ensure_ascii=False), flush=True)
    resultado = {
        "ensaio": "imperfeições do hardware: ruído de fase medido e ADC de 8 bits",
        "tons": medidas, "banda_trajetoria_hz": BANDA_TRAJETORIA_HZ, "offset_hz": OFFSET_HZ,
        "perfis": resultados,
        "versao_do_codigo": versao_do_codigo(ignorar=("dados/", "docs/")),
    }
    saida = RAIZ / "dados" / "logs" / f"imperfeicoes_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
