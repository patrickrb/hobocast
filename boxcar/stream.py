"""Streaming layer: an MPEG-TS becomes a train of self-contained BOXCAR frames.

Real transport streams are 188-byte packets. We group a handful per frame, give
each its own preamble + CRC, and modulate them into one continuous IQ burst-train.
The receiver walks the stream, re-acquiring and decoding frame by frame, so a lost
frame is a localized glitch rather than a stream-ending catastrophe — exactly how
you'd want digital TV to degrade.
"""

import numpy as np

from .modem import (
    Config,
    _acquire,
    _demod_data,
    _peek_length,
    _qpsk_to_bits,
    frame_data_symbols,
    modulate,
    parse_frame,
    rrc_taps,
)

TS_PACKET = 188


def ts_to_frames(ts: bytes, packets_per_frame: int = 7) -> list[bytes]:
    """Split a transport stream into per-frame payloads (last frame may be short)."""
    step = TS_PACKET * packets_per_frame
    return [ts[i : i + step] for i in range(0, len(ts), step)]


def frames_to_ts(frames: list[bytes]) -> bytes:
    return b"".join(frames)


def modulate_stream(payloads: list[bytes], cfg: Config = Config(), gap_syms: int = 32) -> np.ndarray:
    """Modulate payloads into one IQ burst-train, separated by short quiet gaps."""
    if not payloads:
        return np.zeros(0, dtype=complex)
    gap = np.zeros(gap_syms * cfg.sps, dtype=complex)
    parts: list[np.ndarray] = []
    for i, p in enumerate(payloads):
        if i:
            parts.append(gap)
        parts.append(modulate(p, cfg))
    return np.concatenate(parts)


def receive_stream(
    rx: np.ndarray,
    cfg: Config = Config(),
    search: int = 4096,
    min_ratio: float = 4.0,
    max_frames: int = 1_000_000,
) -> list:
    """Walk the burst-train and decode frames in order.

    Returns a list of payloads; a frame that fails its CRC is returned as None so
    the caller can see (and count) the gap in the stream.
    """
    taps = rrc_taps(cfg.beta, cfg.sps, cfg.span)
    mf = np.convolve(rx, taps)
    P, sps = cfg.preamble_len, cfg.sps
    min_frame = (P + frame_data_symbols(0)) * sps

    payloads: list = []
    start = 0
    while start < len(mf) - min_frame and len(payloads) < max_frames:
        acq = _acquire(mf, cfg, start, search)
        if acq is None:
            break
        kf, phi0, omega, ratio = acq
        if ratio < min_ratio:
            break  # only noise ahead — end of stream
        length = _peek_length(mf, kf, phi0, omega, cfg)
        if length < 0 or length > 10_000_000:
            start = int(kf + P * sps) + 1  # implausible; step past this peak
            continue
        d_syms = frame_data_symbols(length)
        out = _demod_data(mf, kf, phi0, omega, d_syms, cfg)
        payloads.append(parse_frame(_qpsk_to_bits(out)))
        start = int(kf + (P + d_syms) * sps)
    return payloads
