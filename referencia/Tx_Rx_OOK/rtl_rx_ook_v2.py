"""
RTL-SDR RX script v2 — Framed OOK text message receiver.

Decodes the frame built by pluto_tx_ook_v2.py:

    [ 16-bit alternating preamble ] [ 13-bit Barker sync word ]
    [ 8-bit length ] [ payload: 8 bits/char ] [ 8-bit CRC-8 ] [ 16-bit guard ]

Instead of guessing a bit-alignment offset (as rtl_rx_ook.py did), this
version finds the exact frame start by cross-correlating the received
envelope against the known Barker-13 sync word. Barker codes have a sharp,
unambiguous autocorrelation peak, which also solves the bit-phase-ambiguity
problem you'd get trying to sync on a plain alternating pattern (e.g.
"10101010..." vs "01010101..." look identical after a 1-bit shift; a
Barker code does not).

Requires: pip install pyrtlsdr numpy matplotlib
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab
from rtlsdr import RtlSdr

# ---- Configuration (should match pluto_tx_ook_v2.py) ----
CENTER_FREQ = 915e6
SAMPLE_RATE = 2.048e6
GAIN = 30
FREQ_CORRECTION_PPM = 34

TONE_FREQ_OFFSET = 200e3
BIT_RATE = 10e3

PREAMBLE_BITS = "10" * 8
SYNC_BITS = "1111100110101"          # Barker-13, must match TX
MAX_EXPECTED_PAYLOAD_BYTES = 64      # just used to bound the correlation
                                      # search margin near the end of the
                                      # capture; the actual decode uses the
                                      # length byte, not this value

CAPTURE_SECONDS = 0.5
CHUNK_SIZE = 256 * 1024

BANDPASS_HALF_WIDTH_HZ = 10e3        # 915.19-915.21 MHz, same as v1 fix
LOWPASS_CUTOFF_HZ = BIT_RATE * 3

SPECTRUM_NFFT = 4096
SPECTRUM_ZOOM_HALF_SPAN_HZ = 60e3


def capture_chunks(sdr, total_seconds, chunk_size, sample_rate):
    num_chunks = int(np.ceil((total_seconds * sample_rate) / chunk_size))
    chunks = []
    for idx in range(num_chunks):
        chunks.append(sdr.read_samples(chunk_size))
        print(f"  chunk {idx + 1}/{num_chunks} captured", end="\r")
    print()
    return np.concatenate(chunks)


def simple_lowpass(signal, sample_rate, cutoff_hz, numtaps=None):
    """Windowed-sinc FIR lowpass (see rtl_rx_ook.py for the tap-count
    reasoning). Works on complex input too, since np.convolve accepts a
    complex array with real taps."""
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
    return np.convolve(signal, h, mode="same"), numtaps


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
    """Map a bit string to +-0.5 around zero, for a zero-mean matched-
    filter template (better correlation behavior than 0/1 levels)."""
    return np.array([0.5 if b == "1" else -0.5 for b in bits])


def read_bits(envelope, start_sample, num_bits, samples_per_bit, threshold):
    """Average the envelope over each bit period starting at start_sample
    and threshold to 0/1. Returns the bit string and the end sample."""
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


# ---- Connect ----
sdr = RtlSdr()
sdr.sample_rate = SAMPLE_RATE
sdr.center_freq = CENTER_FREQ
sdr.gain = GAIN
sdr.freq_correction = FREQ_CORRECTION_PPM

_ = sdr.read_samples(CHUNK_SIZE)

print(f"Capturing ~{CAPTURE_SECONDS:.2f} s at {CENTER_FREQ/1e6:.3f} MHz, "
      f"gain={GAIN} dB, ppm={FREQ_CORRECTION_PPM}...")
samples = capture_chunks(sdr, CAPTURE_SECONDS, CHUNK_SIZE, SAMPLE_RATE)
sdr.close()

actual_duration = len(samples) / SAMPLE_RATE
print(f"Total samples: {len(samples)} (~{actual_duration*1e3:.1f} ms)")

# ---- Mix down from the +200 kHz offset used on TX ----
t = np.arange(len(samples)) / SAMPLE_RATE
mix = samples * np.exp(-1j * 2 * np.pi * TONE_FREQ_OFFSET * t)

# ---- Complex bandpass (915.19-915.21 MHz), then envelope, then smoothing ----
mix_filtered, bandpass_numtaps = simple_lowpass(mix, SAMPLE_RATE, BANDPASS_HALF_WIDTH_HZ)
print(f"Complex bandpass: +/-{BANDPASS_HALF_WIDTH_HZ/1e3:.1f} kHz around baseband, "
      f"numtaps={bandpass_numtaps}")

bandpassed_envelope = np.abs(mix_filtered)
envelope, lowpass_numtaps = simple_lowpass(bandpassed_envelope, SAMPLE_RATE, LOWPASS_CUTOFF_HZ)
print(f"Envelope smoothing: cutoff={LOWPASS_CUTOFF_HZ/1e3:.1f} kHz, numtaps={lowpass_numtaps}")

# ---- Frame sync: cross-correlate the envelope against the Barker-13
#      sync word (upsampled to sample domain) to find the exact frame
#      start, instead of guessing an offset ----
samples_per_bit = SAMPLE_RATE / BIT_RATE
sync_template = np.repeat(bits_to_levels(SYNC_BITS), int(round(samples_per_bit)))

envelope_zero_mean = envelope - np.mean(envelope)
correlation = np.correlate(envelope_zero_mean, sync_template, mode="valid")

# Don't consider peaks so close to the end of the capture that a full
# frame (length + payload + CRC) couldn't possibly fit after them.
max_trailing_bits = 8 + 8 * MAX_EXPECTED_PAYLOAD_BYTES + 8
max_trailing_samples = int(max_trailing_bits * samples_per_bit)
valid_range = len(correlation) - max_trailing_samples
if valid_range <= 0:
    raise RuntimeError("Capture too short relative to MAX_EXPECTED_PAYLOAD_BYTES — "
                        "increase CAPTURE_SECONDS or lower MAX_EXPECTED_PAYLOAD_BYTES.")

sync_start = int(np.argmax(correlation[:valid_range]))
peak_corr = correlation[sync_start]
print(f"\nSync correlation peak at sample {sync_start} "
      f"(t={sync_start/SAMPLE_RATE*1e3:.2f} ms), strength={peak_corr:.2f}")

# ---- Estimate the amplitude threshold from the known preamble bits,
#      which sit right before the sync word ----
preamble_start = sync_start - int(round(len(PREAMBLE_BITS) * samples_per_bit))
if preamble_start < 0:
    raise RuntimeError("Sync peak too close to the start of the capture to "
                        "read the preceding preamble — try a longer capture.")

preamble_bits_str, _ = read_bits(
    envelope, preamble_start, len(PREAMBLE_BITS), samples_per_bit, threshold=0
)
# Use the KNOWN preamble bit values (not the just-decoded ones) to get
# clean high/low level estimates, since we know exactly which samples
# should be '1' and which should be '0'.
preamble_levels = []
for k, expected_bit in enumerate(PREAMBLE_BITS):
    seg_start = int(round(preamble_start + k * samples_per_bit))
    seg_end = int(round(preamble_start + (k + 1) * samples_per_bit))
    preamble_levels.append((expected_bit, np.mean(envelope[seg_start:seg_end])))

high_level = np.mean([lvl for bit, lvl in preamble_levels if bit == "1"])
low_level = np.mean([lvl for bit, lvl in preamble_levels if bit == "0"])
threshold = (high_level + low_level) / 2
print(f"Preamble levels: high={high_level:.4f}, low={low_level:.4f}, "
      f"threshold={threshold:.4f}")

# ---- Decode length, payload, CRC starting right after the sync word ----
data_start = sync_start + int(round(len(SYNC_BITS) * samples_per_bit))

length_bits, payload_start = read_bits(envelope, data_start, 8, samples_per_bit, threshold)
if length_bits is None:
    raise RuntimeError("Capture ended before the length field could be read.")
payload_len = int(length_bits, 2)
print(f"Decoded length byte: {length_bits} = {payload_len} bytes")

payload_bits, crc_start = read_bits(
    envelope, payload_start, payload_len * 8, samples_per_bit, threshold
)
if payload_bits is None:
    raise RuntimeError("Capture ended before the full payload could be read — "
                        "increase CAPTURE_SECONDS.")

payload_bytes = bytes(
    int(payload_bits[i:i + 8], 2) for i in range(0, len(payload_bits), 8)
)
message = payload_bytes.decode("ascii", errors="replace")

crc_bits, frame_end = read_bits(envelope, crc_start, 8, samples_per_bit, threshold)
received_crc = int(crc_bits, 2) if crc_bits else None
computed_crc = crc8(payload_bytes)

print(f"\nDecoded message: {message!r}")
print(f"CRC-8 received={received_crc:#04x} computed={computed_crc:#04x} "
      f"-> {'OK ✅' if received_crc == computed_crc else 'MISMATCH ❌'}")

# ---- Spectrum plots (same as v1) ----
target_freq = CENTER_FREQ + TONE_FREQ_OFFSET

Pxx, freqs = mlab.psd(samples, NFFT=SPECTRUM_NFFT, Fs=SAMPLE_RATE)
Pxx_db = 10 * np.log10(Pxx)
abs_freq_mhz = (CENTER_FREQ + freqs) / 1e6
zoom_mask = np.abs((CENTER_FREQ + freqs) - target_freq) <= SPECTRUM_ZOOM_HALF_SPAN_HZ
zoom_freqs_mhz = abs_freq_mhz[zoom_mask]
zoom_power_db = Pxx_db[zoom_mask]

# ---- Plot: full spectrum, correlation output around the peak, and the
#      decoded frame's envelope with field boundaries marked ----
t_ms = np.arange(len(envelope)) / SAMPLE_RATE * 1e3

fig, axes = plt.subplots(1, 3, figsize=(20, 5))

axes[0].plot(abs_freq_mhz, Pxx_db)
axes[0].axvline(target_freq / 1e6, color="r", linestyle="--", alpha=0.6)
axes[0].set_xlabel("Frequency (MHz)")
axes[0].set_ylabel("Power (dB)")
axes[0].set_title("Full captured spectrum")
axes[0].grid(True)

corr_t_ms = np.arange(len(correlation)) / SAMPLE_RATE * 1e3
corr_zoom_half_ms = 5
corr_mask = np.abs(corr_t_ms - sync_start / SAMPLE_RATE * 1e3) <= corr_zoom_half_ms
axes[1].plot(corr_t_ms[corr_mask], correlation[corr_mask])
axes[1].axvline(sync_start / SAMPLE_RATE * 1e3, color="r", linestyle="--",
                 alpha=0.6, label="Sync peak")
axes[1].set_xlabel("Time (ms)")
axes[1].set_ylabel("Correlation")
axes[1].set_title("Barker-13 sync correlation")
axes[1].legend()
axes[1].grid(True)

frame_start_ms = preamble_start / SAMPLE_RATE * 1e3
frame_end_ms = frame_end / SAMPLE_RATE * 1e3
frame_mask = (t_ms >= frame_start_ms) & (t_ms <= frame_end_ms)
axes[2].plot(t_ms[frame_mask], envelope[frame_mask], label="Envelope")
axes[2].axhline(threshold, color="r", linestyle="--", alpha=0.6, label="Threshold")
for label, sample_pos in [
    ("preamble", preamble_start), ("sync", sync_start),
    ("length", data_start), ("payload", payload_start),
    ("crc", crc_start), ("end", frame_end),
]:
    pos_ms = sample_pos / SAMPLE_RATE * 1e3
    axes[2].axvline(pos_ms, color="gray", linestyle=":", alpha=0.6)
    axes[2].text(pos_ms, axes[2].get_ylim()[1], label, rotation=90,
                 va="top", ha="right", fontsize=8, color="gray")
axes[2].set_xlabel("Time (ms)")
axes[2].set_ylabel("Amplitude")
axes[2].set_title(f"Decoded frame — message: {message!r}")
axes[2].legend()
axes[2].grid(True)

plt.tight_layout()
plt.show()
