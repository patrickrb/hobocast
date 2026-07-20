# Running the hobocast demo

The same demo as [`fstv-demo`](../../fstv-demo) — throw TV into a $30 dongle off
a HackRF — but on the **digital BOXCAR** waveform, so you get **color and sound**
instead of analog black-and-white. And because hobocast has a real *receiver*,
you can watch it come back on a laptop, not just a Sony Watchman.

```
  TX:  ffmpeg (H.264+AAC → MPEG-TS) → boxcar.cli → IQ → hackrf_transfer
  RX:  rtl_sdr → boxcar.cli / native decoder → MPEG-TS → ffplay   (color + sound)
```

Default RF: **906 MHz** (inside the 902–928 MHz ISM band), 2.4 Msps. Override with
`HOBOCAST_FREQ`, `HOBOCAST_RATE`, etc. (see `scripts/_config.sh`).

## No radio? Run the whole thing in software first

```bash
./demo-loopback.sh            # bars+tone → BOXCAR → decode → play, byte-exact
./demo-loopback.sh clip.mp4   # your own video
```

This proves the digital chain end-to-end on any laptop — the same bytes come out
that went in. Perfect for a talk when you can't (or shouldn't) transmit.

> Tip: build the fast C++ decoder once — `scripts/build-native.sh` — or the
> pure-Python receiver will make decoding a full clip slow. It's the same DSP the
> phone runs.

## Transmit (HackRF)

```bash
scripts/install-linux.sh          # or install-mac.sh — ffmpeg + hackrf + rtl-sdr + numpy
./demo-hackrf.sh                  # color bars, or media/channel/* if present
scripts/tx-hackrf.sh clip.mp4     # loop one video, real-time
scripts/fetch-commercials.sh      # grab a 90s-commercials playlist into media/channel/
scripts/tx-cycle.sh media/channel 30   # rotate clips, 30 s each
scripts/tx-file.sh media/bars.cs8 --gain 30 --amp   # loop a pre-rendered IQ file
scripts/tx-obs.sh --gain 30       # broadcast a live OBS feed (UDP → BOXCAR)
```

Two transmit styles, same as fstv:

- **Real-time** (`tx-hackrf.sh`, `tx-obs.sh`) — encode + modulate on the fly, any
  length. Needs enough CPU to modulate in real time; if you hear underruns,
  pre-render instead.
- **Pre-rendered file** (`render-iq.sh` → `tx-file.sh`) — modulate once to a
  `.cs8`, then `hackrf_transfer -R` loops it from disk. Rock-solid, no real-time
  Python. No length cap (unlike the Pluto's DDR loop in fstv).

```bash
scripts/render-iq.sh media/bbb.mp4 10 30 media/bbb.cs8   # 30 s clip → IQ
scripts/render-bars.sh media/bars.cs8 10                 # color bars + tone → IQ
scripts/tx-file.sh media/bbb.cs8
```

## Receive (RTL-SDR)

The part the analog demo couldn't do — a software receiver:

```bash
./demo-rx.sh                 # capture a few seconds, decode, play (color + sound)
./demo-rx.sh --loop          # keep grabbing successive chunks
scripts/rx-rtlsdr.sh --seconds 8 --gain auto --keep grab.ts
```

The pure-Python receiver isn't real-time at 2.4 Msps, so `rx-rtlsdr.sh` captures a
chunk, decodes, and plays it. The **real-time** receiver is the C++ core — either
build it (`scripts/build-native.sh`, used automatically) or run it on the phone
via the Hobocon app's digital source.

## The demo scripts

| Script | What it does |
|--------|--------------|
| `demo-loopback.sh` | Whole chain in software, no radio — encode → BOXCAR → decode → play. |
| `demo-hackrf.sh` | One-command transmit: bars, or `media/channel/*`. |
| `demo-rx.sh` | One-command receive + play off an RTL-SDR. |
| `scripts/tx-hackrf.sh` | Real-time transmit of video(s), looped. |
| `scripts/tx-file.sh` | Loop a `.cs8` (or render a `.ts`/video first). |
| `scripts/tx-cycle.sh` | Rotate a folder of clips, N seconds each. |
| `scripts/tx-obs.sh` | Broadcast a live OBS feed (UDP → BOXCAR). |
| `scripts/render-iq.sh` | Video → BOXCAR `.cs8` IQ file. |
| `scripts/render-bars.sh` | Color bars + tone → `.cs8`. |
| `scripts/rx-rtlsdr.sh` | Capture → decode → play. |
| `scripts/build-native.sh` | Build the fast C++ receiver (real-time decode). |
| `scripts/fetch-commercials.sh` | Pull a 90s-commercials playlist into `media/channel/`. |
| `scripts/install-linux.sh` / `install-mac.sh` | Install ffmpeg + hackrf + rtl-sdr + numpy. |

## Tuning it

- **Bitrate.** `boxcar.cli rate --fec --human` prints the link's payload bitrate
  (~592 kbit/s at the default profile). The scripts mux the TS CBR to exactly
  this so transmit and playback stay in sync.
- **Robustness knobs** (they cost nothing to leave on): `--soft` (soft-decision,
  ~1.5 dB), `--cfo-search 30000` (locks through real tuner PPM error). Both are on
  by default in the RX scripts. `--interleave` adds burst-error defence but must
  match on both ends.
- **Profile.** `HOBOCAST_PACKETS`, or edit `scripts/_config.sh`.

## Legal & safety

Same rules as the analog demo: keep the amp **off**, sessions short, indoors, no
external antenna. 906 MHz is ISM but arbitrary wideband digital there still isn't
blanket-legal — for a public venue prefer a direct coax feed + attenuator into the
receiver, no radiation.
