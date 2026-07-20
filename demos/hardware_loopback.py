"""M4 (software half): the full chain through REAL SDR byte formats.

    ffmpeg TS -> BOXCAR modulate (+FEC) -> float IQ -> [channel] -> CU8 bytes
      -> (this is exactly what `rtl_sdr` writes / the RTL2832U delivers)
      -> BOXCAR receive -> reassembled MPEG-TS

The only thing this demo simulates is the air (boxcar.channel). Everything else —
including the 8-bit CU8 quantization the dongle's ADC imposes — is the real path.
If it survives that, the remaining step to over-the-air is literally piping to
`rtl_sdr` / `hackrf_transfer` (commands printed at the end).

Run:  python demos/hardware_loopback.py
"""

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np

from boxcar import Config, apply_channel, frames_to_ts, modulate_stream, receive_stream, ts_to_frames
from boxcar.sdr_io import from_cu8, to_cu8

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")


def source_ts() -> bytes:
    """A real H.264+AAC transport stream if ffmpeg is around, else random bytes."""
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(OUT, "source.ts")
    if os.path.exists(src):
        return open(src, "rb").read()
    if shutil.which("ffmpeg"):
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-profile:v", "baseline", "-preset", "veryfast",
            "-b:v", "500k", "-pix_fmt", "yuv420p", "-g", "15",
            "-c:a", "aac", "-b:a", "64k", "-f", "mpegts", src,
        ], check=True, capture_output=True)
        return open(src, "rb").read()
    return np.random.default_rng(0).integers(0, 256, 188 * 200, dtype=np.uint8).tobytes()


def main() -> int:
    cfg = Config(fec=True)  # ship with error correction on
    ts = source_ts()
    frames = ts_to_frames(ts, 7)

    print("BOXCAR M4 (software half) — full chain through the real RTL-SDR CU8 format\n")
    print(f"  source TS   : {len(ts)} bytes -> {len(frames)} frames (FEC on)")

    tx = modulate_stream(frames, cfg)
    es_n0_db = 12.0
    rx_float = apply_channel(tx, cfg, es_n0_db=es_n0_db, cfo_hz=1500.0, frac_delay=0.4, seed=4)

    # Quantize to the exact bytes the dongle produces, write the .cu8, read it back.
    cu8 = to_cu8(rx_float)
    cap = os.path.join(OUT, "capture.cu8")
    cu8.tofile(cap)
    print(f"  channel     : Es/N0={es_n0_db} dB, CFO=+1500 Hz, timing offset=0.4 sample")
    print(f"  CU8 capture : {len(cu8)} bytes -> {cap}  (8-bit ADC, real dongle format)")

    rx_back = from_cu8(open(cap, "rb").read())
    got = receive_stream(rx_back, cfg)
    good = [p for p in got if p is not None]
    recovered = frames_to_ts([p if p is not None else b"" for p in got])
    exact = recovered == ts

    print(f"  decoded     : {len(good)}/{len(frames)} frames "
          f"({len(got) - len(good)} CRC drops)")
    print(f"  RESULT      : {'✓ byte-exact' if exact else '~ recovered with drops'} "
          f"through 8-bit quantization ({len(recovered)} bytes)\n")

    print("  To go over the air, the simulated channel becomes real hardware:")
    print(f"    TX:  python -m boxcar.cli tx {os.path.join('out','source.ts')} "
          f"out/tx.cs8 --fmt cs8 --fec")
    print(f"         hackrf_transfer -t out/tx.cs8 -f 906000000 -s {int(cfg.fs)} -a 1 -x 20")
    print(f"    RX:  rtl_sdr -f 906000000 -s {int(cfg.fs)} -g 40 out/capture.cu8")
    print(f"         python -m boxcar.cli rx out/capture.cu8 out/rx.ts --fmt cu8 --fec")
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
