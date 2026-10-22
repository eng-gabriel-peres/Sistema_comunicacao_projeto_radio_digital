"""
Canal de RF + RTL-SDR — SIMULADO.

Substitui o "mundo real" entre o Pluto e o RTL-SDR. Lê 'tx_iq.npy'
(gerado por tx_ook_sim.py) e produz 'rx_iq.npy', que é o que o
sdr.read_samples() do RTL-SDR entregaria.

Efeitos modelados (cada um pode ser ligado/desligado ou ajustado abaixo):
    1. Buffer cíclico do Pluto: o quadro se repete sem parar.
    2. Atraso aleatório: o RX começa a capturar em um ponto qualquer do quadro.
    3. Taxas de amostragem diferentes: TX a 2,000 MS/s, RX a 2,048 MS/s
       (reamostragem 128/125).
    4. Erro de frequência (CFO): os osciladores do Pluto e do RTL nunca
       são idênticos. 1 ppm em 915 MHz = 915 Hz. O FREQ_CORRECTION_PPM
       do RX corrige a maior parte; sobra um resíduo.
    5. Fase aleatória da portadora.
    6. Atenuação do canal + ruído branco gaussiano (AWGN) com SNR definida.
    7. Offset DC do RTL-SDR (o famoso "pico" no centro do espectro).
    8. Quantização de 8 bits do ADC do RTL-SDR (com saturação).

Experimente: SNR_DB = 0 ou -10, ERRO_FREQ_HZ = 8e3 ou 15e3 e veja o RX falhar.

Requer: pip install numpy matplotlib scipy
Próximo passo: python rx_ook_sim.py
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt

try:
    from scipy.signal import resample_poly
except ImportError:          # sem scipy: interpolação linear (menos precisa)
    resample_poly = None

# ---- Parâmetros que devem bater com TX e RX ----
TX_SAMPLE_RATE = 2e6
RX_SAMPLE_RATE = 2.048e6
TX_DAC_FULL_SCALE = 2**15        # o Pluto usa amostras de 16 bits
CAPTURE_SECONDS = 0.5
CHUNK_SIZE = 256 * 1024

# ---- Parâmetros do canal (mexa aqui!) ----
SNR_DB = 10.0              # potência do tom (bit 1) / potência do ruído em toda a banda de 2 MHz
ERRO_FREQ_HZ = 1.5e3       # resíduo de frequência após a correção de ppm do RX
AMPLITUDE_RX = 0.3         # amplitude do tom na entrada do ADC (1.0 = fundo de escala)
OFFSET_DC = 0.02 + 0.01j   # offset DC do RTL-SDR (0 para desligar)
QUANTIZAR_8_BITS = True    # ADC de 8 bits do RTL-SDR
SEMENTE = None             # número inteiro para resultados repetíveis

ARQUIVO_ENTRADA = "tx_iq.npy"
ARQUIVO_SAIDA = "rx_iq.npy"
ARQUIVO_INFO = "canal_info.json"
PASTA_FIGURAS = "figuras"
PAUSAR_ENTRE_PASSOS = True


def mostrar(fig, nome):
    os.makedirs(PASTA_FIGURAS, exist_ok=True)
    fig.tight_layout()
    fig.savefig(os.path.join(PASTA_FIGURAS, nome), dpi=110)
    if PAUSAR_ENTRE_PASSOS:
        plt.show()


def psd_db(x, fs, nfft=4096):
    win = np.hanning(nfft)
    segs = x[: (len(x) // nfft) * nfft].reshape(-1, nfft)
    p = np.mean(np.abs(np.fft.fftshift(np.fft.fft(segs * win, axis=1), axes=1)) ** 2, axis=0)
    p /= fs * np.sum(win ** 2)
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / fs))
    return f, 10 * np.log10(p + 1e-20)


if __name__ == "__main__":
    rng = np.random.default_rng(SEMENTE)

    tx_frame = np.load(ARQUIVO_ENTRADA).astype(np.complex128) / TX_DAC_FULL_SCALE
    frame_len = len(tx_frame)
    print(f"Quadro TX: {frame_len} amostras ({frame_len/TX_SAMPLE_RATE*1e3:.2f} ms)")

    # Número de amostras que o RX vai capturar (mesma lógica de capture_chunks)
    num_chunks = int(np.ceil((CAPTURE_SECONDS * RX_SAMPLE_RATE) / CHUNK_SIZE))
    n_rx = num_chunks * CHUNK_SIZE
    n_tx_needed = int(np.ceil(n_rx * TX_SAMPLE_RATE / RX_SAMPLE_RATE)) + 2 * frame_len

    # 1+2. Buffer cíclico e início aleatório da captura
    atraso = int(rng.integers(0, frame_len))
    reps = int(np.ceil((n_tx_needed + atraso) / frame_len))
    tx_stream = np.tile(tx_frame, reps)[atraso: atraso + n_tx_needed]
    print(f"Captura começa {atraso} amostras TX após o início de um quadro "
          f"({atraso/TX_SAMPLE_RATE*1e3:.2f} ms)")

    # 3. Reamostragem 2,000 -> 2,048 MS/s (razão 128/125)
    if resample_poly is not None:
        rx = resample_poly(tx_stream, 128, 125)
    else:
        t_tx = np.arange(len(tx_stream)) / TX_SAMPLE_RATE
        t_rx = np.arange(int(len(tx_stream) * 128 / 125)) / RX_SAMPLE_RATE
        rx = np.interp(t_rx, t_tx, tx_stream.real) + 1j * np.interp(t_rx, t_tx, tx_stream.imag)
    rx = rx[:n_rx]
    clean_ref = rx.copy()   # guardado só para os gráficos

    # 4+5. Erro de frequência e fase aleatória
    t = np.arange(n_rx) / RX_SAMPLE_RATE
    fase = rng.uniform(0, 2 * np.pi)
    rx = rx * np.exp(1j * (2 * np.pi * ERRO_FREQ_HZ * t + fase))

    # 6. Atenuação + AWGN. O tom (bit 1) tem amplitude 0.5 após a normalização;
    #    reescalamos para AMPLITUDE_RX e ajustamos o ruído pela SNR.
    rx *= AMPLITUDE_RX / 0.5
    p_sinal = AMPLITUDE_RX ** 2
    p_ruido = p_sinal / 10 ** (SNR_DB / 10)
    ruido = np.sqrt(p_ruido / 2) * (rng.standard_normal(n_rx) + 1j * rng.standard_normal(n_rx))
    rx = rx + ruido

    # 7. Offset DC
    rx = rx + OFFSET_DC

    # 8. ADC de 8 bits (o pyrtlsdr devolve (uint8 - 127.5)/127.5)
    if QUANTIZAR_8_BITS:
        def q8(v):
            return (np.clip(np.round(v * 127.5 + 127.5), 0, 255) - 127.5) / 127.5
        rx = q8(rx.real) + 1j * q8(rx.imag)

    samples = rx.astype(np.complex64)
    np.save(ARQUIVO_SAIDA, samples)
    info = {"rx_sample_rate": RX_SAMPLE_RATE, "atraso_amostras_tx": atraso,
            "erro_freq_hz": ERRO_FREQ_HZ, "snr_db": SNR_DB, "fase_rad": fase,
            "amostras": n_rx}
    with open(ARQUIVO_INFO, "w") as fp:
        json.dump(info, fp, indent=2)

    snr_filtro = SNR_DB + 10 * np.log10(RX_SAMPLE_RATE / (2 * 10e3))
    print(f"SNR na banda inteira = {SNR_DB:.1f} dB -> após o filtro de ±10 kHz do RX "
          f"≈ {snr_filtro:.1f} dB (ganho de processamento)")
    print(f"Erro de frequência = {ERRO_FREQ_HZ:+.0f} Hz "
          f"(≈ {ERRO_FREQ_HZ/915:.2f} ppm em 915 MHz), fase = {np.degrees(fase):.0f}°")
    print(f"{n_rx} amostras salvas em '{ARQUIVO_SAIDA}' "
          f"({n_rx/RX_SAMPLE_RATE*1e3:.1f} ms a {RX_SAMPLE_RATE/1e6:.3f} MS/s)")

    # ---- Passo 1: domínio do tempo, antes e depois do canal ----
    n_show = int(3 * frame_len * RX_SAMPLE_RATE / TX_SAMPLE_RATE)
    t_ms = t[:n_show] * 1e3
    fig, axes = plt.subplots(2, 1, figsize=(16, 7), sharex=True)
    axes[0].plot(t_ms, np.abs(clean_ref[:n_show]), lw=0.7)
    axes[0].set_title("Canal passo 1 — |sinal| sem efeitos do canal "
                      "(repetições do quadro, captura começando no meio de um quadro)")
    axes[0].set_ylabel("|x|")
    axes[0].grid(True)
    axes[1].plot(t_ms, np.abs(samples[:n_show]), lw=0.4, color="C1")
    axes[1].set_title(f"|sinal| que chega ao RX: SNR = {SNR_DB:.0f} dB em 2 MHz, "
                      "DC offset, 8 bits — o quadro quase some no ruído")
    axes[1].set_ylabel("|x|")
    axes[1].set_xlabel("Tempo (ms)")
    axes[1].grid(True)
    mostrar(fig, "canal_passo1_tempo.png")

    # ---- Passo 2: espectro antes e depois ----
    f, p_clean = psd_db(clean_ref * AMPLITUDE_RX / 0.5, RX_SAMPLE_RATE)
    _, p_rx = psd_db(samples.astype(np.complex128), RX_SAMPLE_RATE)
    fig, axes = plt.subplots(1, 2, figsize=(16, 4.5))
    axes[0].plot(f / 1e3, p_rx, color="C1", label="recebido")
    axes[0].plot(f / 1e3, p_clean, color="C0", alpha=0.7, label="sem ruído/CFO")
    axes[0].set_xlabel("Frequência em banda-base (kHz)")
    axes[0].set_ylabel("DEP (dB/Hz)")
    axes[0].set_title("Canal passo 2 — Espectro: tom em +200 kHz, pico DC em 0 Hz, piso de ruído")
    axes[0].legend()
    axes[0].grid(True)
    m = np.abs(f - 200e3) <= 40e3
    axes[1].plot((f[m] - 200e3) / 1e3, p_rx[m], color="C1", label="recebido")
    axes[1].plot((f[m] - 200e3) / 1e3, p_clean[m], color="C0", alpha=0.7, label="sem ruído/CFO")
    axes[1].axvspan(-10, 10, color="green", alpha=0.12, label="passa-faixa do RX (±10 kHz)")
    axes[1].axvline(ERRO_FREQ_HZ / 1e3, color="r", ls="--", label=f"CFO = {ERRO_FREQ_HZ:+.0f} Hz")
    axes[1].set_xlabel("Desvio em relação a +200 kHz (kHz)")
    axes[1].set_title("Zoom: o erro de frequência desloca o sinal dentro do filtro")
    axes[1].legend(fontsize=8)
    axes[1].grid(True)
    mostrar(fig, "canal_passo2_espectro.png")

    # ---- Passo 3: plano IQ ----
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    k = slice(0, 20000)
    axes[0].plot(clean_ref[k].real, clean_ref[k].imag, ".", ms=1)
    axes[0].set_title("IQ antes do canal")
    axes[1].plot(samples[k].real, samples[k].imag, ".", ms=1, color="C1", alpha=0.4)
    axes[1].set_title("IQ na saída do RTL-SDR (8 bits, ruído, DC)")
    for a in axes:
        a.set_aspect("equal")
        a.set_xlim(-1, 1)
        a.set_ylim(-1, 1)
        a.grid(True)
        a.set_xlabel("I")
        a.set_ylabel("Q")
    fig.suptitle("Canal passo 3 — Plano IQ")
    mostrar(fig, "canal_passo3_iq.png")

    print("Próximo passo: python rx_ook_sim.py")
    if not PAUSAR_ENTRE_PASSOS:
        plt.show()
