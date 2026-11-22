"""Etapa 5, lado da simulação: a cadeia de medição inteira varrida em Eb/N0.

Para cada configuração candidata e cada Eb/N0: TX com os payloads conhecidos
(sdrlink.metricas.payload_conhecido), 0,5 s de ruído antes, offset de -1,4 kHz,
pico de DC, ruído; RX com guardar_bits; BER (MET-03), PER e goodput pelo log do TX
(MET-01, MET-02), banda a 99% e Eb/N0 medidos na captura (MET-04). Produz as curvas
em que as medições de bancada vão ser sobrepostas, já com o Eb/N0 estimado da
captura, do mesmo jeito que na bancada, e valida a cadeia contra a verdade.

Uso: python ensaios/etapa5/referencia_simulada_ensaio.py   (cerca de 3 min)
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from sdrlink import canal, medicao, metricas, receptor, teoria, transmissor
from sdrlink.modem import ConfigModem
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo
from sdrlink.transmissor import ConfigTransmissor

RAIZ = Path(__file__).resolve().parents[2]
FS = 2.048e6
JANELA_S = 2.0
RUIDO_S = 0.5
OFFSET_HZ = -1400.0
SEMENTE = 20261125
CASOS = {
    "DBPSK RRC, 256 kbit/s": (ConfigModem("dbpsk", "rrc", 8), [6, 7, 8, 9, 10, 11, 12], teoria.ber_dbpsk),
    "GFSK, 128 kbit/s": (ConfigModem("fsk", "gaussiano", 16), [9, 10, 11, 12, 13, 14, 15], teoria.ber_fsk_nao_coerente),
    "OOK RRC, 128 kbit/s": (ConfigModem("ook", "rrc", 16), [9, 10, 11, 12, 13, 14, 15], teoria.ber_ook_nao_coerente),
}


def ponto(cm, ebn0, rng):
    tx = ConfigTransmissor(cm, FS, 250e3)
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(3000)])
    blocos, log = [], []
    for b, regs in transmissor.fluxo(pacotes, tx, JANELA_S):
        blocos.append(b)
        log += regs
    sinal = np.concatenate(blocos).astype(complex)
    sinal = sinal[: len(log) * transmissor.amostras_por_quadro(cm)]
    pot = np.mean(np.abs(sinal) ** 2)
    x = np.concatenate([np.zeros(int(RUIDO_S * FS)), canal.girar(canal.atrasar(sinal, 0.37), OFFSET_HZ, FS)])
    n0 = pot * cm.sps / 10 ** (ebn0 / 10)
    x = x + np.sqrt(n0 / 2) * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x))) + 0.3 * np.sqrt(pot)
    det = receptor.receber(x, ConfigReceptor(cm, FS, 250e3, guardar_bits=True))
    periodo = transmissor.amostras_por_quadro(cm)
    ber = metricas.medir_ber(det, periodo, 2 * cm.sps)
    per = metricas.avaliar([r.pacote for r in log], receptor.pacotes_aceitos(det), JANELA_S)
    med = medicao.medir_captura(x, det[0].inicio, det[-1].inicio + periodo, FS, FS / cm.sps) if det else {}
    return {
        "ebn0_verdadeiro_db": ebn0,
        "ebn0_estimado_db": med.get("ebn0_estimado_db"),
        "banda_99_khz": med.get("banda_99_khz"),
        "transmitidos": per["transmitidos"],
        "per": round(per["per"], 4),
        "goodput_kbps": round(per["goodput_bps"] / 1e3, 1),
        "conteudo_diferente": per["conteudo_diferente"],
        "quadros_na_ber": ber["quadros_comparados"],
        "bits_errados": ber["bits_errados"],
        "bits_comparados": ber["bits_comparados"],
        "ber": ber["ber"],
    }


def figura(res):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5.5))
    cores = dict(zip(res, ["tab:green", "tab:purple", "tab:orange"]))
    e = np.linspace(5, 16, 200)
    for nome, d in res.items():
        _, _, formula = CASOS[nome]
        est = [p["ebn0_estimado_db"] for p in d]
        ber = [p["ber"] if p["bits_errados"] >= 10 else np.nan for p in d]
        a1.semilogy(e, formula(e), "--", color=cores[nome], lw=1)
        a1.semilogy(est, ber, "o", color=cores[nome], label=f"{nome}: medido na cadeia")
        a2.semilogy(est, [max(p["per"], 1e-4) for p in d], "o-", color=cores[nome], label=nome)
    a1.set_title("BER com sequência conhecida × Eb/N0 estimado da captura (tracejado: teoria)")
    a2.set_title("PER pelo log do TX × Eb/N0 estimado da captura")
    a2.axhline(0.01, color="r", ls=":", lw=0.8, label="PER máxima da prova (1%)")
    for a in (a1, a2):
        a.set_xlabel("Eb/N0 estimado da captura (dB)")
        a.grid(which="both", alpha=0.3)
        a.legend(fontsize=8)
    a1.set_ylabel("BER")
    a2.set_ylabel("PER (0 desenhado em 1e-4)")
    a1.set_ylim(1e-6, 0.5)
    fig.suptitle(f"Etapa 5 em simulação: cadeia de medição completa (offset {OFFSET_HZ:.0f} Hz, pico de DC, {JANELA_S:.0f} s por ponto)")
    fig.tight_layout()
    fig.savefig(RAIZ / "docs" / "figuras" / "etapa5_referencia_simulada.png", dpi=100)


def main():
    rng = np.random.default_rng(SEMENTE)
    res = {}
    for nome, (cm, ebn0s, _) in CASOS.items():
        res[nome] = [ponto(cm, float(e), rng) for e in ebn0s]
        for p in res[nome]:
            print(nome, {k: p[k] for k in ("ebn0_verdadeiro_db", "ebn0_estimado_db", "banda_99_khz", "per", "goodput_kbps", "ber", "quadros_na_ber")}, flush=True)
    figura(res)
    registro = {"ensaio": "Etapa 5: referência simulada da cadeia de medição", "versao_do_codigo": versao_do_codigo(),
                "semente": SEMENTE, "janela_s": JANELA_S, "ruido_antes_s": RUIDO_S, "offset_hz": OFFSET_HZ, "resultado": res}
    saida = RAIZ / "dados" / "logs" / f"etapa5_referencia_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(registro, indent=1, ensure_ascii=False, default=float) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
