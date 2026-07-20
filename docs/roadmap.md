# hobocast roadmap

The order is chosen so every milestone is *runnable* and de-risks the next one.

## M1 — BOXCAR waveform ✅ (done)
Pure-Python modem + simulated channel proving a color image survives byte-exact.
- [x] QPSK + RRC modulator
- [x] Simulated channel (AWGN, CFO, fractional timing)
- [x] Data-aided receiver (ZC preamble acquire + decision-directed PLL)
- [x] CRC-framed frames; color-image loopback; BER-vs-theory sweep; tests

## M2 — Forward error correction ✅ (done)
Turn the ragged BER at the cell edge into clean video.
- [x] Rate-1/2 convolutional encoder + hard-decision Viterbi (K=7, 171/133 octal)
- [x] Fixed-size coded frames wired into the stream layer (`cfg.fec`)
- [x] Demo: FEC recovers 7/7 frames at 8 dB Es/N0 where uncoded gets 0/7
      (`demos/fec_demo.py`)
- [x] Soft-decision Viterbi (`viterbi_decode_soft`, `cfg.soft`) — ~1.5 dB gain,
      RX-only so the waveform is unchanged (29/30 vs 13/30 frames at 5.5 dB)
- [x] Block interleaving (`cfg.interleave`) — scatters bursts the code can't
      otherwise survive (decodes a 64-bit burst that kills the plain code).
      `demos/robustness_demo.py` measures both; both wired into `boxcar.cli`

Note: `soft`/`interleave` default **off**, so the byte-exact C++ parity still
holds for the shipping default. Soft is waveform-compatible (turn on anytime);
interleaving changes the wire format, so the vendored C++ receiver would need
the matching de-interleave before shipping it on.

## M3 — Carry real video + audio ✅ (done)
Wrap an actual media stream instead of a test image.
- [x] `ffmpeg` encode: H.264 (baseline, low-res) + AAC → MPEG-TS
- [x] Map 188-byte TS packets onto BOXCAR frames (`boxcar/stream.py`)
- [x] Multi-frame receiver walks the burst-train, re-syncing per frame
- [x] Loopback 3 s of 320×240 color video + 440 Hz tone: 157/157 frames,
      byte-exact, reassembled `.ts` decodes in ffmpeg (`demos/video_loopback.py`)
- [ ] Pilot symbols for fast re-sync after packet loss (deferred to M4)

## M4 — Real hardware 🟡 (software half done)
Get bytes over the air, not just through a simulated channel.
- [x] Real SDR IQ byte formats: CU8 (RTL-SDR) + CS8 (HackRF) converters
      (`boxcar/sdr_io.py`) — the exact bytes `rtl_sdr`/`hackrf_transfer` speak
- [x] `boxcar.cli tx/rx`: file ⇄ IQ capture in those formats, FEC-aware
- [x] Full chain verified through **8-bit ADC quantization**: 157/157 frames
      byte-exact (`demos/hardware_loopback.py`), plus regression tests
- [x] Continuous broadcast transmitter: `boxcar.cli stream` reads a live/looping
      TS from stdin and emits an endless IQ burst-train to stdout — pipes
      straight into `hackrf_transfer -t -` (verified byte-exact, incl. looping)
- [ ] TX via HackRF (`hackrf_transfer`) or a GNU Radio flowgraph — *needs radio*
- [ ] RX capture from a real RTL-SDR feeding the Python RX — *needs radio*
- [ ] Bench loopback over a cable/attenuator, then over the air — *needs radio*
- [ ] Measure real SNR / packet loss at range — *needs radio*

The software half is done and tested: the receiver already decodes the exact
byte format a dongle produces. What remains is purely the physical link —
pipe `boxcar.cli`'s output/input to `hackrf_transfer`/`rtl_sdr`.

## M5 — On the phone 🟡 (core done + app glue written; device-gated)
Fold the receiver into the Hobocon app alongside the existing sources.
- [x] Port the RX DSP to portable C++ (`native/boxcar_rx.{h,cpp}`), verified
      **byte-exact** against the Python reference (coded/uncoded, clean + noisy,
      batch + streaming) via `native/harness.cpp`
- [x] Streaming `feed()`/`flush()` so the phone can push dongle-sized IQ chunks
- [x] Vendored into hobocon-app `:tv-sdr` with a JNI bridge (`boxcar_jni.cpp`),
      Kotlin `BoxcarBridge`, and a `DigitalVideoSource`
- [x] Play recovered H.264+AAC through the app's **existing ExoPlayer** (TS over
      a localhost URL) instead of hand-rolling MediaCodec
- [ ] Verify on a device: USB streaming, ExoPlayer live-TS playback, tuning
      policy for a shared dongle — *needs Android hardware + a BOXCAR transmit*
- [ ] Live color + audio from a $30 dongle 🎉 — *the on-device milestone*

## Open questions
- `sps=4` (safe) vs `sps=2` (double bitrate, tighter sync) as the shipping profile?
- FEC choice: convolutional (simple, proven) vs LDPC (better, more code)?
- Keep the analog NTSC path as a selectable "authentic B&W" mode, or retire it?
