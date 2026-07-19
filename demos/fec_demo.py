"""M2 demo: forward error correction turns a dead link into a working one.

Rate-1/2 convolutional coding (K=7, Viterbi) costs half the raw bitrate but buys
several dB of coding gain. Below we send the same little "transport stream" of
frames through the same channel with FEC off vs on, and sweep the SNR. FEC
recovers whole frames at SNRs where the uncoded link recovers nothing.

Run:  python demos/fec_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np

from boxcar import (
    Config,
    apply_channel,
    frames_to_ts,
    modulate_stream,
    receive_stream,
    ts_to_frames,
)
from boxcar.fec import conv_encode, viterbi_decode


def frame_survival():
    rng = np.random.default_rng(3)
    ts = rng.integers(0, 256, 188 * 49, dtype=np.uint8).tobytes()  # 49 TS packets
    frames = ts_to_frames(ts, 7)

    print("Frame survival — same channel, FEC off vs on (7 frames sent):\n")
    print(f"  {'Es/N0':>7}   {'uncoded':>10}   {'FEC (1/2)':>10}")
    print(f"  {'-'*7}   {'-'*10}   {'-'*10}")
    for esn0 in [7.0, 8.0, 9.0, 10.0, 11.0, 13.0]:
        row = {}
        for fec in (False, True):
            cfg = Config(fec=fec)
            tx = modulate_stream(frames, cfg)
            rx = apply_channel(tx, cfg, es_n0_db=esn0, cfo_hz=1500.0,
                               frac_delay=0.4, seed=int(esn0) + fec)
            got = receive_stream(rx, cfg)
            row[fec] = sum(1 for p in got if p is not None)
        print(f"  {esn0:>5} dB   {row[False]:>7}/7   {row[True]:>7}/7")


def coding_gain():
    print("\nRaw coding gain — info-bit BER after Viterbi vs channel bit-error rate:\n")
    rng = np.random.default_rng(1)
    print(f"  {'channel BER':>12}   {'coded info BER':>15}")
    print(f"  {'-'*12}   {'-'*15}")
    for pct in [0.02, 0.04, 0.06, 0.08]:
        errs = total = 0
        for _ in range(40):
            b = rng.integers(0, 2, 1000).astype(np.uint8)
            c = conv_encode(b).copy()
            c[rng.random(len(c)) < pct] ^= 1
            errs += int(np.sum(viterbi_decode(c) != b))
            total += len(b)
        print(f"  {pct:>12.2f}   {errs / total:>15.2e}")


def main() -> int:
    print("BOXCAR M2 — forward error correction (rate-1/2 convolutional, Viterbi)\n")
    frame_survival()
    coding_gain()
    print("\n  FEC halves the bitrate but recovers frames several dB deeper into the "
          "noise\n  — the difference between a black screen and watchable TV at range.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
