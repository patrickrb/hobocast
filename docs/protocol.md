# BOXCAR waveform specification (v0.1 — reference modem)

BOXCAR is a narrowband digital link designed to fit entirely inside an RTL-SDR's
capture window while carrying enough throughput for low-resolution color video
with audio. This document is the contract between transmitter and receiver.

## 1. Channel & RF

| Parameter | Value | Notes |
|---|---|---|
| Capture sample rate `fs` | 2.4 MS/s | RTL-SDR reliable rate (2.048 MS/s fallback) |
| Occupied bandwidth | ≈ `Rsym·(1+β)` ≈ 0.81 MHz | well inside `fs`; room for guard/AFC |
| Center tuning | video carrier + 0 (NCO to DC) | tuner ppm error handled by CFO tracking |
| Carriers (per station) | 906 / 912 / 918 MHz | inherited from `hobocon-app` rf-contract |

Because the entire signal is < 1 MHz wide, three stations still fit the 902–928
MHz ISM allocation with generous spacing.

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
