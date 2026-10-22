
#!/usr/bin/env python3

import numpy as np
import matplotlib

# Backend gráfico interativo
matplotlib.use("Qt5Agg")

import matplotlib.pyplot as plt
from rtlsdr import RtlSdr

# ==========================================
# Configurações
# ==========================================

FREQ_MIN = 88e6
FREQ_MAX = 108e6

SAMPLE_RATE = 2.4e6
FFT_SIZE = 4096
NUM_SAMPLES = 256 * 1024

# Ganho manual fixo em dB
GAIN = 20

# Sobreposição entre blocos
OVERLAP = 0.20
BANDWIDTH = SAMPLE_RATE * (1 - OVERLAP)

CENTERS = np.arange(
    FREQ_MIN + SAMPLE_RATE / 2,
    FREQ_MAX,
    BANDWIDTH
)

if CENTERS[-1] + SAMPLE_RATE / 2 < FREQ_MAX:
    CENTERS = np.append(
        CENTERS,
        FREQ_MAX - SAMPLE_RATE / 2
    )


def capture_spectrum(sdr, center_freq):
    """Retorna frequências e potência digital em dBFS."""

    sdr.center_freq = float(center_freq)

    # Descarta amostras iniciais após a sintonia
    sdr.read_samples(8192)

    samples = np.asarray(sdr.read_samples(NUM_SAMPLES))

    n_blocks = len(samples) // FFT_SIZE
    samples = samples[:n_blocks * FFT_SIZE]
    blocks = samples.reshape(n_blocks, FFT_SIZE)

    # Remove o componente DC médio de cada bloco
    blocks = blocks - np.mean(blocks, axis=1, keepdims=True)

    window = np.hanning(FFT_SIZE)

    # Normalização da FFT pela soma da janela
    spectra = np.fft.fftshift(
        np.fft.fft(blocks * window, axis=1),
        axes=1
    ) / np.sum(window)

    # Potência média por bin, normalizada para escala digital
    power = np.mean(np.abs(spectra) ** 2, axis=0)

    # dBFS por bin: 0 dBFS corresponde à amplitude digital de referência
    power_dbfs = 10 * np.log10(power + 1e-15)

    freq = (
        center_freq
        + np.fft.fftshift(
            np.fft.fftfreq(FFT_SIZE, d=1 / SAMPLE_RATE)
        )
    )

    return freq, power_dbfs


def main():
    sdr = None

    try:
        print("Inicializando RTL-SDR...")

        sdr = RtlSdr()
        sdr.sample_rate = SAMPLE_RATE

        # Ganho manual constante
        sdr.gain = GAIN

        print(f"Ganho configurado: {GAIN} dB")
        print(f"Faixa: {FREQ_MIN / 1e6:.1f} a {FREQ_MAX / 1e6:.1f} MHz")

        plt.ion()
        fig, ax = plt.subplots(figsize=(13, 6))

        line, = ax.plot(
            [],
            [],
            color="deepskyblue",
            linewidth=0.8
        )

        ax.set_xlim(FREQ_MIN / 1e6, FREQ_MAX / 1e6)
        ax.set_ylim(-100, -20)
        ax.set_xlabel("Frequência (MHz)")
        ax.set_ylabel("Potência por bin (dBFS)")
        ax.set_title(
            f"RTL-SDR R820T/2 — Espectro FM | Ganho: {GAIN} dB"
        )
        ax.grid(True, alpha=0.3)

        fig.tight_layout()
        plt.show(block=False)

        print("Varredura iniciada. Feche a janela para encerrar.")

        while plt.fignum_exists(fig.number):
            all_freq = []
            all_power = []

            for center in CENTERS:
                if not plt.fignum_exists(fig.number):
                    break

                freq, power = capture_spectrum(sdr, center)

                mask = (freq >= FREQ_MIN) & (freq <= FREQ_MAX)

                all_freq.append(freq[mask])
                all_power.append(power[mask])

            if not plt.fignum_exists(fig.number):
                break

            freq = np.concatenate(all_freq) / 1e6
            power = np.concatenate(all_power)

            order = np.argsort(freq)
            freq = freq[order]
            power = power[order]

            line.set_data(freq, power)

            # Escala vertical estável para facilitar comparações
            ax.set_ylim(-110, -20)

            fig.canvas.draw_idle()
            fig.canvas.flush_events()
            plt.pause(0.05)

    except KeyboardInterrupt:
        print("\nVarredura interrompida.")

    finally:
        if sdr is not None:
            sdr.close()

        plt.close("all")
        print("RTL-SDR encerrado.")


if __name__ == "__main__":
    main()

