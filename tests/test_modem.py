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


def test_stream_iter_matches_batch():
    # The incremental (streaming) modulator must produce the exact same waveform
    # as the one-shot modulate_stream over the same frames.
    from boxcar import modulate_stream_iter

    cfg = Config(fec=True)
    rng = np.random.default_rng(30)
    frames = ts_to_frames(rng.integers(0, 256, 188 * 7 * 4, dtype=np.uint8).tobytes(), 7)
    batch = modulate_stream(frames, cfg)
    incremental = np.concatenate(list(modulate_stream_iter(frames, cfg)))
    assert np.array_equal(batch, incremental)


def test_stream_iter_looped_decodes():
    # A looped frame source (broadcast) reassembles to the input repeated.
    from boxcar import modulate_stream_iter

    cfg = Config(fec=True)
    rng = np.random.default_rng(31)
    ts = rng.integers(0, 256, 188 * 7 * 3, dtype=np.uint8).tobytes()
    frames = ts_to_frames(ts, 7)
    looped = frames * 2
    tx = np.concatenate(list(modulate_stream_iter(looped, cfg)))
    rx = apply_channel(tx, cfg, es_n0_db=13.0, cfo_hz=1500.0, frac_delay=0.4, seed=31)
    got = receive_stream(rx, cfg)
    assert all(p is not None for p in got)
    assert frames_to_ts(got) == ts * 2


def test_soft_viterbi_roundtrip():
    # Soft decode of clean symbols must recover the exact info bits.
    from boxcar.fec import conv_encode, viterbi_decode_soft

    rng = np.random.default_rng(20)
    bits = rng.integers(0, 2, 1500).astype(np.uint8)
    coded = conv_encode(bits)
    # Map coded bits to ideal ±1 soft values (bit 0 -> +1, bit 1 -> -1).
    soft = 1.0 - 2.0 * coded
    assert np.array_equal(viterbi_decode_soft(soft), bits)


def test_soft_viterbi_beats_hard():
    # At a fixed noise level, soft decision should correct at least as many
    # frames as hard — and strictly more near the cliff.
    from boxcar.fec import conv_encode, viterbi_decode, viterbi_decode_soft

    rng = np.random.default_rng(21)
    hard_fail = soft_fail = 0
    for _ in range(60):
        bits = rng.integers(0, 2, 400).astype(np.uint8)
        coded = conv_encode(bits)
        tx = 1.0 - 2.0 * coded.astype(float)          # ±1
        rx = tx + rng.normal(0, 0.9, len(tx))          # heavy AWGN
        hard = viterbi_decode((rx < 0).astype(np.uint8))
        soft = viterbi_decode_soft(rx)
        hard_fail += not np.array_equal(hard, bits)
        soft_fail += not np.array_equal(soft, bits)
    assert soft_fail < hard_fail  # soft strictly wins deep in the noise


def test_interleaver_is_bijection():
    from boxcar.fec import interleaver_perm

    for n, depth in [(21164, 32), (1000, 16), (257, 7)]:
        perm = interleaver_perm(n, depth)
        assert len(perm) == n
        assert np.array_equal(np.sort(perm), np.arange(n))  # a true permutation


def test_interleaved_stream_byte_exact():
    # Interleave + soft decode must still be byte-exact through a clean-ish channel.
    rng = np.random.default_rng(22)
    ts = rng.integers(0, 256, 188 * 21, dtype=np.uint8).tobytes()
    frames = ts_to_frames(ts, 7)
    cfg = Config(fec=True, soft=True, interleave=True)
    rx = apply_channel(modulate_stream(frames, cfg), cfg,
                       es_n0_db=12.0, cfo_hz=1500.0, frac_delay=0.4, seed=22)
    got = receive_stream(rx, cfg)
    assert all(p is not None for p in got)
    assert frames_to_ts(got) == ts


def test_interleave_survives_bursts():
    # A burst of consecutive coded-bit errors overwhelms the Viterbi decoder
    # locally, but interleaving scatters that burst into isolated errors it can
    # fix. Tested at the codeword level so it's about the code, not acquisition
    # (a burst that erases a preamble loses the frame no matter what).
    from boxcar.fec import conv_encode, interleaver_perm, viterbi_decode

    rng = np.random.default_rng(23)
    bits = rng.integers(0, 2, 600).astype(np.uint8)
    coded = conv_encode(bits)
    perm = interleaver_perm(len(coded), 32)
    burst = slice(100, 140)  # 40 consecutive on-air bit errors

    plain = coded.copy()
    plain[burst] ^= 1
    assert not np.array_equal(viterbi_decode(plain), bits)  # burst kills it

    woven = coded[perm].copy()
    woven[burst] ^= 1
    deint = np.empty_like(woven)
    deint[perm] = woven
    assert np.array_equal(viterbi_decode(deint), bits)  # interleaving saves it


def test_sdr_format_roundtrip():
    # The 8-bit CU8/CS8 converters must preserve IQ shape and survive a round-trip.
    from boxcar.sdr_io import from_cs8, from_cu8, to_cs8, to_cu8

    rng = np.random.default_rng(11)
    iq = (rng.standard_normal(1000) + 1j * rng.standard_normal(1000)).astype(np.complex128)
    for to, back in ((to_cu8, from_cu8), (to_cs8, from_cs8)):
        b = to(iq)
        assert len(b) == len(iq) * 2                      # interleaved I,Q bytes
        r = back(b.tobytes())
        # Amplitude-blind receiver: absolute scale is irrelevant, but the
        # constellation must survive 8-bit quantization near-perfectly.
        corr = np.abs(np.vdot(r, iq)) / (np.linalg.norm(r) * np.linalg.norm(iq))
        assert corr > 0.999


def test_decode_through_cu8_quantization():
    # Full stream decode through the exact 8-bit format the RTL-SDR delivers.
    from boxcar.sdr_io import from_cu8, to_cu8

    rng = np.random.default_rng(12)
    ts = rng.integers(0, 256, 188 * 28, dtype=np.uint8).tobytes()
    frames = ts_to_frames(ts, 7)
    cfg = Config(fec=True)
    rx_float = apply_channel(modulate_stream(frames, cfg), cfg,
                             es_n0_db=12.0, cfo_hz=1500.0, frac_delay=0.4, seed=12)
    rx_back = from_cu8(to_cu8(rx_float).tobytes())        # through 8-bit ADC
    got = receive_stream(rx_back, cfg)
    assert all(p is not None for p in got)
    assert frames_to_ts(got) == ts                        # byte-exact after quantization


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
