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


def test_fec_codec_roundtrip():
    from boxcar.fec import conv_encode, viterbi_decode

    rng = np.random.default_rng(4)
    bits = rng.integers(0, 2, 2000).astype(np.uint8)
    coded = conv_encode(bits)
    assert len(coded) == (len(bits) + 6) * 2  # rate-1/2 + tail
    assert np.array_equal(viterbi_decode(coded), bits)  # clean roundtrip


def test_fec_corrects_errors():
    from boxcar.fec import conv_encode, viterbi_decode

    rng = np.random.default_rng(5)
    bits = rng.integers(0, 2, 1000).astype(np.uint8)
    coded = conv_encode(bits).copy()
    coded[rng.random(len(coded)) < 0.03] ^= 1  # 3% channel errors
    assert np.array_equal(viterbi_decode(coded), bits)  # fully corrected


def test_fec_stream_beats_uncoded():
    # At a harsh SNR, coded frames survive where uncoded ones don't.
    rng = np.random.default_rng(6)
    ts = rng.integers(0, 256, 188 * 21, dtype=np.uint8).tobytes()
    frames = ts_to_frames(ts, 7)

    cfg_u = Config(fec=False)
    rx_u = apply_channel(modulate_stream(frames, cfg_u), cfg_u,
                         es_n0_db=9.0, cfo_hz=1500.0, frac_delay=0.4, seed=1)
    got_u = [p for p in receive_stream(rx_u, cfg_u) if p is not None]

    cfg_c = Config(fec=True)
    rx_c = apply_channel(modulate_stream(frames, cfg_c), cfg_c,
                         es_n0_db=9.0, cfo_hz=1500.0, frac_delay=0.4, seed=1)
    got_c = receive_stream(rx_c, cfg_c)

    assert all(p is not None for p in got_c)          # FEC recovers all frames
    assert frames_to_ts(got_c) == ts                  # byte-exact
    assert len(got_c) > len(got_u)                    # and beats uncoded


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
