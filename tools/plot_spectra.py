"""Theoretical BOXCAR transmit spectra: ideal transmitter vs. an ADALM-Pluto.

Not a measurement — a first-principles prediction of what each spectrum looks
like on a spectrum analyzer, built from the modem itself.

The 'ideal' curve is the *actual* waveform ``boxcar.modulate()`` emits (RRC-shaped
QPSK, β=0.35, Rsym=600 ksym/s) through a perfect DAC/PA. The 'Pluto' curve is that
identical baseband pushed through a physical model of the AD9363 zero-IF front end:
PA compression (spectral regrowth), LO/DC leakage, I/Q-imbalance image, a finite
quantization/thermal noise floor, and 12-bit DAC quantization.

    python tools/plot_spectra.py        # writes docs/spectra.png and docs/spectra.pdf
"""

import os
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from boxcar.dsp import rrc_taps, upsample  # noqa: E402

# --- signal parameters (straight from boxcar.modem.Config) -----------------
FS = 2_400_000.0   # channel / sample rate (Hz)
SPS = 4            # samples per symbol
BETA = 0.35        # RRC roll-off
SPAN = 8           # RRC span (symbols)
RSYM = FS / SPS    # 600 ksym/s
OCC = RSYM * (1 + BETA)   # occupied bandwidth = 810 kHz

rng = np.random.default_rng(1)  # fixed seed -> reproducible figure

# --- ideal transmitted baseband -------------------------------------------
N_SYM = 60_000
bits = rng.integers(0, 2, size=2 * N_SYM)
syms = ((1 - 2 * bits[0::2]) + 1j * (1 - 2 * bits[1::2])) / np.sqrt(2.0)  # Gray QPSK
taps = rrc_taps(BETA, SPS, SPAN)
ideal = np.convolve(upsample(syms, SPS), taps)
ideal /= np.sqrt(np.mean(np.abs(ideal) ** 2))  # unit average power


# --- ADALM-Pluto (AD9363 zero-IF) impairment model ------------------------
def pluto_frontend(x):
    x = x / np.sqrt(np.mean(np.abs(x) ** 2))

    # 1. PA compression (Rapp model, smooth soft-limit) -> spectral regrowth.
    #    Vsat set so the ~3.5 dB PAPR of RRC-QPSK just grazes compression,
    #    lifting the adjacent-channel shoulders to a realistic ~ -40 dBc.
    vsat, p = 1.9, 2.0
    g = 1.0 / (1.0 + (np.abs(x) / vsat) ** (2 * p)) ** (1 / (2 * p))
    y = x * g

    # 2. I/Q gain + phase imbalance -> a mirror image (~ -45 dBc).
    ge, pe = 0.02, np.deg2rad(1.2)         # 2% gain, 1.2 deg phase
    a = 0.5 * (1 + ge * np.exp(1j * pe))
    b = 0.5 * (1 - ge * np.exp(-1j * pe))
    y = a * y + b * np.conj(y)

    # 3. LO / DC leakage (zero-IF carrier feedthrough). A discrete tone at DC;
    #    on a fine-RBW PSD it concentrates into one bin and pokes above the
    #    spread signal, the classic central spike of a direct-conversion TX.
    y = y + 0.05

    # 4. LO phase noise -> close-in skirt (integrated phase-noise process).
    ph = np.cumsum(rng.standard_normal(len(y))) * 2.2e-4
    y = y * np.exp(1j * ph)

    # 5. Broadband noise floor (thermal + quant), ~ -60 dBc in-channel.
    nf = 10 ** (-63 / 20)
    y = y + nf * (rng.standard_normal(len(y)) + 1j * rng.standard_normal(len(y))) / np.sqrt(2)

    # 6. 12-bit DAC quantization (AD9363), ~90% of full scale.
    fs_scale = 0.9 / np.max(np.abs(y))
    q = np.round(y * fs_scale * 2047) / 2047 / fs_scale
    return q


pluto = pluto_frontend(ideal)


# --- PSD via Welch ----------------------------------------------------------
def welch(x, fs, nfft=4096):
    win = np.hanning(nfft)
    step = nfft // 2
    acc = np.zeros(nfft)
    n = 0
    for i in range(0, len(x) - nfft, step):
        seg = x[i:i + nfft] * win
        acc += np.abs(np.fft.fftshift(np.fft.fft(seg))) ** 2
        n += 1
    psd = acc / (n * (win ** 2).sum())
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / fs))
    return f, psd


f, pi = welch(ideal, FS)
_, pp = welch(pluto, FS)
ref = pi.max()
pi_db = 10 * np.log10(pi / ref + 1e-30)
pp_db = 10 * np.log10(pp / ref + 1e-30)
f_mhz = f / 1e6

# --- plot -------------------------------------------------------------------
BLUE, AMBER, GRID, INK, MUTE = "#2b6cb0", "#dd6b20", "#d9dee5", "#1a202c", "#6b7280"
plt.rcParams.update({
    "font.size": 11, "axes.edgecolor": "#cbd2d9", "axes.linewidth": 0.8,
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def dress(ax, title):
    ax.axvspan(-OCC / 2e6, OCC / 2e6, color="#eef4fb", zorder=0)
    for x0 in (-OCC / 2e6, OCC / 2e6):
        ax.axvline(x0, color="#9db7d4", lw=0.9, ls=(0, (4, 3)), zorder=1)
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-90, 12)
    ax.grid(True, color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(MultipleLocator(0.3))
    ax.yaxis.set_major_locator(MultipleLocator(20))
    ax.set_ylabel("PSD  (dBc / bin)", color=INK)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=8)
    ax.tick_params(colors=MUTE)


fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 8.4), sharex=True)

# (a) ideal
dress(ax1, "(a)  Ideal transmitter — RRC-shaped QPSK, perfect DAC / linear PA")
ax1.plot(f_mhz, pi_db, color=BLUE, lw=1.5, label="BOXCAR TX (ideal)")
ax1.annotate("810 kHz occupied\n(Rsym · (1+β))", xy=(0, -4), xytext=(0, -30),
             ha="center", va="center", fontsize=9, color=MUTE,
             arrowprops=dict(arrowstyle="-", color="#9db7d4", lw=0.8))
ax1.annotate("RRC roll-off (β = 0.35)\n+ finite-filter sidelobes", xy=(0.46, -30),
             xytext=(0.78, -20), fontsize=8.5, color=MUTE, ha="center",
             arrowprops=dict(arrowstyle="->", color="#9db7d4", lw=0.8))
ax1.legend(loc="upper right", frameon=False, fontsize=9.5)

# (b) pluto, with ideal as a faint reference
dress(ax2, "(b)  ADALM-Pluto (AD9363 zero-IF) — same waveform, real front end")
ax2.plot(f_mhz, pi_db, color=BLUE, lw=1.0, ls=(0, (3, 3)), alpha=0.55,
         label="ideal (reference)", zorder=2)
ax2.plot(f_mhz, pp_db, color=AMBER, lw=1.5, label="Pluto TX", zorder=3)
ax2.set_xlabel("baseband frequency  (MHz)   —   2.4 MHz channel", color=INK)
ax2.legend(loc="upper right", frameon=False, fontsize=9.5)

# label the characteristic impairments
ax2.annotate("LO / DC leakage\n(carrier feedthrough;\nheight is RBW-dependent)",
             xy=(0.01, 3), xytext=(-0.5, -8), fontsize=8.5, color=AMBER, ha="center",
             arrowprops=dict(arrowstyle="->", color=AMBER, lw=0.9))
ax2.annotate("PA spectral regrowth\n(shoulders ~ −40 dBc)", xy=(0.55, -40),
             xytext=(0.74, -18), fontsize=8.5, color=AMBER, ha="center",
             arrowprops=dict(arrowstyle="->", color=AMBER, lw=0.9))
ax2.annotate("noise floor ~ −60 dBc", xy=(-0.9, -60), xytext=(-0.6, -80),
             fontsize=8.5, color=MUTE, ha="center",
             arrowprops=dict(arrowstyle="->", color=MUTE, lw=0.9))

fig.suptitle("BOXCAR transmit spectrum  ·  QPSK, 600 ksym/s, RRC β = 0.35",
             x=0.06, ha="left", fontsize=13.5, fontweight="bold", color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.97))

docs = os.path.join(_ROOT, "docs")
png = os.path.join(docs, "spectra.png")
pdf = os.path.join(docs, "spectra.pdf")
fig.savefig(png, dpi=150, bbox_inches="tight")
fig.savefig(pdf, bbox_inches="tight")
print("wrote", png)
print("wrote", pdf)

# quick numeric sanity: occupied BW, shoulders, floor, LO spike
adj = (np.abs(f_mhz) > 0.5) & (np.abs(f_mhz) < 0.7)
lo = int(np.argmin(np.abs(f_mhz)))
print(f"occupied BW      : {OCC / 1e3:.0f} kHz")
print(f"pluto shoulder   : {pp_db[adj].max():.1f} dBc")
print(f"pluto LO spike   : {pp_db[lo]:.1f} dBc")
print(f"pluto noise floor: {np.median(pp_db[np.abs(f_mhz) > 0.95]):.1f} dBc")
