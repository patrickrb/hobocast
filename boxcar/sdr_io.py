"""On-the-wire IQ formats, so BOXCAR interoperates with real SDR tools directly.

Real dongles don't speak complex floats — they speak 8-bit interleaved samples:

  * CU8 — unsigned 8-bit, centered ~127.5. What `rtl_sdr` writes and the RTL2832U
    delivers over USB (and what hobocon-app's native `feedU8` already consumes).
  * CS8 — signed 8-bit. What `hackrf_transfer -t` transmits.

These converters let you feed a captured `.cu8` straight into the receiver, or hand
a modulated `.cs8` straight to `hackrf_transfer`. The 8-bit quantization here is the
same one the hardware imposes — decoding through it is the honest hardware check.

The receiver is amplitude-blind (it tracks phase and slices signs), so absolute
scale doesn't matter; on write we just normalise to a safe peak to avoid clipping.
"""

import numpy as np

_PEAK = 100.0  # target peak code so 8-bit range is used without clipping


def _scale(iq: np.ndarray) -> float:
    peak = float(np.max(np.abs(iq))) if len(iq) else 1.0
    return _PEAK / peak if peak > 0 else 1.0


def to_cu8(iq: np.ndarray, scale: float | None = None) -> np.ndarray:
    """Complex float IQ -> RTL-SDR CU8 byte stream (I0,Q0,I1,Q1,...).

    `scale` fixes the amplitude mapping; pass a constant when writing a
    continuous stream block-by-block so the level doesn't jump between blocks.
    """
    s = _scale(iq) if scale is None else scale
    out = np.empty(len(iq) * 2, dtype=np.uint8)
    out[0::2] = np.clip(np.round(iq.real * s) + 127.5, 0, 255).astype(np.uint8)
    out[1::2] = np.clip(np.round(iq.imag * s) + 127.5, 0, 255).astype(np.uint8)
    return out


def from_cu8(buf) -> np.ndarray:
    """RTL-SDR CU8 byte stream -> complex float IQ."""
    b = np.frombuffer(buf, dtype=np.uint8).astype(np.float32)
    return (b[0::2] - 127.5) + 1j * (b[1::2] - 127.5)


def to_cs8(iq: np.ndarray, scale: float | None = None) -> np.ndarray:
    """Complex float IQ -> HackRF CS8 byte stream. `scale`: see to_cu8."""
    s = _scale(iq) if scale is None else scale
    out = np.empty(len(iq) * 2, dtype=np.int8)
    out[0::2] = np.clip(np.round(iq.real * s), -128, 127).astype(np.int8)
    out[1::2] = np.clip(np.round(iq.imag * s), -128, 127).astype(np.int8)
    return out


def fixed_scale(iq: np.ndarray) -> float:
    """The scale to_cu8/to_cs8 would pick for `iq` — capture it once, reuse it."""
    return _scale(iq)


def from_cs8(buf) -> np.ndarray:
    """HackRF CS8 byte stream -> complex float IQ."""
    b = np.frombuffer(buf, dtype=np.int8).astype(np.float32)
    return b[0::2] + 1j * b[1::2]


_WRITERS = {"cu8": to_cu8, "cs8": to_cs8}
_READERS = {"cu8": from_cu8, "cs8": from_cs8}


def write_iq(path: str, iq: np.ndarray, fmt: str = "cu8") -> None:
    _WRITERS[fmt](iq).tofile(path)


def read_iq(path: str, fmt: str = "cu8") -> np.ndarray:
    with open(path, "rb") as f:
        return _READERS[fmt](f.read())
