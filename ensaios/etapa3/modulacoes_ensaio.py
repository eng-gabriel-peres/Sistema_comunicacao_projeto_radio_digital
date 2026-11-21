"""Evidências do sub-bloco 3b: formas de onda, espectros com banda de 99%, constelação e pacotes simulados.

Entrega da Etapa 3 pedida no enunciado: "gráficos de formas de onda, espectros
(com banda de 99% calculada) e constelação BPSK", com pacotes numerados
transmitidos nas novas modulações (aqui em simulação), payload recuperado e
integridade validada.

Gera em docs/figuras/: etapa3_formas_de_onda.png, etapa3_espectros.png,
etapa3_constelacao_bpsk.png; e em dados/logs/ o registro JSON com as bandas e a
PER simulada.

Uso: python ensaios/etapa3/modulacoes_ensaio.py
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from sdrlink import canal, espectro, modem, quadro
from sdrlink.modem import ConfigModem
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
FIG = RAIZ / "docs" / "figuras"
SEMENTE = 20261121
LIMITE_BANDA_HZ = 1e6
SPS_BANDA = 256  # sobreamostragem alta: o pulso retangular tem lóbulos até ±10 Rb e além
COMBINACOES = [
    ("ook", "retangular"),
    ("ook", "rrc"),
    ("bpsk", "retangular"),
    ("bpsk", "rrc"),
    ("dbpsk", "retangular"),
    ("dbpsk", "rrc"),
    ("fsk", "retangular"),
    ("fsk", "gaussiano"),
]
ROTULO = {
    "ook": "OOK",
    "bpsk": "BPSK",
    "dbpsk": "DBPSK",
    "fsk": "2-FSK (h = 1)",
    "retangular": "retangular",
    "rrc": "RRC β = 0,35",
    "gaussiano": "gaussiano BT = 0,5",
}


def nome(m, p):
    return f"{ROTULO[m]}, {ROTULO[p]}"


def figura_formas_de_onda(rng):
    bits = quadro.montar_quadro(quadro.Pacote(1, b"\xa5"))[:24]  # preâmbulo e começo do sync
    sps = 32
    fig, eixos = plt.subplots(4, 2, figsize=(12, 10), sharex=True)
    for ax, (m, p) in zip(eixos.T.ravel(), COMBINACOES):
        c = ConfigModem(m, p, sps)
        s = modem.modular(bits, c)
        s = s / np.max(np.abs(s))  # escala para ±1 só no gráfico
        # atraso do pulso: o centro de cada símbolo cai no meio da célula do bit
        atraso = (len(c.formato()) - 1) / 2 - (sps - 1) / 2
        atraso += sps if m == "dbpsk" else 0  # a DBPSK começa com um símbolo de referência
        t = (np.arange(len(s)) - atraso) / sps
        ax.plot(t, s.real, label="I")
        if m == "fsk":
            ax.plot(t, s.imag, label="Q", alpha=0.7)
            ax.legend(loc="lower right", fontsize=7)
        for k, b in enumerate(bits):
            ax.text(k + 0.5, 1.3, str(b), ha="center", fontsize=7, color="gray")
        ax.set_xlim(0, len(bits))
        ax.set_ylim(-1.5, 1.6)
        ax.set_title(nome(m, p), fontsize=10)
        ax.grid(alpha=0.3)
    for ax in eixos[-1]:
        ax.set_xlabel("tempo (bits)")
    fig.suptitle("Formas de onda em banda base: os mesmos 24 bits (preâmbulo e início do Barker-13)")
    fig.tight_layout()
    fig.savefig(FIG / "etapa3_formas_de_onda.png", dpi=100)


def bandas(rng):
    tabela = {}
    for m, p in COMBINACOES:
        s = modem.modular(rng.integers(0, 2, 20000).astype(np.uint8), ConfigModem(m, p, SPS_BANDA))
        baixo, alto = espectro.banda_ocupada(s, float(SPS_BANDA), nperseg=32768)
        b99 = alto - baixo  # em múltiplos de Rb (taxa normalizada)
        tabela[nome(m, p)] = {
            "b99_sobre_rb": round(b99, 3),
            "rb_max_para_1MHz_kbps": round(LIMITE_BANDA_HZ / b99 / 1e3, 1),
            "b99_a_10kbps_kHz": round(b99 * 10, 1),
            "b99_a_100kbps_kHz": round(b99 * 100, 1),
        }
    return tabela


def figura_espectros(rng, tabela):
    sps = 64
    fig, eixos = plt.subplots(4, 2, figsize=(12, 10), sharex=True)
    for ax, (m, p) in zip(eixos.T.ravel(), COMBINACOES):
        s = modem.modular(rng.integers(0, 2, 20000).astype(np.uint8), ConfigModem(m, p, sps))
        f, psd = espectro.densidade(s, float(sps), nperseg=8192)
        ax.plot(f, 10 * np.log10(psd / psd.max()), lw=0.8)
        b99 = tabela[nome(m, p)]["b99_sobre_rb"]
        ax.axvspan(-b99 / 2, b99 / 2, color="g", alpha=0.15, label=f"99%: {b99:.2f} Rb")
        ax.set_xlim(-12, 12)
        ax.set_ylim(-70, 3)
        ax.set_title(nome(m, p), fontsize=10)
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(alpha=0.3)
    for ax in eixos[-1]:
        ax.set_xlabel("frequência / Rb")
    for ax in eixos[:, 0]:
        ax.set_ylabel("DEP (dB)")
    fig.suptitle("Densidade espectral de potência e banda a 99% (verde); limite da prova: 1 MHz")
    fig.tight_layout()
    fig.savefig(FIG / "etapa3_espectros.png", dpi=100)


def figura_constelacao(rng):
    """BPSK no filtro casado: sem ruído, com ruído e com o offset residual medido (A18)."""
    sps, rb, offset_hz = 8, 128e3, 1000.0
    bits = quadro.montar_quadro(quadro.Pacote(7, rng.integers(0, 256, 128, dtype=np.uint8).tobytes()))
    c = ConfigModem("bpsk", "rrc", sps)
    s = modem.modular(bits, c)
    ruidoso = canal.awgn(s, 10.0, sps, rng)
    giro = np.exp(2j * np.pi * offset_hz * np.arange(len(s)) / (rb * sps))
    casos = [
        ("sem ruído", modem._amostras_casadas(s, c, len(bits))),
        ("Eb/N0 = 10 dB", modem._amostras_casadas(ruidoso, c, len(bits))),
        ("Eb/N0 = 10 dB e offset de 1 kHz\n(Rb = 128 kbit/s, um quadro de 1109 bits)", modem._amostras_casadas(ruidoso * giro, c, len(bits))),
    ]
    cd = ConfigModem("dbpsk", "rrc", sps)
    sd = canal.awgn(modem.modular(bits, cd), 10.0, sps, rng) * np.exp(2j * np.pi * offset_hz * np.arange(len(modem.modular(bits, cd))) / (rb * sps))
    zd = modem._amostras_casadas(sd, cd, len(bits) + 1)
    casos.append(("DBPSK, mesmo offset: produto\nz[k]·conj(z[k−1]) antes da decisão", zd[1:] * np.conj(zd[:-1])))
    fig, eixos = plt.subplots(1, 4, figsize=(15, 4.2))
    for ax, (titulo, z) in zip(eixos, casos):
        ax.scatter(z.real, z.imag, s=3, alpha=0.5, c=np.arange(len(z)), cmap="viridis")
        ax.axhline(0, color="k", lw=0.5)
        ax.axvline(0, color="k", lw=0.5)
        ax.set_aspect("equal")
        lim = 1.8
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_title(titulo, fontsize=9)
        ax.set_xlabel("I")
    eixos[0].set_ylabel("Q")
    fig.suptitle("Constelação BPSK (RRC β = 0,35) no instante ótimo do filtro casado; cor = posição no quadro")
    fig.tight_layout()
    fig.savefig(FIG / "etapa3_constelacao_bpsk.png", dpi=100)


def pacotes_simulados(rng, n_pacotes=200, ebn0s=(8.0, 12.0)):
    """Quadros v2 com 128 bytes aleatórios por cada modulação: PER com sincronismo ideal."""
    res = {}
    for m, p in COMBINACOES:
        c = ConfigModem(m, p, 8)
        res[nome(m, p)] = {}
        for ebn0 in ebn0s:
            ok = 0
            for seq in range(n_pacotes):
                pacote = quadro.Pacote(seq, rng.integers(0, 256, 128, dtype=np.uint8).tobytes())
                bits = quadro.montar_quadro(pacote)
                r = modem.demodular(canal.awgn(modem.modular(bits, c), ebn0, 8, rng), c, len(bits))
                ok += quadro.interpretar(r[29:]).pacote == pacote
            res[nome(m, p)][f"Eb/N0 {ebn0:.0f} dB"] = f"{ok}/{n_pacotes} CRC OK, PER {100 * (n_pacotes - ok) / n_pacotes:.1f}%"
        print(nome(m, p), res[nome(m, p)], flush=True)
    return res


def main():
    rng = np.random.default_rng(SEMENTE)
    figura_formas_de_onda(rng)
    tabela = bandas(rng)
    for k, v in tabela.items():
        print(k, v, flush=True)
    figura_espectros(rng, tabela)
    figura_constelacao(rng)
    per = pacotes_simulados(rng)
    registro = {
        "ensaio": "modulações do sub-bloco 3b em simulação",
        "versao_do_codigo": versao_do_codigo(),
        "semente": SEMENTE,
        "banda_99": {"sps_usado": SPS_BANDA, "tabela": tabela},
        "pacotes": {"payload_bytes": 128, "pacotes_por_ponto": 200, "sincronismo": "ideal", "resultado": per},
    }
    saida = RAIZ / "dados" / "logs" / f"modulacoes_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
