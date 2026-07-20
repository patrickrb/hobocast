"""BOXCAR modem: framing, QPSK modulation, and a data-aided QPSK receiver.

Frame on the air:

    [ ZC preamble ][ len(4) | payload | crc32(4) ]  -> QPSK -> RRC -> IQ

The Zadoff-Chu preamble is a constant-modulus known sequence used for frame
detection, symbol timing, and carrier (phase + frequency) acquisition. After
acquisition a decision-directed PLL tracks residual carrier drift through the
payload so the frame can be arbitrarily long without the phase walking off.
"""

import zlib
from dataclasses import dataclass

import numpy as np

from .dsp import rrc_taps, upsample


@dataclass
class Config:
    fs: float = 2_400_000.0   # RTL-SDR capture rate (Hz) — the whole channel
    sps: int = 4              # samples/symbol -> symbol rate = fs/sps
    beta: float = 0.35        # RRC rolloff
    span: int = 8             # RRC length in symbols
    preamble_len: int = 64    # Zadoff-Chu preamble length (symbols)
    zc_root: int = 25         # ZC root (coprime with preamble_len)
    fec: bool = False         # rate-1/2 convolutional coding (see boxcar/fec.py)
    fec_payload: int = 1316   # fixed payload bytes per coded frame (7 TS packets)
    soft: bool = False        # soft-decision Viterbi (RX-only; ~2 dB gain)
    interleave: bool = False  # block-interleave coded bits (burst-error defence)
    interleave_depth: int = 32  # interleaver columns (spread) when interleave=True
    cfo_search_hz: float = 0.0  # coarse carrier search half-range; 0 = off (see _acquire)

    @property
    def rsym(self) -> float:
        return self.fs / self.sps

    @property
    def bitrate(self) -> float:
        return self.rsym * 2.0  # QPSK, uncoded


# --- known sequences -------------------------------------------------------

def zc_preamble(cfg: Config) -> np.ndarray:
    """Constant-modulus Zadoff-Chu sequence used as the acquisition preamble."""
    n = np.arange(cfg.preamble_len)
    return np.exp(-1j * np.pi * cfg.zc_root * n * n / cfg.preamble_len)


# --- bit/symbol plumbing ---------------------------------------------------

def _bytes_to_bits(b: bytes) -> np.ndarray:
    return np.unpackbits(np.frombuffer(b, dtype=np.uint8))


def _bits_to_bytes(bits: np.ndarray) -> bytes:
    return np.packbits(bits).tobytes()


def _bits_to_qpsk(bits: np.ndarray) -> np.ndarray:
    if len(bits) % 2:
        bits = np.append(bits, np.uint8(0))
    b0 = bits[0::2].astype(float)
    b1 = bits[1::2].astype(float)
    return ((1.0 - 2.0 * b0) + 1j * (1.0 - 2.0 * b1)) / np.sqrt(2.0)  # Gray QPSK


def _qpsk_to_bits(sym: np.ndarray) -> np.ndarray:
    bits = np.empty(len(sym) * 2, dtype=np.uint8)
    bits[0::2] = (sym.real < 0).astype(np.uint8)
    bits[1::2] = (sym.imag < 0).astype(np.uint8)
    return bits


# --- framing ---------------------------------------------------------------

def build_frame_bits(payload: bytes) -> np.ndarray:
    body = len(payload).to_bytes(4, "big") + payload
    crc = zlib.crc32(body).to_bytes(4, "big")
    return _bytes_to_bits(body + crc)


def parse_frame(bits: np.ndarray):
    """Recover the payload from demodulated bits, or None if the CRC fails."""
    data = _bits_to_bytes(bits[: (len(bits) // 8) * 8])
    if len(data) < 8:
        return None
    length = int.from_bytes(data[:4], "big")
    if length > len(data) - 8:
        return None
    body = data[: 4 + length]
    crc_rx = int.from_bytes(data[4 + length : 8 + length], "big")
    if zlib.crc32(body) != crc_rx:
        return None
    return data[4 : 4 + length]


# --- transmit --------------------------------------------------------------

def modulate_symbols(data_syms: np.ndarray, cfg: Config = Config()) -> np.ndarray:
    """Prepend the preamble and pulse-shape a block of data symbols into IQ."""
    syms = np.concatenate([zc_preamble(cfg), data_syms])
    taps = rrc_taps(cfg.beta, cfg.sps, cfg.span)
    return np.convolve(upsample(syms, cfg.sps), taps)


def modulate(payload: bytes, cfg: Config = Config()) -> np.ndarray:
    """Bytes -> complex baseband IQ ready to hand to an SDR (or the channel sim)."""
    return modulate_symbols(_bits_to_qpsk(build_frame_bits(payload)), cfg)


# --- receive ---------------------------------------------------------------

def _acquire(mf: np.ndarray, cfg: Config, start: int = 0, search: int | None = None):
    """Find the next preamble at/after `start`.

    Returns (kf, phi0, omega, ratio): fractional sample offset of preamble
    symbol 0, seed carrier phase, seed per-symbol frequency offset, and a
    detection ratio (peak / median correlation) used to tell a real frame from
    noise. Correlates the matched-filtered stream against the known preamble
    sampled at symbol spacing; a linear fit of the de-modulated preamble phase
    seeds the tracking loop.
    """
    P, sps = cfg.preamble_len, cfg.sps
    ref = np.conj(zc_preamble(cfg))
    idx = np.arange(P) * sps
    room = len(mf) - start - P * sps
    search = room if search is None else min(search, room)
    if search <= 0:
        return None
    if cfg.cfo_search_hz > 0:
        # Coarse carrier acquisition. A Zadoff-Chu correlation couples frequency
        # to time — an uncorrected offset *shifts* the peak, so the recovered
        # timing (and thus the phase fit) is wrong well before detection itself
        # fails. A real tuner's PPM error (~27 kHz at 906 MHz) lands squarely in
        # that zone. So we sweep trial frequencies: folding each into the
        # reference un-shifts the peak at the matching offset, and the strongest
        # peak across the sweep gives the correct timing. Bin spacing keeps the
        # coherent correlation from washing out between trials.
        df = 0.5 * cfg.fs / (P * sps)
        freqs = np.arange(-cfg.cfo_search_hz, cfg.cfo_search_hz + df / 2, df)
        mag = None
        best_peak = -1.0
        for f in freqs:
            ref_f = ref * np.exp(-1j * 2.0 * np.pi * f * idx / cfg.fs)
            m = np.empty(search)
            for k in range(search):
                m[k] = abs(np.dot(ref_f, mf[start + k + idx]))
            peak = m.max()
            if peak > best_peak:
                best_peak, mag = peak, m
    else:
        mag = np.empty(search)
        for k in range(search):
            mag[k] = abs(np.dot(ref, mf[start + k + idx]))
    k0 = int(np.argmax(mag))
    ratio = mag[k0] / (np.median(mag) + 1e-12)
    # Parabolic interpolation of the peak for sub-sample timing.
    delta = 0.0
    if 1 <= k0 < search - 1:
        ym1, y0, yp1 = mag[k0 - 1], mag[k0], mag[k0 + 1]
        denom = ym1 - 2.0 * y0 + yp1
        if denom != 0.0:
            delta = 0.5 * (ym1 - yp1) / denom
    kf = start + k0 + delta

    pre = _sample_symbols(mf, kf, P, sps) * np.conj(zc_preamble(cfg))
    ph = np.unwrap(np.angle(pre))
    A = np.vstack([np.ones(P), np.arange(P)]).T
    phi0, omega = np.linalg.lstsq(A, ph, rcond=None)[0]
    return kf, phi0, omega, ratio


def _sample_symbols(mf: np.ndarray, kf: float, count: int, sps: int) -> np.ndarray:
    pos = kf + np.arange(count) * sps
    xr = np.interp(pos, np.arange(len(mf)), mf.real)
    xi = np.interp(pos, np.arange(len(mf)), mf.imag)
    return xr + 1j * xi


def _demod_data(mf, kf, phi0, omega, n_syms, cfg):
    """Carrier-correct `n_syms` data symbols after the preamble via a DD-PLL.

    The decision-directed 2nd-order PLL is seeded from the preamble fit and
    tracks residual CFO through the payload, so long frames don't drift.
    """
    P, sps = cfg.preamble_len, cfg.sps
    avail = int((len(mf) - kf - 1) // sps) - P
    n_syms = min(n_syms, max(0, avail))
    if n_syms <= 0:
        return np.array([], dtype=complex)
    data = _sample_symbols(mf, kf + P * sps, n_syms, sps)
    phi = phi0 + omega * P
    freq = omega
    alpha, beta_pll = 0.05, 0.001
    out = np.empty(n_syms, dtype=complex)
    inv = np.sqrt(2.0)
    for i in range(n_syms):
        c = data[i] * np.exp(-1j * phi)
        out[i] = c
        d = (np.sign(c.real) + 1j * np.sign(c.imag)) / inv
        err = np.angle(c * np.conj(d)) if d != 0 else 0.0
        phi += freq + alpha * err
        freq += beta_pll * err
    return out


def _peek_length(mf, kf, phi0, omega, cfg) -> int:
    """Read the 4-byte length header (16 data symbols) using the preamble seed."""
    P, sps = cfg.preamble_len, cfg.sps
    sym = _sample_symbols(mf, kf + P * sps, 16, sps)
    corr = sym * np.exp(-1j * (phi0 + omega * (P + np.arange(16))))
    return int.from_bytes(_bits_to_bytes(_qpsk_to_bits(corr)), "big")


def frame_data_symbols(payload_len: int) -> int:
    """Number of QPSK data symbols a frame with this payload length occupies."""
    return (8 + payload_len) * 4  # (len4 + payload + crc4) bytes * 8 bits / 2


def receive_symbols(rx: np.ndarray, cfg: Config = Config()) -> np.ndarray:
    """Recover carrier-corrected data QPSK symbols from a single-frame capture."""
    taps = rrc_taps(cfg.beta, cfg.sps, cfg.span)
    mf = np.convolve(rx, taps)
    acq = _acquire(mf, cfg, 0, 8192 + cfg.preamble_len * cfg.sps)
    if acq is None:
        return np.array([], dtype=complex)
    kf, phi0, omega, _ = acq
    n_total = int((len(mf) - kf - 1) // cfg.sps) - cfg.preamble_len
    return _demod_data(mf, kf, phi0, omega, n_total, cfg)


def receive(rx: np.ndarray, cfg: Config = Config()):
    """Full receive: IQ in, payload bytes out (or None on CRC failure)."""
    out = receive_symbols(rx, cfg)
    if len(out) == 0:
        return None
    return parse_frame(_qpsk_to_bits(out))
