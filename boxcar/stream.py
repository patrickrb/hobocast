"""Streaming layer: an MPEG-TS becomes a train of self-contained BOXCAR frames.

Real transport streams are 188-byte packets. We group a handful per frame, give
each its own preamble + CRC, and modulate them into one continuous IQ burst-train.
The receiver walks the stream, re-acquiring and decoding frame by frame, so a lost
frame is a localized glitch rather than a stream-ending catastrophe — exactly how
you'd want digital TV to degrade.

Two framing modes:
  * uncoded (cfg.fec=False): variable-length frames, length carried in a header
    the receiver peeks before decoding the body.
  * coded (cfg.fec=True): fixed-size frames protected end-to-end by the rate-1/2
    convolutional code, so the symbol count is constant and no peek is needed.
"""

import zlib

import numpy as np

from .fec import conv_encode, interleaver_perm, viterbi_decode, viterbi_decode_soft
from .modem import (
    Config,
    _acquire,
    _bits_to_bytes,
    _bits_to_qpsk,
    _bytes_to_bits,
    _demod_data,
    _peek_length,
    _qpsk_to_bits,
    frame_data_symbols,
    modulate,
    modulate_symbols,
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


# --- coded (FEC) fixed-frame helpers --------------------------------------

def _coded_symbols(size: int) -> int:
    """Data symbols in a coded frame carrying a `size`-byte fixed payload."""
    info_bits = (2 + size + 4) * 8  # len(2) + padded payload + crc(4)
    return info_bits + 6            # +TAIL bits, then /2 for QPSK -> +TAIL symbols


def _build_coded_frame_syms(payload: bytes, size: int, cfg: Config = Config()) -> np.ndarray:
    if len(payload) > size:
        raise ValueError("payload larger than fixed frame size")
    body = len(payload).to_bytes(2, "big") + payload + bytes(size - len(payload))
    crc = zlib.crc32(body).to_bytes(4, "big")
    bits = conv_encode(_bytes_to_bits(body + crc))
    if cfg.interleave:
        bits = bits[interleaver_perm(len(bits), cfg.interleave_depth)]
    return _bits_to_qpsk(bits)


def _decode_coded_symbols(out: np.ndarray, cfg: Config) -> np.ndarray:
    """Turn carrier-corrected QPSK symbols back into info bits (soft/hard, de-interleaved)."""
    coded_syms = _coded_symbols(cfg.fec_payload)
    if len(out) < coded_syms:  # pad a short final frame so the geometry is fixed
        out = np.concatenate([out, np.zeros(coded_syms - len(out), dtype=complex)])
    if cfg.soft:
        soft = np.empty(2 * len(out))
        soft[0::2] = out.real
        soft[1::2] = out.imag
        if cfg.interleave:
            perm = interleaver_perm(len(soft), cfg.interleave_depth)
            deint = np.empty_like(soft)
            deint[perm] = soft
            soft = deint
        return viterbi_decode_soft(soft)
    bits = _qpsk_to_bits(out)
    if cfg.interleave:
        perm = interleaver_perm(len(bits), cfg.interleave_depth)
        deint = np.empty_like(bits)
        deint[perm] = bits
        bits = deint
    return viterbi_decode(bits)


def _parse_coded_frame(uncoded_bits: np.ndarray, size: int):
    data = _bits_to_bytes(uncoded_bits)
    if len(data) < 2 + size + 4:
        return None
    length = int.from_bytes(data[:2], "big")
    if length > size:
        return None
    body = data[: 2 + size]
    crc_rx = int.from_bytes(data[2 + size : 2 + size + 4], "big")
    if zlib.crc32(body) != crc_rx:
        return None
    return data[2 : 2 + length]


# --- transmit --------------------------------------------------------------

def modulate_stream(payloads: list[bytes], cfg: Config = Config(), gap_syms: int = 32) -> np.ndarray:
    """Modulate payloads into one IQ burst-train, separated by short quiet gaps."""
    if not payloads:
        return np.zeros(0, dtype=complex)
    gap = np.zeros(gap_syms * cfg.sps, dtype=complex)
    parts: list[np.ndarray] = []
    for i, p in enumerate(payloads):
        if i:
            parts.append(gap)
        if cfg.fec:
            parts.append(modulate_symbols(_build_coded_frame_syms(p, cfg.fec_payload, cfg), cfg))
        else:
            parts.append(modulate(p, cfg))
    return np.concatenate(parts)


# --- receive ---------------------------------------------------------------

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
    coded_syms = _coded_symbols(cfg.fec_payload) if cfg.fec else 0
    min_frame = (P + (coded_syms if cfg.fec else frame_data_symbols(0))) * sps

    payloads: list = []
    start = 0
    while start < len(mf) - min_frame and len(payloads) < max_frames:
        acq = _acquire(mf, cfg, start, search)
        if acq is None:
            break
        kf, phi0, omega, ratio = acq
        if ratio < min_ratio:
            break  # only noise ahead — end of stream

        if cfg.fec:
            out = _demod_data(mf, kf, phi0, omega, coded_syms, cfg)
            info = _decode_coded_symbols(out, cfg)
            payloads.append(_parse_coded_frame(info, cfg.fec_payload))
            start = int(kf + (P + coded_syms) * sps)
        else:
            length = _peek_length(mf, kf, phi0, omega, cfg)
            if length < 0 or length > 10_000_000:
                start = int(kf + P * sps) + 1  # implausible; step past this peak
                continue
            d_syms = frame_data_symbols(length)
            out = _demod_data(mf, kf, phi0, omega, d_syms, cfg)
            payloads.append(parse_frame(_qpsk_to_bits(out)))
            start = int(kf + (P + d_syms) * sps)
    return payloads
