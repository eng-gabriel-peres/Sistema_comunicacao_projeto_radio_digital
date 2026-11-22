"""Desempenho do receptor multiquadro em simulação: escolha do limiar e perda de implementação.

A. Limiar: métrica de correlação nos quadros reais (mínimo e mediana) e fora deles
   (quantil 99,99% e máximo), a 6, 8 e 10 dB, com offset de -1,6 kHz.
B. Perda de implementação: PER do receptor completo (detecção, offset de -1,6 kHz,
   atraso fracionário, tudo estimado pelo preâmbulo) contra a PER da demodulação
   ideal (instante exato, sem offset), nos mesmos quadros de 128 bytes.

Eb/N0 é medido só sobre o sinal dos quadros (os intervalos de silêncio não entram).

Uso: python ensaios/etapa3/receptor_desempenho_ensaio.py   (cerca de 5 min)
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import fftconvolve, resample_poly

from sdrlink import canal, modem, quadro, receptor
from sdrlink.modem import ConfigModem
from sdrlink.receptor import ConfigReceptor
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
FS = 2.048e6
OFFSET = -1600.0
SEMENTE = 20261123
CONFIGS = {
    "DBPSK RRC, 256 kbit/s": ConfigModem("dbpsk", "rrc", 8),
    "DBPSK RRC, 10,24 kbit/s": ConfigModem("dbpsk", "rrc", 200),
    "GFSK, 128 kbit/s": ConfigModem("fsk", "gaussiano", 16),
    "OOK RRC, 128 kbit/s": ConfigModem("ook", "rrc", 16),
}
EBN0_B = {
    "DBPSK RRC, 256 kbit/s": [6.0, 7.0, 8.0, 9.0, 10.0],
    "DBPSK RRC, 10,24 kbit/s": [6.0, 7.0, 8.0, 9.0, 10.0],
    "GFSK, 128 kbit/s": [10.0, 11.0, 12.0, 13.0, 14.0],
    "OOK RRC, 128 kbit/s": [10.0, 11.0, 12.0, 13.0, 14.0],
}


def captura(cm, pacotes, ebn0, rng):
    """Quadros separados por silêncio; ruído calculado pela potência dos quadros, não da captura."""
    partes, inicios, pos, ondas = [np.zeros(2000, dtype=complex)], [], 2000.37, []
    for p in pacotes:
        onda = modem.modular(quadro.montar_quadro(p), cm)
        ondas.append(onda)
        intervalo = int(rng.integers(300, 3000))
        inicios.append(pos)
        partes += [onda, np.zeros(intervalo, dtype=complex)]
        pos += len(onda) + intervalo
    potencia = np.mean(np.abs(np.concatenate(ondas)) ** 2)
    n0 = potencia * cm.sps / 10 ** (ebn0 / 10)
    sinal = canal.girar(canal.atrasar(np.concatenate(partes), 0.37), OFFSET, FS)
    ruido = rng.standard_normal(len(sinal)) + 1j * rng.standard_normal(len(sinal))
    return sinal + np.sqrt(n0 / 2) * ruido, ondas, n0, inicios


def parte_a(rng):
    resultado = {}
    for nome, cm in CONFIGS.items():
        rx = ConfigReceptor(cm, FS)
        resultado[nome] = {}
        for ebn0 in (6.0, 8.0, 10.0):
            pacotes = [quadro.Pacote(s, rng.integers(0, 256, 128, dtype=np.uint8).tobytes()) for s in range(30)]
            x, _, _, inicios = captura(cm, pacotes, ebn0, rng)
            base = resample_poly(x, 1, rx.decimacao) if rx.decimacao > 1 else x
            met, _ = receptor.metrica_de_correlacao(fftconvolve(base, rx.filtro_deteccao(), mode="same"), rx)
            d, sps_i = rx.decimacao, rx.modem_interno.sps
            verdadeiros = [met[max(0, int(i / d) - 2) : int(i / d) + 3].max() for i in inicios]
            longe = np.ones(len(met), bool)
            for i in inicios:
                longe[max(0, int(i / d) - 2 * sps_i) : int(i / d) + 2 * sps_i] = False
            resultado[nome][f"{ebn0:.0f} dB"] = {
                "verdadeiro_min": round(float(min(verdadeiros)), 3),
                "verdadeiro_mediana": round(float(np.median(verdadeiros)), 3),
                "falso_q9999": round(float(np.quantile(met[longe], 0.9999)), 3),
                "falso_max": round(float(met[longe].max()), 3),
            }
        print("A", nome, resultado[nome], flush=True)
    return resultado


def parte_b(rng, n_quadros=200):
    resultado = {}
    for nome, cm in CONFIGS.items():
        rx = ConfigReceptor(cm, FS)
        pontos = []
        for ebn0 in EBN0_B[nome]:
            pacotes = [quadro.Pacote(s, rng.integers(0, 256, 128, dtype=np.uint8).tobytes()) for s in range(n_quadros)]
            x, ondas, n0, _ = captura(cm, pacotes, ebn0, rng)
            ideal = 0
            for p, onda in zip(pacotes, ondas):
                r = onda + np.sqrt(n0 / 2) * (rng.standard_normal(len(onda)) + 1j * rng.standard_normal(len(onda)))
                bits = modem.demodular(r, cm, len(quadro.montar_quadro(p)))
                ideal += quadro.interpretar(bits[29:]).pacote == p
            deteccoes = receptor.receber(x, rx)
            aceitos = receptor.pacotes_aceitos(deteccoes)
            certos = sum(a in pacotes for a in aceitos)
            errados = len(aceitos) - certos
            pontos.append({
                "ebn0_db": ebn0,
                "per_ideal": round(1 - ideal / n_quadros, 4),
                "per_receptor": round(1 - certos / n_quadros, 4),
                "aceitos_errados": errados,
                "deteccoes": len(deteccoes),
            })
        resultado[nome] = pontos
        print("B", nome, [(p["ebn0_db"], p["per_ideal"], p["per_receptor"]) for p in pontos], flush=True)
    return resultado


def figura_b(res):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    cores = dict(zip(res, ["tab:green", "tab:olive", "tab:purple", "tab:orange"]))
    for nome, pontos in res.items():
        e = [p["ebn0_db"] for p in pontos]
        ax.semilogy(e, [max(p["per_ideal"], 1e-3) for p in pontos], "--", color=cores[nome], label=f"{nome}: ideal")
        ax.semilogy(e, [max(p["per_receptor"], 1e-3) for p in pontos], "o-", color=cores[nome], label=f"{nome}: receptor")
    ax.axhline(0.01, color="r", lw=0.8, ls=":", label="PER máxima da prova (1%)")
    ax.set_xlabel("Eb/N0 (dB)")
    ax.set_ylabel(f"PER (quadros de 128 bytes, 200 por ponto; 0 desenhado em 1e-3)")
    ax.set_title("Receptor completo (offset −1,6 kHz, atraso fracionário, tudo estimado) × demodulação ideal")
    ax.grid(which="both", alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(RAIZ / "docs" / "figuras" / "etapa3_receptor_per.png", dpi=100)


def main():
    rng = np.random.default_rng(SEMENTE)
    res_a = parte_a(rng)
    res_b = parte_b(rng)
    figura_b(res_b)
    registro = {
        "ensaio": "receptor multiquadro: limiar e perda de implementação (simulação)",
        "versao_do_codigo": versao_do_codigo(),
        "semente": SEMENTE,
        "offset_hz": OFFSET,
        "limiar_adotado": receptor.LIMIAR_PADRAO,
        "A_limiar": res_a,
        "B_per": res_b,
    }
    saida = RAIZ / "dados" / "logs" / f"receptor_desempenho_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(registro, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
