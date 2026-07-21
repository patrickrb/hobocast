# BOXCAR waveform specification (v0.1 — reference modem)

BOXCAR is a narrowband digital link designed to fit entirely inside an RTL-SDR's
capture window while carrying enough throughput for low-resolution color video
with audio. This document is the contract between transmitter and receiver.

## 1. Channel & RF

| Parameter | Value | Notes |
|---|---|---|
| Capture sample rate `fs` | 2.4 MS/s | RTL-SDR reliable rate (2.048 MS/s fallback) |
| Occupied bandwidth | ≈ `Rsym·(1+β)` ≈ 0.81 MHz | well inside `fs`; room for guard/AFC |
| Center tuning | channel carrier + 0 (NCO to DC) | tuner ppm error handled by CFO tracking |
| Carriers (per channel) | UHF ch 14 up: **471.25 MHz + n·1.5 MHz** | matched to a UHF antenna; see below |

Because the entire signal is only ~810 kHz wide, **many channels fit in one wide
transmit stream**. The deployment stacks 6 channels 1.5 MHz apart
(471.25–478.75 MHz) into a single HackRF transmission via frequency-division
multiplexing — see §6.

> **Band note.** Earlier drafts put the carriers in the 902–928 MHz ISM band. On
> a UHF-tuned antenna that mismatch coupled poorly and caused progressive
> dropouts; moving to the antenna's actual band (UHF TV, ch 14 up) restored link
> margin. Frequency is deployment config, not part of the waveform.

## 2. Physical layer

- **Modulation:** QPSK, Gray-mapped. Symbol `s = ((1−2·b0) + j(1−2·b1))/√2`,
  where `b0` is the first (MSB-order) bit of the pair.
- **Symbol rate:** `Rsym = fs / sps`. Reference uses `sps = 4` → 600 ksym/s →
  1.2 Mbit/s uncoded. `sps = 2` → 1.2 Msym/s → 2.4 Mbit/s (tighter sync budget).
- **Pulse shaping:** root-raised-cosine, rolloff `β = 0.35`, span 8 symbols,
  applied at TX and matched at RX (raised-cosine overall ⇒ zero ISI).

## 3. Frame format

```
┌──────────────────┬───────────────────────────────────────────────┐
│  ZC preamble     │  payload (QPSK data symbols)                   │
│  (64 symbols)    │  ┌────────┬───────────────┬──────────┐         │
│                  │  │ len u32│ payload bytes │ crc32 u32│         │
│                  │  └────────┴───────────────┴──────────┘         │
└──────────────────┴───────────────────────────────────────────────┘
```

- **Preamble:** Zadoff-Chu, length 64, root 25. Constant modulus; used for frame
  detection, symbol-timing recovery, and initial carrier phase/frequency estimate.
- **Header `len`:** big-endian uint32, payload length in bytes.
- **CRC-32:** IEEE (zlib) over `len ‖ payload`. Frames that fail are dropped.
- Bit → symbol packing is MSB-first; bytes are unpacked to bits big-endian.

## 4. Receiver (data-aided)

1. **Matched filter** the incoming IQ with the RRC taps.
2. **Acquire:** correlate against the preamble sampled at symbol spacing; the
   magnitude peak gives frame position, with parabolic interpolation for
   sub-sample timing. A linear fit of the de-modulated preamble phase seeds the
   carrier phase `φ₀` and per-symbol frequency offset `ω`.
3. **Track:** a decision-directed 2nd-order PLL (seeded from `φ₀, ω`) corrects
   residual carrier drift through the whole payload, so frame length is
   unbounded by CFO.
4. **Demap** QPSK → bits, **parse** header, **check** CRC.

Reference implementation: `boxcar/modem.py`. Channel model: `boxcar/channel.py`.

## 5. Not in v0.1 (see roadmap)

- Forward error correction (convolutional+Viterbi or LDPC) — today integrity is
  detect-only via CRC; FEC turns marginal frames into good ones.
- Pilot symbols for fast re-acquisition on burst loss.
- MPEG-TS packetization mapping (188-byte TS packets → BOXCAR frames).
- Real SDR I/O (rtl-sdr / SoapySDR capture, HackRF or GNU Radio transmit).

## 6. Multi-channel (frequency-division multiplexing)

A single HackRF transmits **several BOXCAR channels at once** — each channel is
independently modulated to its own `.cs8`, then all are stacked in frequency into
one wideband stream. Every receiver just tunes its RTL-SDR to the channel it
wants; the receiver DSP above is unchanged (the ±30 kHz coarse search absorbs the
slot offset).

`scripts/fdm_mux.py` builds the composite:

1. Read N per-channel `.cs8` (2.4 MS/s baseband, centered at DC).
2. Upsample each to a common composite rate `fs_out = fs · up` (e.g. 12 MS/s,
   `up = 5`) with a polyphase filter.
3. Shift each channel to its slot: multiply by `exp(j2π·offset·n/fs_out)`.
4. Sum, normalize below full scale, write one composite `.cs8`.

```bash
python scripts/fdm_mux.py --out composite.cs8 \
    reel-1.cs8@-3750000 reel-2.cs8@-2250000 reel-3.cs8@-750000 \
    reel-4.cs8@750000   reel-5.cs8@2250000  reel-6.cs8@3750000
hackrf_transfer -t composite.cs8 -f 475000000 -s 12000000 -R   # all 6 channels
```

Design rules:

- **Spacing ≥ occupied BW + guard.** At 810 kHz occupied, 1.5 MHz spacing keeps a
  neighbor outside the tuned channel's matched-filter passband.
- **Avoid composite DC.** Don't place a channel at `fs_out/2`'s center (the radio
  has an LO/DC spur there); offset the plan so DC lands between channels.
- **Capacity is bandwidth ÷ spacing.** ~20 MHz of HackRF fits ~8–13 channels at
  1.5 MHz; the practical limit is the 8-bit DAC's dynamic range and per-channel
  power (each channel loses ≈ `10·log₁₀(N)` dB to the split).
- The expensive DSP (modulation) is already per-channel, so muxing is only
  resample + shift + sum; a chunked accumulator keeps peak RAM bounded for
  multi-GB composites.
