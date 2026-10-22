"""
ADALM-Pluto TX script v2 — Framed OOK text message.

Sends a real message (not just a raw bit pattern) as a self-synchronizing
OOK frame:

    [ 16-bit alternating preamble ] [ 13-bit Barker sync word ]
    [ 8-bit length ] [ payload: 8 bits/char ] [ 8-bit CRC-8 ] [ 16-bit guard ]

- The preamble lets the RX lock bit timing and estimate high/low
  amplitude levels.
- The Barker-13 sync word has a sharp autocorrelation peak, so the RX can
  find the exact frame start via cross-correlation instead of guessing an
  offset (this is what fixes the "shifted samples" / bit-phase-ambiguity
  problem you'd get with a plain alternating test pattern).
- The length + CRC-8 let the RX know how many payload bytes to expect and
  verify the message wasn't corrupted.
- The guard (all zeros) gives a clean gap between repeats of the cyclic
  buffer, so nothing from the tail of one repeat bleeds into the next
  frame's preamble.

Requires: pip install pyadi-iio numpy
"""

import time
import numpy as np
import adi

# ---- Configuration (matches pluto_tx_ook.py / rtl_rx_ook_v2.py) ----
PLUTO_URI = "ip:192.168.2.22"
CENTER_FREQ = int(915e6)
SAMPLE_RATE = int(2e6)
TONE_FREQ = 200e3
TX_GAIN = -20

BIT_RATE = 10e3
RAMP_FRACTION = 0.1

# ---- Message ----
MESSAGE = "HELLO WORLD MANDRIAUM"    # <-- change this to whatever you want to send

# ---- Frame structure ----
PREAMBLE_BITS = "10" * 8                 # 16 bits, alternating
SYNC_BITS = "1111100110101"              # Barker-13
GUARD_BITS = "0" * 16                    # silence between repeats

SAMPLES_PER_BIT = int(round(SAMPLE_RATE / BIT_RATE))
AMPLITUDE = 2**14


def crc8(data_bytes, poly=0x07, init=0x00):
    """Standard bitwise CRC-8 (poly 0x07, the same one used in CRC-8-CCITT)."""
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
        raise ValueError("Message too long for an 8-bit length field (max 255 bytes).")

    length_bits = format(len(payload_bytes), "08b")
    payload_bits = "".join(format(b, "08b") for b in payload_bytes)
    crc_bits = format(crc8(payload_bytes), "08b")

    frame = PREAMBLE_BITS + SYNC_BITS + length_bits + payload_bits + crc_bits + GUARD_BITS
    return frame, payload_bytes


def build_ook_envelope(bits, samples_per_bit, ramp_fraction):
    """Amplitude envelope (0..1) for a bit string, with raised-cosine
    ramps on transitions (see pluto_tx_ook.py for details)."""
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


# ---- Build the frame ----
FRAME_BITS, payload_bytes = build_frame_bits(MESSAGE)

print(f"Message: {MESSAGE!r} ({len(payload_bytes)} bytes)")
print(f"Frame layout: preamble={len(PREAMBLE_BITS)} bits, sync={len(SYNC_BITS)} bits, "
      f"length=8 bits, payload={len(payload_bytes)*8} bits, crc=8 bits, "
      f"guard={len(GUARD_BITS)} bits")
print(f"Total frame: {len(FRAME_BITS)} bits "
      f"(~{len(FRAME_BITS)/BIT_RATE*1e3:.2f} ms per loop)")
print(f"CRC-8: {crc8(payload_bytes):#04x}")

# ---- Connect ----
sdr = adi.Pluto(PLUTO_URI)
sdr.sample_rate = SAMPLE_RATE
sdr.tx_rf_bandwidth = SAMPLE_RATE
sdr.tx_lo = CENTER_FREQ
sdr.tx_hardwaregain_chan0 = TX_GAIN
sdr.tx_cyclic_buffer = True

envelope = build_ook_envelope(FRAME_BITS, SAMPLES_PER_BIT, RAMP_FRACTION)
N = len(envelope)
ts = 1 / sdr.sample_rate
t = np.arange(N) * ts

carrier = np.exp(1j * 2 * np.pi * TONE_FREQ * t)
iq_samples = AMPLITUDE * envelope * carrier

print(f"\nTransmitting at {CENTER_FREQ/1e6:.3f} MHz + {TONE_FREQ/1e3:.0f} kHz "
      f"(i.e. {(CENTER_FREQ+TONE_FREQ)/1e6:.3f} MHz), gain={TX_GAIN} dB")
print("Press Ctrl+C to stop.")

sdr.tx(iq_samples)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping transmission...")
    sdr.tx_destroy_buffer()
