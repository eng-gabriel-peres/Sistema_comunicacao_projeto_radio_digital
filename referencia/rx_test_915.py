"""
RTL-SDR RX test script.

1. Runs a short calibration capture, using a known TX tone (must match the
   TONE_FREQ used in pluto_tx.py) to measure the dongle's PPM frequency
   error, and applies that correction.
2. Captures 5 seconds of IQ data around 915 MHz (in safe, moderate-sized
   chunks to avoid USB buffer overflow).
3. Plots the spectrum and auto-zooms around the strongest peak found.

Requires: pip install pyrtlsdr matplotlib numpy
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab
from rtlsdr import RtlSdr

# ---- Configuration (should match the TX center frequency / tone) ----
CENTER_FREQ = 915e6         # Hz
SAMPLE_RATE = 2.048e6       # Hz (RTL-SDR max is ~3.2 MHz, but not fully stable there)
GAIN = 30                   # dB, manual gain (try 'auto' if this saturates or is too low)
EXPECTED_TONE_OFFSET_HZ = 200e3   # must match TONE_FREQ in pluto_tx.py

CAPTURE_SECONDS = 5.0        # total duration of the main capture
CHUNK_SIZE = 256 * 1024      # samples per read call (keep moderate to avoid overflow)

CALIBRATION_SECONDS = 1.0    # shorter capture just for PPM estimation

# Frequencies too close to DC (0 Hz baseband) are dominated by the RTL-SDR's
# DC spike, so we exclude a small window around it when looking for the
# real signal peak.
DC_EXCLUDE_HZ = 20e3
ZOOM_HALF_SPAN_HZ = 150e3    # how wide a window to zoom into around the peak
YLIM_MARGIN_DB = 5
CALIBRATION_NFFT = 4096
MAIN_NFFT = 4096


def capture_chunks(sdr, total_seconds, chunk_size, sample_rate, label=""):
    num_chunks = int(np.ceil((total_seconds * sample_rate) / chunk_size))
    chunks = []
    for idx in range(num_chunks):
        chunk = sdr.read_samples(chunk_size)
        chunks.append(chunk)
        if label:
            print(f"  [{label}] chunk {idx + 1}/{num_chunks} captured", end="\r")
    if label:
        print()
    return np.concatenate(chunks)


def find_peak(samples, sample_rate, center_freq, nfft, dc_exclude_hz):
    Pxx, freqs = mlab.psd(samples, NFFT=nfft, Fs=sample_rate)
    Pxx_db = 10 * np.log10(Pxx)
    mask = np.abs(freqs) > dc_exclude_hz
    peak_idx = np.argmax(Pxx_db[mask])
    peak_freq_offset = freqs[mask][peak_idx]
    peak_power_db = Pxx_db[mask][peak_idx]
    return peak_freq_offset, peak_power_db, freqs, Pxx_db


# ---- Connect ----
sdr = RtlSdr()
sdr.sample_rate = SAMPLE_RATE
sdr.center_freq = CENTER_FREQ
sdr.gain = GAIN
sdr.freq_correction = 34

# Discard the first read: the very first samples after tuning are often
# stale/settling and not representative.
_ = sdr.read_samples(CHUNK_SIZE)

# ---- Step 1: Calibration ----
print(f"Calibrating using expected tone at +{EXPECTED_TONE_OFFSET_HZ/1e3:.1f} kHz offset...")
calib_samples = capture_chunks(sdr, CALIBRATION_SECONDS, CHUNK_SIZE, SAMPLE_RATE, label="calibration")

measured_offset, measured_power_db, _, _ = find_peak(
    calib_samples, SAMPLE_RATE, CENTER_FREQ, CALIBRATION_NFFT, DC_EXCLUDE_HZ
)
measured_freq = CENTER_FREQ + measured_offset
expected_freq = CENTER_FREQ + EXPECTED_TONE_OFFSET_HZ
ppm_error = (expected_freq - measured_freq) / CENTER_FREQ * 1e6

print(f"  Measured peak: {measured_freq/1e6:.4f} MHz ({measured_offset/1e3:+.1f} kHz offset), "
      f"{measured_power_db:.1f} dB")
print(f"  Expected peak: {expected_freq/1e6:.4f} MHz ({EXPECTED_TONE_OFFSET_HZ/1e3:+.1f} kHz offset)")
print(f"  Estimated PPM error: {ppm_error:+.1f} ppm")

ppm_correction = int(round(ppm_error))
sdr.freq_correction = ppm_correction
sdr.center_freq = CENTER_FREQ  # re-tune so the correction takes effect
print(f"  Applied freq_correction = {ppm_correction} ppm\n")

# ---- Step 2: Main 5-second capture (now frequency-corrected) ----
print(f"Capturing ~{CAPTURE_SECONDS:.1f} s at {CENTER_FREQ/1e6:.3f} MHz center, "
      f"{SAMPLE_RATE/1e6:.3f} MSPS...")
samples = capture_chunks(sdr, CAPTURE_SECONDS, CHUNK_SIZE, SAMPLE_RATE, label="main")
sdr.close()

actual_duration = len(samples) / SAMPLE_RATE
print(f"Total samples: {len(samples)} (~{actual_duration:.2f} s)")

# ---- Compute PSD on the corrected capture ----
peak_freq_offset, peak_power_db, freqs, Pxx_db = find_peak(
    samples, SAMPLE_RATE, CENTER_FREQ, MAIN_NFFT, DC_EXCLUDE_HZ
)
abs_freq_mhz = (CENTER_FREQ + freqs) / 1e6
peak_freq_mhz = (CENTER_FREQ + peak_freq_offset) / 1e6

print(f"Strongest peak (post-correction): {peak_freq_mhz:.4f} MHz "
      f"({peak_freq_offset/1e3:+.1f} kHz offset), {peak_power_db:.1f} dB")

# ---- Plot full spectrum ----
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

axes[0].plot(abs_freq_mhz, Pxx_db)
axes[0].set_xlabel("Frequency (MHz)")
axes[0].set_ylabel("Power (dB)")
axes[0].set_title(f"Full captured spectrum (ppm correction: {ppm_correction})")
axes[0].grid(True)
axes[0].axvline(peak_freq_mhz, color="r", linestyle="--", alpha=0.6)

# ---- Auto-zoomed plot around the detected peak ----
zoom_mask = np.abs(freqs - peak_freq_offset) <= ZOOM_HALF_SPAN_HZ
zoom_freqs_mhz = abs_freq_mhz[zoom_mask]
zoom_power_db = Pxx_db[zoom_mask]

axes[1].plot(zoom_freqs_mhz, zoom_power_db)
axes[1].set_xlabel("Frequency (MHz)")
axes[1].set_ylabel("Power (dB)")
axes[1].set_title(f"Auto-zoomed around peak ({peak_freq_mhz:.4f} MHz)")
axes[1].grid(True)
axes[1].axvline(peak_freq_mhz, color="r", linestyle="--", alpha=0.6,
                 label=f"Peak @ {peak_freq_mhz:.4f} MHz")
axes[1].set_xlim(zoom_freqs_mhz.min(), zoom_freqs_mhz.max())
axes[1].set_ylim(zoom_power_db.min() - YLIM_MARGIN_DB,
                  zoom_power_db.max() + YLIM_MARGIN_DB)
axes[1].legend()

plt.tight_layout()
plt.show()