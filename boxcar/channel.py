"""A simulated RF channel: fractional delay, carrier frequency offset, and AWGN.

This stands in for the real path (HackRF/GNU Radio TX -> air -> RTL-SDR RX) so the
whole modem can be developed and regression-tested with no hardware. The
impairments modelled are the ones that actually bite on a cheap dongle: unknown
sample-timing phase, tuner frequency error (ppm), and thermal noise.
"""

import numpy as np

from .modem import Config


def apply_channel(
    tx: np.ndarray,
    cfg: Config = Config(),
    es_n0_db: float = 15.0,
    cfo_hz: float = 0.0,
    frac_delay: float = 0.0,
    pad: int = 200,
    seed: int = 0,
) -> np.ndarray:
    """Pass transmit IQ through the modelled channel and return received IQ.

    es_n0_db: symbol SNR (Es/N0). cfo_hz: carrier offset (tuner ppm error).
    frac_delay: sub-sample timing offset. pad: leading/trailing noise samples
    (models an unsynchronised capture the receiver must acquire within).
    """
    rng = np.random.default_rng(seed)

    if frac_delay:
        n = np.arange(len(tx))
        tx = np.interp(n - frac_delay, n, tx.real) + 1j * np.interp(
            n - frac_delay, n, tx.imag
        )

    if cfo_hz:
        n = np.arange(len(tx))
        tx = tx * np.exp(1j * 2.0 * np.pi * cfo_hz * n / cfg.fs)

    y = np.concatenate([np.zeros(pad, dtype=complex), tx, np.zeros(pad, dtype=complex)])

    # Es/N0 -> per-complex-sample noise power. Es is the per-symbol energy, which
    # is spread across sps samples, so signal power * sps = Es.
    es = np.mean(np.abs(tx) ** 2) * cfg.sps
    n0 = es / (10.0 ** (es_n0_db / 10.0))
    sigma = np.sqrt(n0 / 2.0)
    noise = sigma * (rng.standard_normal(len(y)) + 1j * rng.standard_normal(len(y)))
    return y + noise
