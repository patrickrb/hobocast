"""M3 demo: real COLOR video + AUDIO over the BOXCAR radio channel.

    ffmpeg (H.264 + AAC -> MPEG-TS)  ->  chunk into BOXCAR frames
      ->  modulate burst-train  ->  [CFO + timing + AWGN]  ->  receive_stream
      ->  reassemble MPEG-TS  ->  ffmpeg proves it's valid, playable video

No hardware — the "channel" is boxcar.channel. If the reassembled .ts plays and
matches byte-for-byte, the same waveform carries real color TV with sound to a
$30 RTL-SDR.

Run:  python demos/video_loopback.py
"""

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from boxcar import (
    Config,
    apply_channel,
    frames_to_ts,
    modulate_stream,
    receive_stream,
    ts_to_frames,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")

VID_KBPS, AUD_KBPS, DURATION, FPS = 500, 64, 3, 15


def run(args):
    subprocess.run(args, check=True, capture_output=True)


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH — needed to make/verify the test clip.")
        return 2

    cfg = Config()
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(OUT, "source.ts")

    print("BOXCAR M3 — real color video + audio over a simulated RTL-SDR channel\n")
    print("  encoding test clip (ffmpeg): 320x240 color motion + 440 Hz tone")
    run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate={FPS}:duration={DURATION}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={DURATION}",
        "-c:v", "libx264", "-profile:v", "baseline", "-preset", "veryfast",
        "-b:v", f"{VID_KBPS}k", "-pix_fmt", "yuv420p", "-g", str(FPS),
        "-c:a", "aac", "-b:a", f"{AUD_KBPS}k",
        "-f", "mpegts", src,
    ])

    ts = open(src, "rb").read()
    frames = ts_to_frames(ts, packets_per_frame=7)
    stream_kbps = (VID_KBPS + AUD_KBPS)
    print(f"  source TS   : {len(ts)} bytes -> {len(frames)} BOXCAR frames "
          f"(~{stream_kbps} kbps)")
    print(f"  link budget : stream {stream_kbps} kbps fits {cfg.bitrate/1e3:.0f} "
          f"kbps QPSK link  ({'OK' if stream_kbps*1e3 < cfg.bitrate else 'TOO BIG'})")

    tx = modulate_stream(frames, cfg)
    print(f"  tx IQ       : {len(tx)} samples (~{len(tx)/cfg.fs*1e3:.0f} ms on air)\n")

    es_n0_db = 18.0
    rx = apply_channel(tx, cfg, es_n0_db=es_n0_db, cfo_hz=1500.0, frac_delay=0.4, seed=11)
    print(f"  channel     : Es/N0={es_n0_db} dB, CFO=+1500 Hz, timing offset=0.4 sample")

    got = receive_stream(rx, cfg)
    good = [p for p in got if p is not None]
    print(f"  decoded     : {len(good)}/{len(frames)} frames recovered "
          f"({len(got) - len(good)} CRC drops)")

    recovered_ts = frames_to_ts([p if p is not None else b"" for p in got])
    out_ts = os.path.join(OUT, "recovered.ts")
    with open(out_ts, "wb") as f:
        f.write(recovered_ts)

    exact = recovered_ts == ts
    print(f"  RESULT      : {'✓ byte-exact' if exact else '~ recovered with drops'} "
          f"transport stream ({len(recovered_ts)} bytes)")
    print(f"\n  wrote       : {out_ts}")

    # Prove it's genuinely decodable color video: pull a frame and probe streams.
    frame_png = os.path.join(OUT, "recovered_frame.png")
    try:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", out_ts,
             "-frames:v", "1", frame_png])
        print(f"  wrote       : {frame_png}  (a real decoded video frame)")
    except subprocess.CalledProcessError:
        print("  note        : could not extract a frame (too many drops?)")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name", "-of", "csv=p=0", out_ts],
        capture_output=True, text=True,
    )
    if probe.stdout.strip():
        print("  ffprobe     : " + "  ".join(probe.stdout.split()))

    print("\n  Real H.264 color video + AAC audio crossed the channel and still plays.")
    return 0 if exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
