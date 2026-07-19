"""Regression tests for the BOXCAR modem. Run: python tests/test_modem.py

Also works under pytest if installed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from boxcar import (
    Config,
    apply_channel,
    frames_to_ts,
    modulate,
    modulate_stream,
    receive,
    receive_stream,
    ts_to_frames,
)


def test_byte_exact_clean():
    cfg = Config()
    payload = b"HOBOCAST rides the rails." * 40
    rx = apply_channel(modulate(payload, cfg), cfg, es_n0_db=20.0, seed=1)
    assert receive(rx, cfg) == payload


def test_recovers_with_impairments():
    cfg = Config()
    payload = bytes(range(256)) * 8
    rx = apply_channel(
        modulate(payload, cfg), cfg, es_n0_db=14.0, cfo_hz=2000.0, frac_delay=0.5, seed=3
    )
    assert receive(rx, cfg) == payload


def test_crc_rejects_noise():
    cfg = Config()
    # Pure noise must not parse as a valid frame.
    rng = np.random.default_rng(0)
    noise = (rng.standard_normal(50000) + 1j * rng.standard_normal(50000)) * 0.1
    assert receive(noise, cfg) is None


def test_binary_payload_roundtrip():
    cfg = Config()
    rng = np.random.default_rng(2)
    payload = rng.integers(0, 256, size=5000, dtype=np.uint8).tobytes()
    rx = apply_channel(modulate(payload, cfg), cfg, es_n0_db=16.0, cfo_hz=-900.0,
                       frac_delay=0.2, seed=5)
    assert receive(rx, cfg) == payload


def test_stream_multiframe():
    # A chunked "transport stream" of many frames must reassemble byte-exact.
    cfg = Config()
    rng = np.random.default_rng(9)
    ts = rng.integers(0, 256, size=188 * 60, dtype=np.uint8).tobytes()
    frames = ts_to_frames(ts, packets_per_frame=7)
    tx = modulate_stream(frames, cfg)
    rx = apply_channel(tx, cfg, es_n0_db=18.0, cfo_hz=1500.0, frac_delay=0.4, seed=9)
    got = receive_stream(rx, cfg)
    assert len(got) == len(frames)
    assert all(p is not None for p in got)
    assert frames_to_ts(got) == ts


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError:
            failed += 1
            print(f"  FAIL  {t.__name__}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
