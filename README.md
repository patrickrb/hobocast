# hobocast 📺🚂

**Color TV — with sound — thrown into a $30 RTL-SDR off the back of a moving train.**

Hobocast is the digital successor to the analog NTSC-over-RTL-SDR experiment in
`hobocon-app`. That experiment worked, but hit a wall of physics: analog NTSC
color lives on a subcarrier 3.58 MHz above the video carrier, which falls
*outside* an RTL-SDR's ~2.4 MHz capture window. So the analog picture is forever
black-and-white, and the audio (another carrier 4.5 MHz up) can't come along
either.

The fix is to stop fighting analog and **go digital**. We own the transmitter,
so we get to design the signal. A humble QPSK link fits comfortably inside the
dongle's window and carries an MPEG-TS of **H.264 color video + AAC audio**. On a
digital link, color and sound stop being an RF problem and become *just bytes*.

The waveform is codenamed **BOXCAR** — it's a box, it hauls cargo, and it rides
the rails.

```
  transmitter (HackRF / GNU Radio)                 receiver (RTL-SDR, $30)
  ────────────────────────────────                 ──────────────────────────
  video ─┐                                          IQ ─► matched filter
  audio ─┤► ffmpeg ► MPEG-TS ► BOXCAR modem ► RF  ►      ► preamble sync
         │           (H.264+AAC)  (QPSK/RRC)              ► carrier PLL
                                                          ► QPSK demod
                                                          ► MPEG-TS ► MediaCodec
                                                                       (color + sound)
```

## It already runs — with no radio

`boxcar/` is a complete, pure-Python reference modem: transmit → simulated RF
channel → receive. The channel models the impairments that actually bite on a
cheap dongle (thermal noise, tuner frequency error, unknown sample timing).

```bash
python demos/loopback.py        # push a COLOR image through the channel, byte-exact
python demos/video_loopback.py  # real H.264+AAC color video+audio over the channel
python demos/fec_demo.py        # error correction: FEC frames survive where uncoded die
python demos/robustness_demo.py # soft-decision (~1.5 dB) + interleaving (burst defence)
python demos/ber_sweep.py       # measured BER vs coherent-QPSK theory
python tests/test_modem.py      # regression tests (15)
```

The loopback recovers a color test image **bit-for-bit** through a 15 dB channel
with +1800 Hz carrier offset and a sub-sample timing error, and writes it to
`out/recovered.png`. The BER sweep tracks the theoretical QPSK curve within ~1 dB
— i.e. the receiver is genuinely coherent, not faked.

## Waveform at a glance

| Parameter | Value | Why |
|---|---|---|
| Modulation | QPSK, Gray-coded | 2 bits/symbol, robust, simple carrier recovery |
| Sample rate | 2.4 MS/s | RTL-SDR's reliable rate; the whole channel |
| Symbol rate | 600 ksym/s (sps=4) | fits with margin; sps=2 doubles the bitrate |
| Pulse shape | root-raised-cosine, β=0.35 | Nyquist / zero-ISI with the matched RX filter |
| Raw bitrate | 1.2 Mbit/s (uncoded) | enough for 320×240 color H.264 + AAC |
| Acquisition | Zadoff-Chu preamble | frame detection + timing + carrier estimate |
| Tracking | decision-directed 2nd-order PLL | holds phase across long frames |
| Integrity | CRC-32 per frame | drops corrupt frames instead of showing garbage |

Full spec: [`docs/protocol.md`](docs/protocol.md). Where this is going:
[`docs/roadmap.md`](docs/roadmap.md).

## The tradeoff (be honest)

This buys color + audio on the **cheap $30 dongle** — the thing wider-bandwidth
SDRs (~$99+ Airspy) would otherwise be needed for. The cost is the retro analog
*look*: no CRT scanlines, no roll, no glorious analog decay. It's a clean digital
picture instead. If the analog charm is the point, keep the NTSC path; if getting
color and sound to everyone's cheap dongle is the point, this is the way.

## Status

- **M1 done** — the BOXCAR waveform: modem + simulated channel + proof color
  image bytes survive byte-exact.
- **M3 done** — real color video + audio: an ffmpeg H.264+AAC MPEG-TS chunked
  into a BOXCAR frame-train, through the channel, reassembled and playable
  (157/157 frames, byte-exact).
- **M2 done** — forward error correction: rate-1/2 convolutional coding + Viterbi
  recovers whole frames several dB deeper into the noise (7/7 at 8 dB where
  uncoded gets 0/7). Plus **soft-decision** decoding (~1.5 dB more) and **block
  interleaving** for burst/fade defence — both in `boxcar.cli`
  (`demos/robustness_demo.py`).
- **M4 software half done** — the receiver speaks the real dongle byte formats
  (CU8/CS8) and decodes video byte-exact through 8-bit ADC quantization
  (`demos/hardware_loopback.py`). A `boxcar.cli tx/rx` tool reads and writes the
  exact `.cu8`/`.cs8` files `rtl_sdr`/`hackrf_transfer` use. What's left is the
  physical radio link (needs hardware).

```bash
python demos/hardware_loopback.py                        # decode through the real CU8 format
python -m boxcar.cli tx video.ts tx.cs8 --fmt cs8 --fec  # file -> HackRF-ready IQ
python -m boxcar.cli rx capture.cu8 out.ts --fmt cu8 --fec  # RTL-SDR capture -> file
```

Next: **M4** over-the-air (HackRF transmit → RTL-SDR capture) and **M5** folding
the receiver into the Hobocon app. See the [roadmap](docs/roadmap.md).
