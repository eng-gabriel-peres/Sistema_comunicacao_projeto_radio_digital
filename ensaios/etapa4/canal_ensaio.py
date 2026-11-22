"""Etapa 4: BER × Eb/N0 simulada contra a teoria e efeito de fase, offset e temporização.

Entrega pedida no enunciado: "curvas BER × Eb/N0 simuladas comparadas às curvas
teóricas, e análise do efeito de um offset residual típico após calibração
(centenas de hertz)", avaliando AWGN, erro de fase, offset de frequência e erro
de temporização nas três modulações.

A simulação trabalha por quadros de 1109 bits (o quadro v2 com 128 bytes): cada
quadro é modulado, sofre o efeito do canal, recebe ruído e é demodulado com o
sincronismo ideal do sdrlink.modem. Assim o offset de frequência gira a fase ao
longo de um quadro, como no enlace real, e a BPSK coerente parte da fase certa
no início de cada quadro (melhor caso de uma estimativa pelo preâmbulo).

Partes:
    A. BER × Eb/N0 de 0 a 14 dB, simulada e teórica;
    B. efeito isolado de erro de fase, offset (Δf/Rb) e atraso (τ/T), com cada
       modulação no Eb/N0 em que a teoria dá BER = 1e-3;
    C. offset residual medido (500 Hz e 1,6 kHz, achado A18) em taxas de 10 a 500 kbit/s.

Uso: python ensaios/etapa4/canal_ensaio.py   (cerca de 10 min)
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq

from sdrlink import canal, modem, teoria
from sdrlink.modem import ConfigModem
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
FIG = RAIZ / "docs" / "figuras"
SEMENTE = 20261122
SPS = 8
BITS_QUADRO = 1109
ERROS_ALVO = 200
BITS_MAX = 3_000_000
BER_ALVO_B = 1e-3
CONFIGS = {
    "OOK (RRC)": ConfigModem("ook", "rrc", SPS),
    "BPSK coerente (RRC)": ConfigModem("bpsk", "rrc", SPS),
    "DBPSK (RRC)": ConfigModem("dbpsk", "rrc", SPS),
    "2-FSK CPFSK (h = 1)": ConfigModem("fsk", "retangular", SPS),
    "2-FSK GFSK (BT = 0,5)": ConfigModem("fsk", "gaussiano", SPS),
}
CORES = dict(zip(CONFIGS, ["tab:orange", "tab:blue", "tab:green", "tab:red", "tab:purple"]))


def ber(config, ebn0_db, rng, efeito=None, bits_max=BITS_MAX):
    """BER por Monte Carlo em quadros de BITS_QUADRO bits; para em ERROS_ALVO erros ou bits_max bits."""
    erros = total = 0
    for _ in range(bits_max // BITS_QUADRO + 1):
        if erros >= ERROS_ALVO or total >= bits_max:
            break
        bits = rng.integers(0, 2, BITS_QUADRO).astype(np.uint8)
        sinal = modem.modular(bits, config)
        if efeito is not None:
            sinal = efeito(sinal)
        r = modem.demodular(canal.awgn(sinal, ebn0_db, SPS, rng), config, BITS_QUADRO)
        erros += int(np.sum(r != bits))
        total += BITS_QUADRO
    return erros / total, erros, total


def curva_teorica(config, ebn0):
    return teoria.BER_TEORICA[config.modulacao](ebn0)


def parte_a(rng):
    ebn0 = np.arange(0, 15)
    resultado = {}
    for nome, c in CONFIGS.items():
        pontos = []
        for e in ebn0:
            b, n_err, n_bits = ber(c, float(e), rng)
            pontos.append({"ebn0_db": int(e), "ber": b, "erros": n_err, "bits": n_bits, "teoria": float(curva_teorica(c, e))})
            if n_err == 0:
                break  # abaixo do que dá para medir com BITS_MAX bits
        resultado[nome] = pontos
        print("A", nome, [(p["ebn0_db"], f"{p['ber']:.1e}") for p in pontos], flush=True)
    return resultado


def figura_a(res):
    fig, ax = plt.subplots(figsize=(10, 7))
    e = np.linspace(0, 15, 151)
    ax.semilogy(e, teoria.ber_bpsk(e), color=CORES["BPSK coerente (RRC)"], label="teoria BPSK coerente: Q(√(2Eb/N0))")
    ax.semilogy(e, teoria.ber_dbpsk(e), color=CORES["DBPSK (RRC)"], label="teoria DBPSK: ½exp(−Eb/N0)")
    ax.semilogy(e, teoria.ber_fsk_nao_coerente(e), color=CORES["2-FSK CPFSK (h = 1)"], label="teoria 2-FSK não coerente: ½exp(−Eb/2N0)")
    ax.fill_between(e, teoria.ber_ook_nao_coerente(e), teoria.ber_ook_nao_coerente(e, "meio"), color=CORES["OOK (RRC)"], alpha=0.25, label="teoria OOK não coerente (limiar ótimo a limiar no meio)")
    ax.semilogy(e, teoria.ber_fsk_coerente(e), "k:", lw=1, label="referência: 2-FSK coerente Q(√(Eb/N0))")
    for nome, pontos in res.items():
        validos = [p for p in pontos if p["erros"] >= 10]
        ax.semilogy([p["ebn0_db"] for p in validos], [p["ber"] for p in validos], "o", mfc="none", color=CORES[nome], label=f"simulado: {nome}")
    ax.set_ylim(1e-6, 0.6)
    ax.set_xlim(0, 15)
    ax.grid(which="both", alpha=0.3)
    ax.set_xlabel("Eb/N0 (dB)")
    ax.set_ylabel("BER")
    ax.set_title(f"BER × Eb/N0 em AWGN: simulação (≥ 10 erros por ponto, até {BITS_MAX / 1e6:.0f} M bits) e teoria")
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(FIG / "etapa4_ber_awgn.png", dpi=100)


def ebn0_para_ber(config, alvo):
    """Eb/N0 (dB) em que a teoria dá a BER alvo."""
    return brentq(lambda e: float(curva_teorica(config, e)) - alvo, -5, 30)


def parte_b(rng):
    varreduras = {
        "erro de fase (graus)": (np.array([0, 10, 20, 30, 45, 60, 75, 90]), lambda v: lambda s: canal.girar(s, 0.0, 1.0, np.deg2rad(v))),
        "offset Δf/Rb": (np.array([0, 1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 0.1, 0.2]), lambda v: lambda s: canal.girar(s, v, SPS)),
        "atraso τ/T": (np.array([0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5]), lambda v: lambda s: canal.atrasar(s, v * SPS)),
    }
    resultado = {}
    for efeito, (valores, fabrica) in varreduras.items():
        resultado[efeito] = {}
        for nome, c in CONFIGS.items():
            e0 = ebn0_para_ber(c, BER_ALVO_B)
            bers = [ber(c, e0, rng, fabrica(float(v)), bits_max=600_000)[0] for v in valores]
            resultado[efeito][nome] = {"ebn0_db": round(e0, 2), "valores": valores.tolist(), "ber": bers}
            print("B", efeito, nome, [f"{b:.1e}" for b in bers], flush=True)
    return resultado


def figura_b(res):
    fig, eixos = plt.subplots(1, 3, figsize=(16, 5))
    for ax, (efeito, dados) in zip(eixos, res.items()):
        for nome, d in dados.items():
            x = np.array(d["valores"], dtype=float)
            y = np.maximum(np.array(d["ber"]), 1e-6)
            if efeito.startswith("offset"):
                x = np.maximum(x, 3e-5)  # o zero vai para a esquerda do eixo log
            ax.semilogy(x, y, "o-", ms=4, color=CORES[nome], label=f"{nome} ({d['ebn0_db']} dB)")
        if efeito.startswith("erro de fase"):
            fi = np.linspace(0, 90, 91)
            e0 = res[efeito]["BPSK coerente (RRC)"]["ebn0_db"]
            ax.semilogy(fi, teoria.ber_bpsk(e0, np.deg2rad(fi)), "k--", lw=1, label="teoria BPSK: Q(√(2Eb/N0)·cos φ)")
        if efeito.startswith("offset"):
            e0 = res[efeito]["BPSK coerente (RRC)"]["ebn0_db"]
            eps = np.logspace(-5, np.log10(0.2), 200)
            k = np.arange(BITS_QUADRO)
            fq = [np.mean(teoria.q(np.sqrt(2 * 10 ** (e0 / 10)) * np.cos(2 * np.pi * x * k))) for x in eps]
            (linha,) = ax.semilogy(np.maximum(eps, 3e-5), fq, "k--", lw=1, label="teoria BPSK: média no quadro de\nQ(√(2Eb/N0)·cos(2πkΔf/Rb))")
            ax.legend(handles=[linha], fontsize=7, loc="upper left")
            ax.set_xscale("log")
        ax.axhline(BER_ALVO_B, color="gray", lw=0.8, ls=":")
        ax.set_xlabel(efeito)
        ax.set_ylim(5e-5, 0.7)
        ax.grid(which="both", alpha=0.3)
        ax.set_title(f"Efeito do {efeito.split(' (')[0].split(' Δ')[0]}")
    eixos[0].set_ylabel(f"BER (cada modulação no Eb/N0 em que a teoria dá {BER_ALVO_B:.0e})")
    eixos[0].legend(fontsize=7, loc="upper left")
    fig.suptitle(f"Efeito isolado de cada imperfeição; quadros de {BITS_QUADRO} bits, a BPSK coerente começa cada quadro com a fase certa")
    fig.tight_layout()
    fig.savefig(FIG / "etapa4_imperfeicoes.png", dpi=100)


def parte_c(rng):
    taxas = [10e3, 50e3, 100e3, 250e3, 500e3]
    offsets = [0.0, 500.0, 1600.0]
    resultado = {}
    for nome, c in CONFIGS.items():
        e0 = ebn0_para_ber(c, BER_ALVO_B)
        resultado[nome] = {"ebn0_db": round(e0, 2), "tabela": {}}
        for rb in taxas:
            for df in offsets:
                b = ber(c, e0, rng, lambda s, v=df / rb: canal.girar(s, v, SPS), bits_max=300_000)[0]
                per = 1 - (1 - b) ** 1064  # aproximação de erros independentes
                resultado[nome]["tabela"][f"{rb / 1e3:.0f} kbit/s, {df:.0f} Hz"] = {"ber": b, "per_estimada": per}
        print("C", nome, {k: f"{v['ber']:.1e}" for k, v in resultado[nome]["tabela"].items()}, flush=True)
    return resultado


def figura_c(res):
    taxas = ["10", "50", "100", "250", "500"]
    fig, eixos = plt.subplots(1, 3, figsize=(16, 4.8), sharey=True)
    for ax, df in zip(eixos, ["0", "500", "1600"]):
        for nome, d in res.items():
            y = [max(d["tabela"][f"{t} kbit/s, {df} Hz"]["ber"], 1e-6) for t in taxas]
            ax.semilogy([float(t) for t in taxas], y, "o-", ms=4, color=CORES[nome], label=nome)
        ax.axhline(BER_ALVO_B, color="gray", lw=0.8, ls=":")
        ax.set_xscale("log")
        ax.set_xlabel("taxa de bits (kbit/s)")
        ax.set_title(f"offset residual de {df} Hz")
        ax.set_ylim(5e-5, 0.7)
        ax.grid(which="both", alpha=0.3)
    eixos[0].set_ylabel("BER (Eb/N0 da BER teórica 1e-3)")
    eixos[0].legend(fontsize=7)
    fig.suptitle("Offset residual medido em 04/11 (de −0,4 a −1,6 kHz, achado A18) contra a taxa de bits; sem nenhuma correção de frequência")
    fig.tight_layout()
    fig.savefig(FIG / "etapa4_offset_residual.png", dpi=100)


def main():
    rng = np.random.default_rng(SEMENTE)
    res_a = parte_a(rng)
    figura_a(res_a)
    res_b = parte_b(rng)
    figura_b(res_b)
    res_c = parte_c(rng)
    figura_c(res_c)
    registro = {
        "ensaio": "Etapa 4: BER em AWGN e efeito de fase, offset e temporização (simulação)",
        "versao_do_codigo": versao_do_codigo(),
        "semente": SEMENTE,
        "parametros": {"sps": SPS, "bits_por_quadro": BITS_QUADRO, "erros_alvo": ERROS_ALVO, "bits_max": BITS_MAX, "ber_alvo_parte_b": BER_ALVO_B},
        "A_ber_awgn": res_a,
        "B_imperfeicoes": res_b,
        "C_offset_residual": res_c,
    }
    saida = RAIZ / "dados" / "logs" / f"etapa4_canal_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(registro, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
