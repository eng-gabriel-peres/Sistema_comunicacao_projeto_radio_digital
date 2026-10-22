"""
ADALM-Pluto TX test script.
Transmits a continuous complex sinusoid (single tone) offset from the
carrier so it's easy to spot on the RX side, away from any DC spike.

Requires: pip install pyadi-iio
"""

import time
import numpy as np
import adi

# ---- Configuration ----
PLUTO_URI = "ip:192.168.2.22"   # default Pluto IP over USB; change if needed
CENTER_FREQ = int(915e6)       # 915 MHz carrier
SAMPLE_RATE = int(2e6)         # 2 MSPS
TONE_FREQ = 200e3              # offset tone: signal will appear at 915.1 MHz
TX_GAIN = -20                  # dB attenuation (0 = max power). Start low.

# ---- Connect ----
sdr = adi.Pluto(PLUTO_URI)
sdr.sample_rate = SAMPLE_RATE
sdr.tx_rf_bandwidth = SAMPLE_RATE
sdr.tx_lo = CENTER_FREQ
sdr.tx_hardwaregain_chan0 = TX_GAIN
sdr.tx_cyclic_buffer = True  # loop the buffer continuously

# ---- Build a single-tone complex baseband signal ----
N = 1024
ts = 1 / sdr.sample_rate
t = np.arange(N) * ts

# Amplitude scaled to Pluto's expected int16 range
amplitude = 2**14
i = amplitude * np.cos(2 * np.pi * TONE_FREQ * t)
q = amplitude * np.sin(2 * np.pi * TONE_FREQ * t)
iq_samples = i + 1j * q

print(f"Transmitting tone at {CENTER_FREQ/1e6:.3f} MHz + {TONE_FREQ/1e3:.0f} kHz "
      f"(i.e. {(CENTER_FREQ+TONE_FREQ)/1e6:.3f} MHz), gain={TX_GAIN} dB")
print("Press Ctrl+C to stop.")

sdr.tx(iq_samples)  # starts cyclic transmission

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping transmission...")
    sdr.tx_destroy_buffer()