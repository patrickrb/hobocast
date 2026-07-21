#!/usr/bin/env python3
"""Frequency-division-multiplex N BOXCAR channel .cs8 files into one wideband
composite .cs8 -- so a single HackRF transmits every channel at once and each
viewer's RTL-SDR just tunes to the channel it wants.

Each input is a 2.4 MSPS complex baseband (cs8 = interleaved signed 8-bit I/Q)
BOXCAR signal centered at DC. We upsample every channel to a common composite
rate (fs_in * up), shift each to its frequency slot with a complex exponential,
and sum. The result is transmitted at the band-center frequency; a channel given
offset f lands at center+f on the air.

  fdm_mux.py --out composite.cs8 ch1.cs8@-3750000 ch2.cs8@-2250000 ...

The expensive DSP (BOXCAR modulation) is already done per channel; this is only
resample + shift + sum, which is cheap enough to run offline in one pass.
"""
import argparse
import numpy as np
from scipy.signal import resample_poly


def cs8_len(path: str) -> int:
    """Sample count (I/Q pairs) without loading the file."""
    import os
    return os.path.getsize(path) // 2


def read_cs8(path: str) -> np.ndarray:
    raw = np.fromfile(path, dtype=np.int8).astype(np.float32)
    return raw[0::2] + 1j * raw[1::2]  # complex baseband


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fs-in", type=float, default=2_400_000, help="per-channel input rate")
    ap.add_argument("--up", type=int, default=5, help="composite rate = fs_in * up")
    ap.add_argument("--rms", type=float, default=34.0, help="target composite RMS (of 127)")
    ap.add_argument("--out", required=True)
    ap.add_argument("channels", nargs="+", help="path@offset_hz (offset relative to band center)")
    a = ap.parse_args()

    fs_out = a.fs_in * a.up
    specs = []
    for c in a.channels:
        path, off = c.rsplit("@", 1)
        specs.append((path, float(off)))

    # Common length: tile every channel up to the longest so the whole composite
    # loops as a unit. Shorter channels wrap internally (a brief blip the app's
    # stall-recovery already handles), and all channels wrap together at the end.
    L = max(cs8_len(p) for p, _ in specs)
    Lout = L * a.up
    print(f"composite: {len(specs)} channels  fs_out={fs_out/1e6:.1f} MSPS  "
          f"L={L} -> {Lout} samples  (~{Lout * 2 / 1e6:.0f} MB out)")

    acc = np.zeros(Lout, dtype=np.complex64)
    CHUNK = 8_000_000  # shift+accumulate in blocks so we never hold a full-length
                       # phasor array (keeps peak RAM ~ acc + one upsampled channel)
    for path, off in specs:
        x = read_cs8(path)
        if x.size < L:
            x = np.tile(x, int(np.ceil(L / x.size)))[:L]
        else:
            x = x[:L]
        xu = resample_poly(x, a.up, 1).astype(np.complex64)
        del x
        if xu.size < Lout:
            xu = np.concatenate([xu, np.zeros(Lout - xu.size, np.complex64)])
        else:
            xu = xu[:Lout]
        # Frequency shift into this channel's slot. Reduce phase mod 1 in float64
        # per block so precision holds across hundreds of millions of samples.
        for s in range(0, Lout, CHUNK):
            e = min(s + CHUNK, Lout)
            idx = np.arange(s, e, dtype=np.float64)
            phase = np.mod(off / fs_out * idx, 1.0)
            acc[s:e] += xu[s:e] * np.exp(2j * np.pi * phase).astype(np.complex64)
        print(f"  + {path}  @ {off/1e6:+.3f} MHz")
        del xu

    rms = float(np.sqrt(np.mean(np.abs(acc) ** 2)))
    scale = a.rms / rms
    acc *= scale
    peak = float(np.max(np.abs(acc)))
    clip = float(np.mean(np.abs(acc) > 127) * 100)
    print(f"normalize: rms={rms:.1f} -> {a.rms:.0f}  scale={scale:.3f}  "
          f"peak={peak:.0f}  clip={clip:.4f}%")

    inter = np.empty(Lout * 2, dtype=np.int8)
    inter[0::2] = np.clip(np.round(acc.real), -127, 127).astype(np.int8)
    inter[1::2] = np.clip(np.round(acc.imag), -127, 127).astype(np.int8)
    inter.tofile(a.out)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
