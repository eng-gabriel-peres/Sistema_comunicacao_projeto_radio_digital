"""
RX OOK — versão SIMULADA (sem RTL-SDR).

Mesmo algoritmo de rtl_rx_ook_v2.py, mas em vez de capturar do RTL-SDR
(sdr.read_samples), lê as amostras de 'rx_iq.npy' (gerado por canal_sim.py).
Cada etapa do processamento é mostrada em um gráfico.

Etapas:
    Passo 1 — Espectro da captura
    Passo 2 — Translação de frequência (-200 kHz) e filtro passa-faixa complexo
    Passo 3 — Detecção de envoltória |x| e suavização (passa-baixas)
    Passo 4 — Sincronismo de quadro por correlação com o Barker-13
    Passo 5 — Limiar a partir do preâmbulo + diagrama de olho
    Passo 6 — Decisão bit a bit, montagem dos bytes e verificação do CRC

Dica: para analisar uma captura REAL com este mesmo script, acrescente
    np.save("captura_real.npy", samples)
logo após capture_chunks(...) em rtl_rx_ook_v2.py e mude ARQUIVO_ENTRADA abaixo.

Requer: pip install numpy matplotlib   (scipy opcional: deixa os filtros bem mais rápidos)
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab

try:
    from scipy.signal import fftconvolve as _conv   # mesmo resultado, muito mais rápido
except ImportError:
    _conv = np.convolve

# ---- Configuração (igual a rtl_rx_ook_v2.py) ----
CENTER_FREQ = 915e6
SAMPLE_RATE = 2.048e6
GAIN = 30                   # não usado na simulação
FREQ_CORRECTION_PPM = 34    # não usado na simulação (o canal_sim já modela o resíduo)

TONE_FREQ_OFFSET = 200e3
BIT_RATE = 10e3

PREAMBLE_BITS = "10" * 8
SYNC_BITS = "1111100110101"          # Barker-13, igual ao TX
MAX_EXPECTED_PAYLOAD_BYTES = 64

BANDPASS_HALF_WIDTH_HZ = 10e3
LOWPASS_CUTOFF_HZ = BIT_RATE * 3

SPECTRUM_NFFT = 4096
SPECTRUM_ZOOM_HALF_SPAN_HZ = 60e3

# ---- Opções da simulação ----
ARQUIVO_ENTRADA = "rx_iq.npy"
ARQUIVO_INFO = "canal_info.json"     # só para comparar com o "gabarito" do canal
PASTA_FIGURAS = "figuras"
PAUSAR_ENTRE_PASSOS = True


def mostrar(fig, nome):
    os.makedirs(PASTA_FIGURAS, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_FIGURAS, nome), dpi=110)
    if PAUSAR_ENTRE_PASSOS:
        plt.show()


def make_lowpass_taps(sample_rate, cutoff_hz, numtaps=None):
    """Coeficientes do FIR passa-baixas (sinc janelado), como em rtl_rx_ook_v2.py."""
    if numtaps is None:
        desired_transition_hz = cutoff_hz / 4
        numtaps = int(np.ceil(3.3 * sample_rate / desired_transition_hz))
        numtaps = max(numtaps, 51)
    if numtaps % 2 == 0:
        numtaps += 1
    n = np.arange(numtaps) - (numtaps - 1) / 2
    fc = cutoff_hz / sample_rate
    h = 2 * fc * np.sinc(2 * fc * n)
    h *= np.hamming(numtaps)
    h /= np.sum(h)
    return h


def simple_lowpass(signal, sample_rate, cutoff_hz, numtaps=None):
    """FIR passa-baixas. Funciona com entrada complexa (taps reais)."""
    h = make_lowpass_taps(sample_rate, cutoff_hz, numtaps)
    return _conv(signal, h, mode="same"), len(h)


def crc8(data_bytes, poly=0x07, init=0x00):
    crc = init
    for byte in data_bytes:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def bits_to_levels(bits):
    """Bits -> ±0.5 (modelo de média zero para o filtro casado)."""
    return np.array([0.5 if b == "1" else -0.5 for b in bits])


def read_bits(envelope, start_sample, num_bits, samples_per_bit, threshold):
    """Média da envoltória em cada período de bit e comparação com o limiar."""
    bits = []
    for k in range(num_bits):
        seg_start = int(round(start_sample + k * samples_per_bit))
        seg_end = int(round(start_sample + (k + 1) * samples_per_bit))
        if seg_end > len(envelope):
            return None, seg_start
        level = np.mean(envelope[seg_start:seg_end])
        bits.append("1" if level > threshold else "0")
    end_sample = int(round(start_sample + num_bits * samples_per_bit))
    return "".join(bits), end_sample


def bit_means(envelope, start_sample, num_bits, samples_per_bit):
    """Valor médio de cada bit (o que read_bits compara com o limiar)."""
    out = []
    for k in range(num_bits):
        a = int(round(start_sample + k * samples_per_bit))
        b = int(round(start_sample + (k + 1) * samples_per_bit))
        out.append(np.mean(envelope[a:b]))
    return np.array(out)


def psd_simple(x, fs, nfft=4096):
    win = np.hanning(nfft)
    segs = x[: (len(x) // nfft) * nfft].reshape(-1, nfft)
    p = np.mean(np.abs(np.fft.fftshift(np.fft.fft(segs * win, axis=1), axes=1)) ** 2, axis=0)
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / fs))
    return f, 10 * np.log10(p / p.max() + 1e-15)


if __name__ == "__main__":
    # ---- Em vez de RtlSdr() + capture_chunks(): lê o arquivo ----
    samples = np.load(ARQUIVO_ENTRADA).astype(np.complex128)
    print(f"[SIMULAÇÃO] Amostras lidas de '{ARQUIVO_ENTRADA}' "
          f"(no hardware: sdr.read_samples a {CENTER_FREQ/1e6:.3f} MHz)")
    actual_duration = len(samples) / SAMPLE_RATE
    print(f"Total de amostras: {len(samples)} (~{actual_duration*1e3:.1f} ms)")

    # ================= Passo 1: espectro da captura =================
    target_freq = CENTER_FREQ + TONE_FREQ_OFFSET
    Pxx, freqs = mlab.psd(samples, NFFT=SPECTRUM_NFFT, Fs=SAMPLE_RATE)
    Pxx_db = 10 * np.log10(Pxx)
    abs_freq_mhz = (CENTER_FREQ + freqs) / 1e6
    zoom_mask = np.abs((CENTER_FREQ + freqs) - target_freq) <= SPECTRUM_ZOOM_HALF_SPAN_HZ

    fig, axes = plt.subplots(1, 2, figsize=(16, 4.5))
    axes[0].plot(abs_freq_mhz, Pxx_db)
    axes[0].axvline(target_freq / 1e6, color="r", ls="--", alpha=0.6, label="tom esperado")
    axes[0].set_xlabel("Frequência (MHz)")
    axes[0].set_ylabel("Potência (dB)")
    axes[0].set_title("RX passo 1 — Espectro capturado (pico DC no centro é do RTL-SDR)")
    axes[0].legend()
    axes[0].grid(True)
    axes[1].plot(abs_freq_mhz[zoom_mask], Pxx_db[zoom_mask])
    axes[1].axvline(target_freq / 1e6, color="r", ls="--", alpha=0.6)
    axes[1].set_xlabel("Frequência (MHz)")
    axes[1].set_title(f"Zoom ±{SPECTRUM_ZOOM_HALF_SPAN_HZ/1e3:.0f} kHz em torno de "
                      f"{target_freq/1e6:.3f} MHz")
    axes[1].grid(True)
    mostrar(fig, "rx_passo1_espectro.png")

    # ================= Passo 2: translação + passa-faixa =================
    t = np.arange(len(samples)) / SAMPLE_RATE
    mix = samples * np.exp(-1j * 2 * np.pi * TONE_FREQ_OFFSET * t)
    mix_filtered, bandpass_numtaps = simple_lowpass(mix, SAMPLE_RATE, BANDPASS_HALF_WIDTH_HZ)
    print(f"Passa-faixa complexo: ±{BANDPASS_HALF_WIDTH_HZ/1e3:.1f} kHz em torno de 0 Hz, "
          f"numtaps={bandpass_numtaps}")

    f, p_raw = psd_simple(samples, SAMPLE_RATE)
    _, p_mix = psd_simple(mix, SAMPLE_RATE)
    _, p_filt = psd_simple(mix_filtered, SAMPLE_RATE)
    h_bp = make_lowpass_taps(SAMPLE_RATE, BANDPASS_HALF_WIDTH_HZ)
    H = np.fft.fftshift(np.fft.fft(h_bp, 1 << 16))
    fH = np.fft.fftshift(np.fft.fftfreq(1 << 16, 1 / SAMPLE_RATE))

    fig, axes = plt.subplots(1, 2, figsize=(16, 4.5))
    axes[0].plot(f / 1e3, p_raw, alpha=0.6, label="capturado (tom em +200 kHz)")
    axes[0].plot(f / 1e3, p_mix, alpha=0.8, label="após × exp(-j2π·200k·t)")
    axes[0].set_xlabel("Frequência (kHz)")
    axes[0].set_ylabel("Potência relativa (dB)")
    axes[0].set_title("RX passo 2 — Translação: o tom vai para 0 Hz e o DC do RTL vai para -200 kHz")
    axes[0].legend(fontsize=8)
    axes[0].grid(True)
    m = np.abs(f) <= 60e3
    axes[1].plot(f[m] / 1e3, p_mix[m], alpha=0.6, label="transladado")
    axes[1].plot(f[m] / 1e3, p_filt[m], label="após passa-faixa")
    mH = np.abs(fH) <= 60e3
    axes[1].plot(fH[mH] / 1e3, 20 * np.log10(np.abs(H[mH]) + 1e-12), color="gray", lw=0.5,
                 label=f"resposta do filtro ({bandpass_numtaps} taps)")
    axes[1].set_ylim(-90, 5)
    axes[1].set_xlabel("Frequência (kHz)")
    axes[1].set_title("Zoom: o filtro ±10 kHz remove o ruído fora da banda do sinal")
    axes[1].legend(fontsize=8)
    axes[1].grid(True)
    mostrar(fig, "rx_passo2_translacao_filtro.png")

    # ================= Passo 3: envoltória + suavização =================
    bandpassed_envelope = np.abs(mix_filtered)
    envelope, lowpass_numtaps = simple_lowpass(bandpassed_envelope, SAMPLE_RATE, LOWPASS_CUTOFF_HZ)
    print(f"Suavização da envoltória: corte={LOWPASS_CUTOFF_HZ/1e3:.1f} kHz, "
          f"numtaps={lowpass_numtaps}")

    t_ms = t * 1e3
    w = (t_ms >= 20) & (t_ms <= 32)
    fig, axes = plt.subplots(3, 1, figsize=(16, 8.5), sharex=True)
    axes[0].plot(t_ms[w], np.abs(mix[w]), lw=0.4, color="gray")
    axes[0].set_title("RX passo 3 — |transladado| SEM filtro: o ruído de banda larga esconde os bits")
    axes[1].plot(t_ms[w], bandpassed_envelope[w], lw=0.6)
    axes[1].set_title("|após passa-faixa| = detector de envoltória: os bits aparecem")
    axes[2].plot(t_ms[w], envelope[w], lw=1, color="C2")
    axes[2].set_title(f"Envoltória suavizada (passa-baixas {LOWPASS_CUTOFF_HZ/1e3:.0f} kHz): "
                      "é ela que vai para o sincronismo e a decisão")
    axes[2].set_xlabel("Tempo (ms)")
    for a in axes:
        a.grid(True)
        a.set_ylabel("Amplitude")
    mostrar(fig, "rx_passo3_envoltoria.png")

    # ================= Passo 4: sincronismo por correlação =================
    samples_per_bit = SAMPLE_RATE / BIT_RATE
    sync_template = np.repeat(bits_to_levels(SYNC_BITS), int(round(samples_per_bit)))

    envelope_zero_mean = envelope - np.mean(envelope)
    correlation = np.correlate(envelope_zero_mean, sync_template, mode="valid") \
        if _conv is np.convolve else \
        _conv(envelope_zero_mean, sync_template[::-1], mode="valid")

    max_trailing_bits = 8 + 8 * MAX_EXPECTED_PAYLOAD_BYTES + 8
    max_trailing_samples = int(max_trailing_bits * samples_per_bit)
    valid_range = len(correlation) - max_trailing_samples
    if valid_range <= 0:
        raise RuntimeError("Captura curta demais para MAX_EXPECTED_PAYLOAD_BYTES.")

    sync_start = int(np.argmax(correlation[:valid_range]))
    peak_corr = correlation[sync_start]
    print(f"\nPico de correlação do sync na amostra {sync_start} "
          f"(t={sync_start/SAMPLE_RATE*1e3:.2f} ms), intensidade={peak_corr:.2f}")

    corr_t_ms = np.arange(len(correlation)) / SAMPLE_RATE * 1e3
    fig, axes = plt.subplots(1, 3, figsize=(18, 4.5), gridspec_kw={"width_ratios": [2, 1.3, 1]})
    axes[0].plot(corr_t_ms, correlation, lw=0.5)
    axes[0].axvline(sync_start / SAMPLE_RATE * 1e3, color="r", ls="--", alpha=0.7,
                    label="pico escolhido")
    axes[0].axvspan(corr_t_ms[valid_range - 1], corr_t_ms[-1], color="gray", alpha=0.2,
                    label="região ignorada (quadro não caberia)")
    axes[0].set_title("RX passo 4 — Correlação com o Barker-13 na captura inteira\n"
                      "(um pico por repetição do quadro)")
    axes[0].set_xlabel("Tempo (ms)")
    axes[0].legend(fontsize=8)
    axes[0].grid(True)
    corr_mask = np.abs(corr_t_ms - sync_start / SAMPLE_RATE * 1e3) <= 5
    axes[1].plot(corr_t_ms[corr_mask], correlation[corr_mask])
    axes[1].axvline(sync_start / SAMPLE_RATE * 1e3, color="r", ls="--", alpha=0.6)
    axes[1].set_title("Zoom ±5 ms em torno do pico")
    axes[1].set_xlabel("Tempo (ms)")
    axes[1].grid(True)
    # Autocorrelação ideal do Barker-13 vs. de um padrão alternado
    lv = bits_to_levels(SYNC_BITS)
    alt = bits_to_levels("10" * 6 + "1")
    lags = np.arange(-12, 13)
    axes[2].stem(lags, np.correlate(lv, lv, "full"), linefmt="C1-", markerfmt="C1o",
                 basefmt=" ", label="Barker-13")
    axes[2].plot(lags, np.correlate(alt, alt, "full"), "k.--", lw=0.8, label="1010...")
    axes[2].set_title("Por que Barker? Autocorrelação ideal\n(pico único vs. vários picos)")
    axes[2].set_xlabel("Deslocamento (bits)")
    axes[2].legend(fontsize=8)
    axes[2].grid(True)
    mostrar(fig, "rx_passo4_correlacao.png")

    # ================= Passo 5: limiar pelo preâmbulo =================
    preamble_start = sync_start - int(round(len(PREAMBLE_BITS) * samples_per_bit))
    if preamble_start < 0:
        raise RuntimeError("Pico de sync muito perto do início da captura.")

    preamble_levels = []
    for k, expected_bit in enumerate(PREAMBLE_BITS):
        seg_start = int(round(preamble_start + k * samples_per_bit))
        seg_end = int(round(preamble_start + (k + 1) * samples_per_bit))
        preamble_levels.append((expected_bit, np.mean(envelope[seg_start:seg_end])))

    high_level = np.mean([lvl for bit, lvl in preamble_levels if bit == "1"])
    low_level = np.mean([lvl for bit, lvl in preamble_levels if bit == "0"])
    threshold = (high_level + low_level) / 2
    print(f"Níveis do preâmbulo: alto={high_level:.4f}, baixo={low_level:.4f}, "
          f"limiar={threshold:.4f}")

    data_start = sync_start + int(round(len(SYNC_BITS) * samples_per_bit))

    fig, axes = plt.subplots(1, 2, figsize=(16, 4.5), gridspec_kw={"width_ratios": [2, 1]})
    pe = int(round(len(PREAMBLE_BITS) * samples_per_bit))
    tt = np.arange(preamble_start, data_start)
    axes[0].plot((tt - preamble_start) / samples_per_bit, envelope[tt], color="C2")
    for k, (bit, lvl) in enumerate(preamble_levels):
        axes[0].hlines(lvl, k, k + 1, colors="C1" if bit == "1" else "C0", lw=3)
    axes[0].axvline(len(PREAMBLE_BITS), color="k", ls=":")
    axes[0].text(len(PREAMBLE_BITS) + 0.2, high_level, "início do sync", fontsize=8)
    axes[0].axhline(high_level, color="C1", ls="--", lw=0.8, label=f"alto = {high_level:.4f}")
    axes[0].axhline(low_level, color="C0", ls="--", lw=0.8, label=f"baixo = {low_level:.4f}")
    axes[0].axhline(threshold, color="r", ls="--", label=f"limiar = {threshold:.4f}")
    axes[0].set_xlabel("Bits a partir do início do preâmbulo")
    axes[0].set_ylabel("Envoltória")
    axes[0].set_title("RX passo 5 — Preâmbulo + sync: média de cada bit conhecido define o limiar")
    axes[0].legend(fontsize=8, loc="lower right")
    axes[0].grid(True)

    # Diagrama de olho da envoltória, alinhado pelo sync
    spb = samples_per_bit
    n_eye_bits = min(300, int((len(envelope) - data_start) / spb) - 2)
    for k in range(n_eye_bits):
        a = int(round(data_start + (k - 0.5) * spb))
        seg = envelope[a: a + int(round(2 * spb))]
        axes[1].plot(np.arange(len(seg)) / spb - 0.5, seg, color="C2", alpha=0.08, lw=0.8)
    axes[1].axhline(threshold, color="r", ls="--")
    axes[1].axvspan(0, 1, color="yellow", alpha=0.15, label="janela de média do bit")
    axes[1].set_xlabel("Tempo (períodos de bit)")
    axes[1].set_title("Diagrama de olho da envoltória")
    axes[1].legend(fontsize=8, loc="upper right")
    axes[1].grid(True)
    mostrar(fig, "rx_passo5_limiar_olho.png")

    # ================= Passo 6: decisão e decodificação =================
    length_bits, payload_start = read_bits(envelope, data_start, 8, samples_per_bit, threshold)
    if length_bits is None:
        raise RuntimeError("A captura terminou antes do campo de comprimento.")
    payload_len = int(length_bits, 2)
    print(f"Byte de comprimento: {length_bits} = {payload_len} bytes")

    payload_bits, crc_start = read_bits(
        envelope, payload_start, payload_len * 8, samples_per_bit, threshold
    )
    if payload_bits is None:
        raise RuntimeError("A captura terminou antes do payload completo.")

    payload_bytes = bytes(int(payload_bits[i:i + 8], 2) for i in range(0, len(payload_bits), 8))
    message = payload_bytes.decode("ascii", errors="replace")

    crc_bits, frame_end = read_bits(envelope, crc_start, 8, samples_per_bit, threshold)
    received_crc = int(crc_bits, 2) if crc_bits else None
    computed_crc = crc8(payload_bytes)
    crc_ok = received_crc == computed_crc

    print("\nBits -> bytes -> caracteres:")
    for i, b in enumerate(payload_bytes):
        print(f"  {payload_bits[8*i:8*i+8]} = {b:#04x} = {chr(b)!r}")
    print(f"\nMensagem decodificada: {message!r}")
    print(f"CRC-8 recebido={received_crc:#04x} calculado={computed_crc:#04x} "
          f"-> {'OK' if crc_ok else 'DIVERGENTE'}")

    # Comparação com o que foi transmitido (só possível na simulação)
    tx_bits = None
    try:
        from tx_ook_sim import build_frame_bits, MESSAGE as TX_MESSAGE
        tx_frame_bits, _ = build_frame_bits(TX_MESSAGE)
        n_dec = 8 + 8 * payload_len + 8
        tx_bits = tx_frame_bits[len(PREAMBLE_BITS) + len(SYNC_BITS):][:n_dec]
        rx_bits = length_bits + payload_bits + crc_bits
        n_err = sum(a != b for a, b in zip(tx_bits, rx_bits)) + abs(len(tx_bits) - len(rx_bits))
        print(f"[SIMULAÇÃO] Bits errados (comparando com o TX): {n_err} de {len(rx_bits)}")
    except Exception:
        pass
    if os.path.exists(ARQUIVO_INFO):
        with open(ARQUIVO_INFO) as fp:
            info = json.load(fp)
        print(f"[SIMULAÇÃO] Canal usado: SNR={info['snr_db']} dB, "
              f"erro de frequência={info['erro_freq_hz']:+.0f} Hz")

    # Gráfico: envoltória do quadro com campos, janelas de bit e decisões
    all_bits = PREAMBLE_BITS + SYNC_BITS + length_bits + payload_bits + crc_bits
    fields = [("preâmbulo", preamble_start, sync_start), ("sync", sync_start, data_start),
              ("compr.", data_start, payload_start), ("payload", payload_start, crc_start),
              ("CRC", crc_start, frame_end)]
    colors = {"preâmbulo": "#9ecae1", "sync": "#fdae6b", "compr.": "#a1d99b",
              "payload": "#dadaeb", "CRC": "#fc9272"}
    means = bit_means(envelope, preamble_start, len(all_bits), samples_per_bit)

    fig, axes = plt.subplots(2, 1, figsize=(17, 8))
    to_ms = 1e3 / SAMPLE_RATE
    for ax in axes:
        for name, a, b in fields:
            ax.axvspan(a * to_ms, b * to_ms, color=colors[name], alpha=0.45, lw=0)
    seg = slice(preamble_start, frame_end)
    axes[0].plot(np.arange(len(envelope))[seg] * to_ms, envelope[seg], color="k", lw=0.8,
                 label="envoltória")
    axes[0].axhline(threshold, color="r", ls="--", label="limiar")
    ymax = max(high_level * 1.35, threshold * 2)
    for name, a, b in fields:
        axes[0].text((a + b) / 2 * to_ms, ymax * 0.97, name, ha="center", va="top", fontsize=9)
    axes[0].set_ylim(min(0, low_level * 1.2), ymax)
    axes[0].set_ylabel("Amplitude")
    axes[0].set_title(f"RX passo 6 — Quadro decodificado: {message!r}   "
                      f"CRC {'OK' if crc_ok else 'DIVERGENTE'}")
    axes[0].legend(loc="lower right", fontsize=8)
    axes[0].grid(True, alpha=0.3)

    # Médias por bit (o que é comparado com o limiar) e o bit decidido
    centers = (preamble_start + (np.arange(len(all_bits)) + 0.5) * samples_per_bit) * to_ms
    ref_bits = None
    if tx_bits is not None:
        ref_bits = PREAMBLE_BITS + SYNC_BITS + tx_bits
    for k, (c, mval, bit) in enumerate(zip(centers, means, all_bits)):
        wrong = ref_bits is not None and k < len(ref_bits) and ref_bits[k] != bit
        col = "red" if wrong else ("C1" if bit == "1" else "C0")
        axes[1].bar(c, mval, width=0.8 * 1e3 / BIT_RATE, color=col)
        axes[1].text(c, -0.08 * ymax, bit, ha="center", va="top", fontsize=6,
                     family="monospace", color=col)
    p_ms = payload_start * to_ms
    for i, ch in enumerate(message):
        axes[1].text(p_ms + (8 * i + 4) * 1e3 / BIT_RATE, ymax * 0.9, ch, ha="center",
                     fontsize=10, family="monospace", color="navy", weight="bold")
    axes[1].axhline(threshold, color="r", ls="--")
    axes[1].set_ylim(-0.16 * ymax, ymax)
    axes[1].set_xlabel("Tempo (ms)")
    axes[1].set_ylabel("Média por bit")
    axes[1].set_title("Média da envoltória em cada bit → decisão (laranja = 1, azul = 0, "
                      "vermelho = bit errado) → caracteres")
    axes[1].grid(True, alpha=0.3)
    mostrar(fig, "rx_passo6_decodificacao.png")

    if not PAUSAR_ENTRE_PASSOS:
        plt.show()
