# native — the BOXCAR receiver in portable C++

`boxcar_rx.{h,cpp}` is a pure-C++ port of the Python reference receiver in
`boxcar/`. It has **no platform dependencies**, so the same source compiles for:

- this **desktop verification harness** (host toolchain, below), and
- the **Android NDK** library that feeds `MediaCodec` in the Hobocon app
  (mirrors the layout of hobocon-app's `:tv-sdr` `ntsc_demod`).

The receiver is the whole chain a phone needs: RRC matched filter → Zadoff-Chu
preamble acquisition (correlate, parabolic sub-sample timing, linear phase fit)
→ decision-directed carrier PLL → QPSK slice → rate-1/2 Viterbi → CRC-checked
frames → reassembled MPEG-TS.

## It's verified byte-exact against Python

The port isn't "probably equivalent" — it's checked. The Python transmitter
writes a real dongle-format capture, the C++ decodes it, and the bytes match the
source transport stream exactly, including through a noisy channel:

```
Python  boxcar.cli tx source.ts tx.cu8 --fec      # transmit
C++     boxcar_harness tx.cu8 rx.ts --fec          # receive
        rx.ts == source.ts   (157/157 frames, 206612 bytes, byte-exact)
```

Verified cases: coded (FEC) and uncoded paths, clean and through AWGN + a
+1500 Hz carrier offset + a 0.4-sample timing offset.

### Streaming, too

The phone gets IQ in small chunks, not one big capture, so `BoxcarRx` also
exposes `feed()`/`flush()`. Feeding the same samples in dongle-sized chunks is
byte-identical to the one-shot decode — verified at chunk sizes 4k/16k/64k/128k:

```bash
boxcar_harness capture.cu8 out.ts --fec --chunk 65536   # == one-shot output
```

## Build & run (desktop, no NDK)

With CMake:

```bash
cmake -S . -B build && cmake --build build
./build/boxcar_harness <capture.cu8|.cs8> <out.ts> [--cs8] [--fec] [--packets N]
```

Or straight with MSVC:

```bat
cl /O2 /EHsc /std:c++17 native\harness.cpp native\boxcar_rx.cpp /Fe:boxcar_harness.exe
```

## Next: onto the phone

The DSP is done and portable. The remaining app work (in hobocon-app) is the
glue that can only be built/run on Android:

- a JNI bridge (`nativeCreate/nativeFeed/nativePollTs/...`) over `BoxcarRx`
- a Kotlin `DigitalVideoSource` sibling to `SdrVideoSource`
- hand the recovered H.264+AAC MPEG-TS to Android `MediaCodec` for hardware
  decode → color + audio

That layer is hardware/Android-build-gated; this core is not, and it's green.
