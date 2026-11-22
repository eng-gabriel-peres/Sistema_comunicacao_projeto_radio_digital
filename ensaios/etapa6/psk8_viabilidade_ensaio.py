"""Viabilidade de uma 8-PSK coerente na prova A (1,5 vez a taxa da DQPSK na mesma banda).

A prova A é limitada pela banda (1 MHz) e pela potência, que é padronizada. A 8-PSK leva
3 bits por símbolo contra 2 da DQPSK, mas precisa de detecção coerente (a 8-DPSK custaria
cerca de 3 dB a mais). O ensaio mede, com o instante de amostragem ideal (como o estudo
do FEC no bloco 09), quanto Eb/N0 a 8-PSK coerente precisa para PER de 1%, com a fase e o
offset estimados quadro a quadro pela potência 8 dos símbolos do corpo e a ambiguidade de
45° resolvida pela fase do prefixo conhecido. A DQPSK passa pelo mesmo arranjo, com o
demodulador de produção, como referência.

Canais: (a) só ruído branco; (b) realista: offset residual de até ±500 Hz (o que o
estimador do preâmbulo deixa), a trajetória de fase real dos tons de 04/11/2026 e
ruído branco.

Uso: python ensaios/etapa6/psk8_viabilidade_ensaio.py   (cerca de 10 min)
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy import signal

from sdrlink import fase, metricas, modem, quadro, teoria, transmissor
from sdrlink.modem import ConfigModem
from sdrlink.quadro import Pacote
from sdrlink.registro import carimbo_de_tempo, versao_do_codigo

RAIZ = Path(__file__).resolve().parents[2]
FS = 2.048e6
SPS = 3
BETA = 0.25
PREFIXO = quadro.BITS_PREFIXO
QUADROS = 1000
OFFSET_MAX_HZ = 500.0
GRAY8 = np.array([0, 1, 3, 2, 6, 7, 5, 4])  # índice de fase (k·45°) do símbolo de 3 bits b2b1b0
BITS_VALIDADOS = quadro.bits_apos_sync(transmissor.TAMANHO_PAYLOAD) - len(quadro.GUARDA)
EBN0_DQPSK = np.arange(10.0, 14.5, 0.5)
EBN0_8PSK = np.arange(11.0, 17.5, 0.5)
TOM = "calibracao_20261104_100631_depois"
PER_ALVO = 0.01
SEMENTE = 20261123


def quadros_de_bits():
    pacotes = transmissor.numerar([metricas.payload_conhecido(k) for k in range(QUADROS)])
    return np.stack([quadro.montar_quadro(p) for p in pacotes])


def simbolos_8psk(bits):
    """Prefixo como na DBPSK (com o símbolo de referência), corpo em 8-PSK absoluta com Gray."""
    prefixo = np.cumprod(np.concatenate([np.ones((len(bits), 1)), 1 - 2.0 * bits[:, :PREFIXO]], axis=1), axis=1)
    corpo = bits[:, PREFIXO:]
    corpo = np.concatenate([corpo, np.zeros((len(bits), (-corpo.shape[1]) % 3), dtype=corpo.dtype)], axis=1)
    trios = corpo.reshape(len(bits), -1, 3).astype(np.intp)
    indice = GRAY8[4 * trios[..., 0] + 2 * trios[..., 1] + trios[..., 2]]
    # o prefixo termina num símbolo ±1; o corpo é absoluto (a fase do prefixo é a referência)
    return np.concatenate([prefixo, np.exp(1j * np.pi / 4 * indice)], axis=1)


def formar(simbolos, forma):
    trem = np.zeros((simbolos.shape[0], simbolos.shape[1] * SPS), dtype=np.complex128)
    trem[:, ::SPS] = simbolos
    return signal.fftconvolve(trem, forma[None, :], axes=1)


def canal(x, ebn0_db, bits_por_simbolo, rng, realista, trajetoria):
    potencia = np.mean(np.abs(x) ** 2)
    n0 = potencia * SPS / bits_por_simbolo / 10 ** (ebn0_db / 10)
    y = x.copy()
    if realista:
        n = np.arange(x.shape[1])
        offset = rng.uniform(-OFFSET_MAX_HZ, OFFSET_MAX_HZ, (len(x), 1))
        inicio = rng.integers(0, len(trajetoria) - x.shape[1], len(x))
        ph = trajetoria[inicio[:, None] + n[None, :]] + rng.uniform(0, 2 * np.pi, (len(x), 1))
        y = y * np.exp(1j * (2 * np.pi * offset * n / FS + ph))
    return y + np.sqrt(n0 / 2) * (rng.standard_normal(y.shape) + 1j * rng.standard_normal(y.shape))


def casar(y, forma, n_simbolos):
    casado = signal.fftconvolve(y, forma[::-1][None, :], axes=1)
    return casado[:, np.arange(n_simbolos) * SPS + len(forma) - 1]


N_FFT = 8192  # busca da frequência da potência 8 (resolução de 1/8192 ciclo por símbolo)


def _frequencia_ml(v):
    """Pico de |Σ v_k e^(−jωk)| (máxima verossimilhança), refinado por parábola: ω em rad/símbolo."""
    espectro = np.abs(np.fft.fft(v, N_FFT, axis=1))
    pico = np.argmax(espectro, axis=1)
    linhas = np.arange(len(v))
    a, b, c = (espectro[linhas, (pico + d) % N_FFT] for d in (-1, 0, 1))
    delta = 0.5 * (a - c) / (a - 2 * b + c)
    ciclos = (pico + delta) / N_FFT
    return 2 * np.pi * (ciclos - np.round(ciclos))


def _decidir(corrigido):
    return np.mod(np.round(np.angle(corrigido) / (np.pi / 4)), 8).astype(np.intp)


def detectar_8psk(z, referencia):
    """Fase e offset pela potência 8 do corpo (máx. verossimilhança), ambiguidade de 45° pela
    fase do prefixo, e uma passada guiada pelas decisões (reta de fase em z·conj(decisão))."""
    zp, zc = z[:, : PREFIXO + 1], z[:, PREFIXO + 1 :]
    v = np.abs(zc) * np.exp(8j * np.angle(zc))
    omega = _frequencia_ml(v) / 8  # rad por símbolo
    k = np.arange(zc.shape[1])
    theta8 = np.angle(np.sum(v * np.exp(-8j * omega[:, None] * k[None, :]), axis=1)) / 8
    centro = PREFIXO / 2
    theta_p = np.angle(np.sum(zp * np.conj(referencia)[None, :], axis=1))
    previsto = theta_p + omega * (PREFIXO + 1 - centro)
    salto = np.round((previsto - theta8) / (np.pi / 4))
    theta = theta8 + salto * np.pi / 4
    indice = _decidir(zc * np.exp(-1j * (theta[:, None] + omega[:, None] * k[None, :])))
    # passada guiada pelas decisões: a fase residual de z·conj(decisão) ajustada por uma reta
    residuo = np.unwrap(np.angle(zc * np.exp(-1j * np.pi / 4 * indice)), axis=1)
    inclinacao, intercepto = np.polyfit(k, residuo.T, 1)
    indice = _decidir(zc * np.exp(-1j * (intercepto[:, None] + inclinacao[:, None] * k[None, :])))
    trios = np.argsort(GRAY8)[indice]  # valor de 3 bits de cada índice de fase
    return np.stack([(trios >> 2) & 1, (trios >> 1) & 1, trios & 1], axis=-1).reshape(len(z), -1)


def per_8psk(bits, ebn0_db, rng, realista, trajetoria, forma):
    s = simbolos_8psk(bits)
    referencia = s[0, : PREFIXO + 1]
    z = casar(canal(formar(s, forma), ebn0_db, 3, rng, realista, trajetoria), forma, s.shape[1])
    recebidos = detectar_8psk(z, referencia)[:, :BITS_VALIDADOS]
    erros = recebidos != bits[:, PREFIXO : PREFIXO + BITS_VALIDADOS]
    return float(np.mean(erros.any(axis=1))), float(np.mean(erros))


def per_dqpsk(bits, ebn0_db, rng, realista, trajetoria, cm):
    x = np.stack([modem.modular(b, cm, prefixo=PREFIXO) for b in bits])
    y = canal(x, ebn0_db, 2, rng, realista, trajetoria)
    erros = np.stack([
        modem.demodular(linha, cm, bits.shape[1], prefixo=PREFIXO)[PREFIXO : PREFIXO + BITS_VALIDADOS]
        != b[PREFIXO : PREFIXO + BITS_VALIDADOS]
        for linha, b in zip(y, bits, strict=True)
    ])
    return float(np.mean(erros.any(axis=1))), float(np.mean(erros))


def cruzamento(ebn0, per):
    for k in range(1, len(per)):
        if per[k] <= PER_ALVO < per[k - 1]:
            a, b = np.log10(max(per[k - 1], 1e-4)), np.log10(max(per[k], 1e-4))
            return round(float(ebn0[k - 1] + (np.log10(PER_ALVO) - a) / (b - a) * (ebn0[k] - ebn0[k - 1])), 2)
    return None


def ber_8psk_teorica(ebn0_db):
    """8-PSK coerente com Gray (aproximação dos vizinhos mais próximos)."""
    g = 10 ** (np.asarray(ebn0_db) / 10)
    return 2 / 3 * teoria.q(np.sqrt(6 * g) * np.sin(np.pi / 8))


def main():
    cm = ConfigModem("dqpsk", "rrc", SPS, beta=BETA)
    forma = cm.formato()
    bits = quadros_de_bits()
    trajetoria = fase.trajetoria(fase.fase_do_tom(np.load(RAIZ / "dados" / "calibracao" / f"{TOM}.npy"), FS,
                                                  banda_hz=2e3), 2**23)
    rng = np.random.default_rng(SEMENTE)
    resultado = {"quadros_por_ponto": QUADROS, "offset_max_hz": OFFSET_MAX_HZ, "bits_validados": BITS_VALIDADOS}
    for nome, ebn0s, funcao in (("dqpsk", EBN0_DQPSK, per_dqpsk), ("8psk", EBN0_8PSK, per_8psk)):
        extra = cm if nome == "dqpsk" else forma
        for realista in (False, True):
            curva = [funcao(bits, e, rng, realista, trajetoria, extra) for e in ebn0s]
            rotulo = f"{nome} {'realista' if realista else 'só ruído'}"
            resultado[rotulo] = {
                "ebn0_db": [float(e) for e in ebn0s], "per": [round(c[0], 4) for c in curva],
                "ber": [float(f"{c[1]:.3g}") for c in curva],
                "ebn0_per_1pct_db": cruzamento(ebn0s, [c[0] for c in curva]),
            }
            print(rotulo, json.dumps(resultado[rotulo]), flush=True)
    teor = {"dqpsk": teoria.ber_dqpsk, "8psk": ber_8psk_teorica}
    resultado["teoria_ebn0_per_1pct_db"] = {
        nome: cruzamento(e, list(1 - (1 - np.minimum(f(e), 0.5)) ** BITS_VALIDADOS))
        for nome, f, e in (("dqpsk", teor["dqpsk"], np.arange(8, 16, 0.05)),
                           ("8psk", teor["8psk"], np.arange(9, 19, 0.05)))
    }
    periodo_dqpsk = transmissor.amostras_por_quadro(cm, emendar_caudas=True)
    simbolos_8 = PREFIXO + 1 + -(-(quadro.bits_apos_sync(transmissor.TAMANHO_PAYLOAD)) // 3)
    periodo_8psk = (simbolos_8 + 1) * SPS  # com as caudas emendadas, como o prova-a
    resultado["goodput_sem_perdas_kbit_s"] = {
        "dqpsk": round(8 * transmissor.TAMANHO_PAYLOAD * FS / periodo_dqpsk / 1e3, 1),
        "8psk": round(8 * transmissor.TAMANHO_PAYLOAD * FS / periodo_8psk / 1e3, 1),
    }
    taxas = {"dqpsk": 2 * FS / SPS, "8psk": 3 * FS / SPS}
    resultado["cn0_necessario_realista_dbhz"] = {
        nome: None if resultado[f"{nome} realista"]["ebn0_per_1pct_db"] is None
        else round(resultado[f"{nome} realista"]["ebn0_per_1pct_db"] + 10 * np.log10(taxas[nome]), 2)
        for nome in taxas
    }
    resultado["versao_do_codigo"] = versao_do_codigo(ignorar=("dados/", "docs/"))
    print(json.dumps({k: resultado[k] for k in ("teoria_ebn0_per_1pct_db", "goodput_sem_perdas_kbit_s",
                                                  "cn0_necessario_realista_dbhz")}))
    saida = RAIZ / "dados" / "logs" / f"psk8_viabilidade_{carimbo_de_tempo()}.json"
    saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"registro: {saida}")


if __name__ == "__main__":
    sys.exit(main())
