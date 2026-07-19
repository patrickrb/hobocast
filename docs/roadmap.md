# hobocast roadmap

The order is chosen so every milestone is *runnable* and de-risks the next one.

## M1 — BOXCAR waveform ✅ (done)
Pure-Python modem + simulated channel proving a color image survives byte-exact.
- [x] QPSK + RRC modulator
- [x] Simulated channel (AWGN, CFO, fractional timing)
- [x] Data-aided receiver (ZC preamble acquire + decision-directed PLL)
- [x] CRC-framed frames; color-image loopback; BER-vs-theory sweep; tests

## M2 — Forward error correction
Turn the raw ~1e-3 BER at the cell edge into clean video.
- [ ] Rate-1/2 convolutional encoder + Viterbi decoder (or LDPC)
- [ ] Interleaving to spread burst errors
- [ ] Re-run the BER sweep as a BER-vs-coded curve (expect ~4–5 dB coding gain)

## M3 — Carry real video + audio ✅ (done)
Wrap an actual media stream instead of a test image.
- [x] `ffmpeg` encode: H.264 (baseline, low-res) + AAC → MPEG-TS
- [x] Map 188-byte TS packets onto BOXCAR frames (`boxcar/stream.py`)
- [x] Multi-frame receiver walks the burst-train, re-syncing per frame
- [x] Loopback 3 s of 320×240 color video + 440 Hz tone: 157/157 frames,
      byte-exact, reassembled `.ts` decodes in ffmpeg (`demos/video_loopback.py`)
- [ ] Pilot symbols for fast re-sync after packet loss (deferred to M4)

## M4 — Real hardware
Get bytes over the air, not just through a simulated channel.
- [ ] RX capture from RTL-SDR (rtl-sdr / SoapySDR) feeding the Python RX
- [ ] TX via HackRF (`hackrf_transfer`) or a GNU Radio flowgraph
- [ ] Bench loopback over a cable/attenuator, then over the air
- [ ] Measure real SNR / packet loss at range

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
