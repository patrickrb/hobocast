"""How much do soft-decision + interleaving actually buy?

Two independent wins, measured against the same channel:

  1. Soft-decision Viterbi — feed the decoder the received amplitudes instead of
     hard 0/1 slices. Pure RX change (same waveform), ~2 dB of coding gain.
  2. Interleaving — permute coded bits so a burst on the air becomes isolated
     errors the convolutional code can fix. Changes the waveform (TX+RX agree).

Run:  python demos/robustness_demo.py
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


def frames_recovered(cfg: Config, ts: bytes, frames, es_n0_db: float,
                     bursts: int = 0, seed: int = 7) -> int:
    tx = modulate_stream(frames, cfg)
    rx = apply_channel(tx, cfg, es_n0_db=es_n0_db, cfo_hz=1500.0, frac_delay=0.4, seed=seed)
    if bursts:
        r = np.random.default_rng(seed + 1)
        n = len(rx)
        for _ in range(bursts):
            s = int(r.integers(0, max(1, n - 500)))
            rx[s:s + 300] *= 0.03  # deep fade
    got = receive_stream(rx, cfg)
    return sum(1 for p in got if p is not None)


def main() -> int:
    rng = np.random.default_rng(0)
    ts = rng.integers(0, 256, 188 * 7 * 30, dtype=np.uint8).tobytes()  # 30 frames
    frames = ts_to_frames(ts, 7)
    total = len(frames)

    print("BOXCAR robustness — frames recovered / %d, same channel each row\n" % total)

    # --- 1. Soft vs hard across the AWGN cliff -----------------------------
    print("  (1) hard vs soft-decision Viterbi, AWGN only:")
    print("      Es/N0 |  hard  |  soft")
    print("      ------+--------+------")
    for snr in [4.0, 4.5, 5.0, 5.5, 6.0]:
        hard = frames_recovered(Config(fec=True, soft=False), ts, frames, snr)
        soft = frames_recovered(Config(fec=True, soft=True), ts, frames, snr)
        print(f"      {snr:4.1f}  |  {hard:3d}   |  {soft:3d}")

    # --- 2. Interleaving vs a burst, at the codeword level -----------------
    # This is where interleaving actually operates: a run of consecutive bad
    # bits (a deep fade) overwhelms the decoder locally, but interleaving
    # scatters it into isolated errors it fixes. (At the whole-stream level a
    # long fade tends to erase a preamble instead, losing the frame to
    # acquisition regardless — a different problem, for pilots/re-sync.)
    from boxcar.fec import conv_encode, interleaver_perm, viterbi_decode

    info = np.random.default_rng(1).integers(0, 2, 1200).astype(np.uint8)
    coded = conv_encode(info)
    perm = interleaver_perm(len(coded), 32)
    print("\n  (2) burst of consecutive coded-bit errors, does it still decode?")
    print("      burst | plain | woven")
    print("      ------+-------+------")
    for blen in [8, 16, 24, 40, 64]:
        b = slice(200, 200 + blen)
        plain = coded.copy(); plain[b] ^= 1
        ok_plain = np.array_equal(viterbi_decode(plain), info)
        woven = coded[perm].copy(); woven[b] ^= 1
        deint = np.empty_like(woven); deint[perm] = woven
        ok_woven = np.array_equal(viterbi_decode(deint), info)
        mark = lambda ok: " ok  " if ok else "fail "
        print(f"      {blen:4d}  | {mark(ok_plain)} | {mark(ok_woven)}")

    # --- 3. Everything on: still byte-exact when the link is good ----------
    cfg = Config(fec=True, soft=True, interleave=True)
    got = receive_stream(
        apply_channel(modulate_stream(frames, cfg), cfg, es_n0_db=13.0,
                      cfo_hz=1500.0, frac_delay=0.4, seed=3),
        cfg,
    )
    exact = all(p is not None for p in got) and frames_to_ts(got) == ts
    print(f"\n  (3) soft+interleave, 13 dB clean link: "
          f"{'✓ byte-exact' if exact else '~ lossy'} ({total}/{total} frames)")
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
