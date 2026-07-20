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
- [ ] Interleaving to spread burst errors (deferred — matters most on real fading)
- [ ] Soft-decision Viterbi for a further ~2 dB (deferred to hardware bring-up)

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
- [ ] TX via HackRF (`hackrf_transfer`) or a GNU Radio flowgraph — *needs radio*
- [ ] RX capture from a real RTL-SDR feeding the Python RX — *needs radio*
- [ ] Bench loopback over a cable/attenuator, then over the air — *needs radio*
- [ ] Measure real SNR / packet loss at range — *needs radio*

The software half is done and tested: the receiver already decodes the exact
byte format a dongle produces. What remains is purely the physical link —
pipe `boxcar.cli`'s output/input to `hackrf_transfer`/`rtl_sdr`.

## M5 — On the phone
Fold the receiver into the Hobocon app alongside the existing sources.
- [ ] Port the RX DSP to C++/NDK (mirrors the existing `:tv-sdr` module layout)
- [ ] Hand recovered H.264+AAC to Android `MediaCodec` for hardware decode
- [ ] New `VideoSource` (digital) in the app's source selector
- [ ] Live color + audio from a $30 dongle 🎉

## Open questions
- `sps=4` (safe) vs `sps=2` (double bitrate, tighter sync) as the shipping profile?
- FEC choice: convolutional (simple, proven) vs LDPC (better, more code)?
- Keep the analog NTSC path as a selectable "authentic B&W" mode, or retire it?
