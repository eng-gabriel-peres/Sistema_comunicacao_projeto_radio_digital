"""
TX OOK — versão SIMULADA (sem ADALM-Pluto).

Mesmo código de pluto_tx_ook_v2.py, mas em vez de enviar as amostras IQ
para o Pluto (sdr.tx), elas são salvas em 'tx_iq.npy' e cada etapa da
construção do sinal é mostrada em gráficos.

Quadro (frame) transmitido:

    [ preâmbulo 16 bits ] [ sync Barker-13 ] [ comprimento 8 bits ]
    [ payload 8 bits/char ] [ CRC-8 ] [ guarda 16 bits ]

Etapas mostradas:
    Passo 1 — Montagem do quadro (bits e campos)
    Passo 2 — Envoltória OOK com rampas cosseno levantado
    Passo 3 — Sinal IQ: envoltória x portadora complexa de 200 kHz
    Passo 4 — Espectro do sinal transmitido (banda-base do Pluto)

Requer: pip install numpy matplotlib
Próximo passo: python canal_sim.py
"""

import os
import numpy as np
import matplotlib.pyplot as plt

# ---- Configuração (igual a pluto_tx_ook_v2.py) ----
CENTER_FREQ = int(915e6)
SAMPLE_RATE = int(2e6)
TONE_FREQ = 200e3
TX_GAIN = -20               # não usado na simulação (só informativo)

BIT_RATE = 10e3
RAMP_FRACTION = 0.1

# ---- Mensagem ----
MESSAGE = "HELLO WORLD MANDRIAUM"    # <-- troque pela mensagem desejada

# ---- Estrutura do quadro ----
PREAMBLE_BITS = "10" * 8                 # 16 bits alternados
SYNC_BITS = "1111100110101"              # Barker-13
GUARD_BITS = "0" * 16                    # silêncio entre repetições

SAMPLES_PER_BIT = int(round(SAMPLE_RATE / BIT_RATE))
AMPLITUDE = 2**14

# ---- Opções da simulação ----
ARQUIVO_SAIDA = "tx_iq.npy"
PASTA_FIGURAS = "figuras"
PAUSAR_ENTRE_PASSOS = True   # True: abre um gráfico por vez (feche para avançar)
                             # False: abre todos juntos no final


def crc8(data_bytes, poly=0x07, init=0x00):
    """CRC-8 bit a bit (polinômio 0x07)."""
    crc = init
    for byte in data_bytes:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def build_frame_bits(message):
    payload_bytes = message.encode("ascii", errors="replace")
    if len(payload_bytes) > 255:
        raise ValueError("Mensagem longa demais para o campo de 8 bits (máx 255 bytes).")

    length_bits = format(len(payload_bytes), "08b")
    payload_bits = "".join(format(b, "08b") for b in payload_bytes)
    crc_bits = format(crc8(payload_bytes), "08b")

    frame = PREAMBLE_BITS + SYNC_BITS + length_bits + payload_bits + crc_bits + GUARD_BITS
    return frame, payload_bytes


def build_ook_envelope(bits, samples_per_bit, ramp_fraction):
    """Envoltória (0..1) para a sequência de bits, com rampas de cosseno
    levantado nas transições (reduz o espalhamento espectral)."""
    ramp_len = max(1, int(samples_per_bit * ramp_fraction))
    ramp_up = 0.5 * (1 - np.cos(np.pi * np.arange(ramp_len) / ramp_len))
    ramp_down = ramp_up[::-1]

    envelope = np.zeros(len(bits) * samples_per_bit)
    prev_bit = 0
    for idx, bit in enumerate(bits):
        start = idx * samples_per_bit
        end = start + samples_per_bit
        level = 1.0 if bit == "1" else 0.0
        envelope[start:end] = level

        cur_bit = int(bit)
        if cur_bit != prev_bit:
            if cur_bit == 1:
                envelope[start:start + ramp_len] = ramp_up
            else:
                envelope[start:start + ramp_len] = ramp_down
        prev_bit = cur_bit

    return envelope


def field_boundaries(payload_len):
    """Lista (nome, bit_inicial, bit_final) de cada campo do quadro."""
    sizes = [("preâmbulo", len(PREAMBLE_BITS)), ("sync", len(SYNC_BITS)),
             ("compr.", 8), ("payload", 8 * payload_len), ("CRC", 8),
             ("guarda", len(GUARD_BITS))]
    out, pos = [], 0
    for name, n in sizes:
        out.append((name, pos, pos + n))
        pos += n
    return out


FIELD_COLORS = {"preâmbulo": "#9ecae1", "sync": "#fdae6b", "compr.": "#a1d99b",
                "payload": "#dadaeb", "CRC": "#fc9272", "guarda": "#d9d9d9"}


def shade_fields(ax, fields, scale=1.0):
    """Pinta o fundo do gráfico com a cor de cada campo do quadro."""
    for name, b0, b1 in fields:
        ax.axvspan(b0 * scale, b1 * scale, color=FIELD_COLORS[name], alpha=0.5, lw=0)
        ax.text((b0 + b1) / 2 * scale, 1.12, name, ha="center", va="bottom", fontsize=8)


def mostrar(fig, nome):
    os.makedirs(PASTA_FIGURAS, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_FIGURAS, nome), dpi=110)
    if PAUSAR_ENTRE_PASSOS:
        plt.show()


if __name__ == "__main__":
    # ---- Passo 1: montar o quadro ----
    FRAME_BITS, payload_bytes = build_frame_bits(MESSAGE)
    fields = field_boundaries(len(payload_bytes))

    print(f"Mensagem: {MESSAGE!r} ({len(payload_bytes)} bytes)")
    print(f"Campos: preâmbulo={len(PREAMBLE_BITS)} bits, sync={len(SYNC_BITS)} bits, "
          f"compr.=8 bits, payload={len(payload_bytes)*8} bits, crc=8 bits, "
          f"guarda={len(GUARD_BITS)} bits")
    print(f"Quadro total: {len(FRAME_BITS)} bits "
          f"(~{len(FRAME_BITS)/BIT_RATE*1e3:.2f} ms por repetição)")
    print(f"CRC-8: {crc8(payload_bytes):#04x}")
    print("\nCaracteres -> bytes -> bits:")
    for ch, b in zip(MESSAGE, payload_bytes):
        print(f"  {ch!r:5} = {b:#04x} = {b:08b}")

    bits_arr = np.array([int(b) for b in FRAME_BITS])
    fig, ax = plt.subplots(figsize=(16, 3.8))
    shade_fields(ax, fields)
    ax.step(np.arange(len(bits_arr) + 1), np.r_[bits_arr, bits_arr[-1]],
            where="post", color="k", lw=1.2)
    ax.set_ylim(-0.15, 1.35)
    ax.set_yticks([0, 1])
    ax.set_xlim(0, len(bits_arr))
    ax.set_xlabel("Índice do bit")
    ax.set_title(f"Passo 1 — Quadro de {len(FRAME_BITS)} bits para a mensagem {MESSAGE!r}",
                 pad=18)
    # Mostra o caractere sobre cada byte do payload
    p0 = fields[3][1]
    for i, ch in enumerate(MESSAGE):
        ax.text(p0 + 8 * i + 4, -0.12, ch, ha="center", va="bottom", fontsize=8,
                color="navy", family="monospace")
    mostrar(fig, "tx_passo1_quadro.png")

    # ---- Passo 2: envoltória OOK ----
    envelope = build_ook_envelope(FRAME_BITS, SAMPLES_PER_BIT, RAMP_FRACTION)
    N = len(envelope)
    ts = 1 / SAMPLE_RATE
    t = np.arange(N) * ts
    t_ms = t * 1e3

    fig, axes = plt.subplots(2, 1, figsize=(16, 7))
    shade_fields(axes[0], fields, scale=1e3 / BIT_RATE)
    axes[0].plot(t_ms, envelope, color="k", lw=0.8)
    axes[0].set_ylim(-0.1, 1.3)
    axes[0].set_xlabel("Tempo (ms)")
    axes[0].set_ylabel("Amplitude")
    axes[0].set_title("Passo 2 — Envoltória OOK do quadro inteiro "
                      f"({SAMPLES_PER_BIT} amostras/bit a {SAMPLE_RATE/1e6:.1f} MS/s)", pad=18)

    # Zoom numa transição 0->1 do preâmbulo para ver a rampa
    z0, z1 = 0, 4 * SAMPLES_PER_BIT
    axes[1].plot(np.arange(z0, z1), envelope[z0:z1], ".-", ms=3)
    ramp_len = max(1, int(SAMPLES_PER_BIT * RAMP_FRACTION))
    for k in range(5):
        axes[1].axvline(k * SAMPLES_PER_BIT, color="gray", ls=":")
    axes[1].axvspan(0, ramp_len, color="orange", alpha=0.3,
                    label=f"rampa = {ramp_len} amostras ({RAMP_FRACTION:.0%} do bit)")
    axes[1].axvspan(SAMPLES_PER_BIT, SAMPLES_PER_BIT + ramp_len, color="orange", alpha=0.3)
    axes[1].set_xlabel("Índice da amostra")
    axes[1].set_ylabel("Amplitude")
    axes[1].set_title("Zoom nos 4 primeiros bits (1 0 1 0): rampas de cosseno levantado nas transições")
    axes[1].legend(loc="upper right")
    axes[1].grid(True)
    mostrar(fig, "tx_passo2_envoltoria.png")

    # ---- Passo 3: modulação na portadora complexa ----
    carrier = np.exp(1j * 2 * np.pi * TONE_FREQ * t)
    iq_samples = AMPLITUDE * envelope * carrier

    fig, axes = plt.subplots(1, 2, figsize=(16, 4.5), gridspec_kw={"width_ratios": [3, 1]})
    z1 = 3 * SAMPLES_PER_BIT
    axes[0].plot(t[:z1] * 1e6, iq_samples.real[:z1], label="I (real)")
    axes[0].plot(t[:z1] * 1e6, iq_samples.imag[:z1], label="Q (imag)", alpha=0.8)
    axes[0].plot(t[:z1] * 1e6, AMPLITUDE * envelope[:z1], "k--", label="envoltória")
    axes[0].set_xlabel("Tempo (µs)")
    axes[0].set_ylabel("Valor da amostra (DAC)")
    axes[0].set_title(f"Passo 3 — IQ = {AMPLITUDE} · envoltória · exp(j2π·{TONE_FREQ/1e3:.0f}k·t)"
                      "  (3 primeiros bits)")
    axes[0].legend(loc="center")
    axes[0].grid(True)
    axes[1].plot(iq_samples.real[:z1], iq_samples.imag[:z1], ".", ms=2)
    axes[1].set_aspect("equal")
    axes[1].set_xlabel("I")
    axes[1].set_ylabel("Q")
    axes[1].set_title(f"Plano IQ: bit 1 = pontos no círculo\n({SAMPLE_RATE/TONE_FREQ:.0f} fases, pois fs/f_tom = {SAMPLE_RATE/TONE_FREQ:.0f}); bit 0 = origem")
    axes[1].grid(True)
    mostrar(fig, "tx_passo3_iq.png")

    # ---- Passo 4: espectro ----
    # Repete o quadro algumas vezes (como o buffer cíclico do Pluto faz)
    rep = np.tile(iq_samples, 8)
    nfft = 8192
    win = np.hanning(nfft)
    segs = rep[: (len(rep) // nfft) * nfft].reshape(-1, nfft)
    psd = np.mean(np.abs(np.fft.fftshift(np.fft.fft(segs * win, axis=1), axes=1)) ** 2, axis=0)
    psd_db = 10 * np.log10(psd / psd.max() + 1e-15)
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / SAMPLE_RATE))

    fig, axes = plt.subplots(1, 2, figsize=(16, 4.5))
    axes[0].plot((CENTER_FREQ + f) / 1e6, psd_db)
    axes[0].set_xlabel("Frequência (MHz)")
    axes[0].set_ylabel("Potência relativa (dB)")
    axes[0].set_title(f"Passo 4 — Espectro transmitido (LO = {CENTER_FREQ/1e6:.0f} MHz, "
                      f"tom em +{TONE_FREQ/1e3:.0f} kHz)")
    axes[0].set_ylim(-100, 5)
    axes[0].grid(True)
    m = np.abs(f - TONE_FREQ) <= 60e3
    axes[1].plot((f[m] - TONE_FREQ) / 1e3, psd_db[m])
    for x in (-BIT_RATE, BIT_RATE):
        axes[1].axvline(x / 1e3, color="r", ls="--", alpha=0.6)
    axes[1].set_xlabel(f"Desvio em relação a {(CENTER_FREQ+TONE_FREQ)/1e6:.3f} MHz (kHz)")
    axes[1].set_ylabel("Potência relativa (dB)")
    axes[1].set_title("Zoom: lóbulo principal OOK ≈ ±taxa de bits (linhas vermelhas)")
    axes[1].set_ylim(-100, 5)
    axes[1].grid(True)
    mostrar(fig, "tx_passo4_espectro.png")

    # ---- Em vez de sdr.tx(iq_samples): salva para o canal simulado ----
    np.save(ARQUIVO_SAIDA, iq_samples.astype(np.complex64))
    print(f"\n[SIMULAÇÃO] No hardware real: sdr.tx(iq_samples) com buffer cíclico, "
          f"em {(CENTER_FREQ+TONE_FREQ)/1e6:.3f} MHz.")
    print(f"[SIMULAÇÃO] Aqui: {N} amostras IQ salvas em '{ARQUIVO_SAIDA}'.")
    print("Próximo passo: python canal_sim.py")

    if not PAUSAR_ENTRE_PASSOS:
        plt.show()
