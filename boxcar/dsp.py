"""Baseband DSP primitives: root-raised-cosine pulse shaping and upsampling.

A matched RRC filter on each end (TX + RX) gives a raised-cosine overall
response — the Nyquist condition, i.e. zero inter-symbol interference at the
symbol instants. Everything else in the modem builds on that.
"""

import numpy as np


def rrc_taps(beta: float, sps: int, span: int) -> np.ndarray:
    """Root-raised-cosine filter taps, unit energy.

    beta: rolloff (0..1); sps: samples per symbol; span: length in symbols.
    """
    n = span * sps
    t = (np.arange(n + 1) - n / 2) / sps  # time axis in symbol periods
    h = np.zeros(n + 1)
    for i, ti in enumerate(t):
        if abs(ti) < 1e-8:
            h[i] = 1.0 - beta + 4.0 * beta / np.pi
        elif beta > 0 and abs(abs(ti) - 1.0 / (4.0 * beta)) < 1e-8:
            # Removable singularity at t = ±1/(4·beta).
            h[i] = (beta / np.sqrt(2.0)) * (
                (1.0 + 2.0 / np.pi) * np.sin(np.pi / (4.0 * beta))
                + (1.0 - 2.0 / np.pi) * np.cos(np.pi / (4.0 * beta))
            )
        else:
            num = np.sin(np.pi * ti * (1.0 - beta)) + 4.0 * beta * ti * np.cos(
                np.pi * ti * (1.0 + beta)
            )
            den = np.pi * ti * (1.0 - (4.0 * beta * ti) ** 2)
            h[i] = num / den
    h /= np.sqrt(np.sum(h ** 2))
    return h


def upsample(sym: np.ndarray, sps: int) -> np.ndarray:
    """Insert sps-1 zeros between symbols (impulse train for pulse shaping)."""
    out = np.zeros(len(sym) * sps, dtype=complex)
    out[::sps] = sym
    return out
