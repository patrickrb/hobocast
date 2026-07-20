"""sps=4 vs sps=2: is doubling the bitrate worth the robustness cost?

sps (samples/symbol) sets the symbol rate = fs/sps, so halving it from 4 to 2
doubles the payload bitrate (1.2 -> 2.4 Mbit/s) — better video — but packs the
symbols tighter, which usually costs some noise/timing margin. This measures the
actual tradeoff so the shipping profile is a data decision, not a guess.

Run:  python demos/profile_sweep.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np

from boxcar import Config, apply_channel, frames_to_ts, modulate_stream, receive_stream, ts_to_frames


def recovered(sps: int, es_n0_db: float, ts: bytes, frames, cfo=1500.0, frac=0.4,
              seed=1, cfo_search=0.0) -> int:
    cfg = Config(fec=True, soft=True, sps=sps, cfo_search_hz=cfo_search)
    tx = modulate_stream(frames, cfg)
    rx = apply_channel(tx, cfg, es_n0_db=es_n0_db, cfo_hz=cfo, frac_delay=frac, seed=seed)
    got = receive_stream(rx, cfg)
    return sum(1 for p in got if p is not None)


def main() -> int:
    rng = np.random.default_rng(0)
    ts = rng.integers(0, 256, 188 * 7 * 10, dtype=np.uint8).tobytes()  # 10 frames
    frames = ts_to_frames(ts, 7)
    total = len(frames)

    print("BOXCAR profile sweep — frames recovered / %d\n" % total)
    print("  bitrate:  sps=4 -> 1.2 Mbit/s   |   sps=2 -> 2.4 Mbit/s (2x)\n")

    print("  (1) noise margin (CFO=+1500 Hz, 0.4-sample timing):")
    print("      Es/N0 | sps=4 | sps=2")
    print("      ------+-------+------")
    for snr in [5.0, 6.0, 7.0, 8.0, 10.0]:
        a = recovered(4, snr, ts, frames)
        b = recovered(2, snr, ts, frames)
        print(f"      {snr:4.1f}  |  {a:3d}  |  {b:3d}")

    print("\n  (2) carrier-offset tolerance (Es/N0=12 dB, 0.4-sample timing):")
    print("      CFO Hz | sps=4 | sps=2")
    print("      -------+-------+------")
    for cfo in [1000, 3000, 6000, 10000, 15000]:
        a = recovered(4, 12.0, ts, frames, cfo=cfo)
        b = recovered(2, 12.0, ts, frames, cfo=cfo)
        print(f"      {cfo:5d}  |  {a:3d}  |  {b:3d}")

    print("\n  Read-off: sps=2 buys 2x video bitrate; the columns above show what,")
    print("  if anything, it costs in noise/carrier margin on this channel model.")

    print("\n  (3) coarse carrier search rescues real-tuner offsets (sps=4, 12 dB):")
    print("      CFO Hz | no search | search ±30 kHz")
    print("      -------+-----------+---------------")
    for cfo in [6000, 15000, 27000]:  # 27 kHz ~= 30 ppm at 906 MHz
        off = recovered(4, 12.0, ts, frames, cfo=cfo)
        on = recovered(4, 12.0, ts, frames, cfo=cfo, cfo_search=30000.0)
        print(f"      {cfo:5d}  |    {off:3d}    |      {on:3d}")
    print("\n  -> without the search a real tuner never locks; with it, it does.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
