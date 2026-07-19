"""Headline demo: push a COLOR image through the BOXCAR radio channel, byte-exact.

    color bars (PPM) -> QPSK/RRC modulate -> [fractional delay + CFO + AWGN]
                     -> data-aided receive -> CRC-checked payload

No hardware involved — the "channel" is boxcar.channel. If this recovers the
image bit-for-bit, the same waveform will carry an H.264+AAC MPEG-TS of color
video and audio to a $30 RTL-SDR. Color and sound become "just bytes."

Run:  python demos/loopback.py
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from boxcar import Config, apply_channel, modulate, receive
from tools.testpattern import color_bars

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")


def main() -> int:
    cfg = Config()
    payload = color_bars(160, 100)

    print("BOXCAR loopback — color image over a simulated RTL-SDR channel\n")
    print(f"  waveform    : QPSK, {cfg.rsym/1e3:.0f} ksym/s, RRC beta={cfg.beta}, "
          f"fits in fs={cfg.fs/1e6:.1f} MHz")
    print(f"  raw bitrate : {cfg.bitrate/1e6:.2f} Mbit/s (uncoded)")
    print(f"  payload     : {len(payload)} bytes (160x100 color PPM)")

    tx = modulate(payload, cfg)
    print(f"  tx IQ       : {len(tx)} samples "
          f"(~{len(tx)/cfg.fs*1e3:.1f} ms on air)\n")

    # A deliberately unkind capture: tuner off-frequency, random timing phase, noise.
    es_n0_db = 15.0
    rx = apply_channel(tx, cfg, es_n0_db=es_n0_db, cfo_hz=1800.0, frac_delay=0.37, seed=7)
    print(f"  channel     : Es/N0={es_n0_db} dB, CFO=+1800 Hz, timing offset=0.37 sample")

    recovered = receive(rx, cfg)

    if recovered is None:
        print("\n  RESULT      : ✗ CRC failed — frame not recovered")
        return 1

    exact = recovered == payload
    print(f"  RESULT      : {'✓ byte-exact' if exact else '✗ mismatch'} "
          f"({len(recovered)} bytes, CRC valid)")
    if not exact:
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    ppm_path = os.path.join(OUT_DIR, "recovered.ppm")
    with open(ppm_path, "wb") as f:
        f.write(recovered)
    print(f"\n  wrote       : {ppm_path}")

    # Best-effort convenience conversion to PNG for easy viewing.
    png_path = os.path.join(OUT_DIR, "recovered.png")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", ppm_path, png_path],
            check=True,
        )
        print(f"  wrote       : {png_path}")
    except Exception:
        pass

    print("\n  Color pixels crossed the channel intact. That's the whole thesis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
