"""BOXCAR command-line tool — modulate/demodulate to real SDR IQ file formats.

    # transmit a file as an IQ burst you can hand to a HackRF:
    python -m boxcar.cli tx video.ts tx.cs8 --fmt cs8 --fec
    hackrf_transfer -t tx.cs8 -f 906000000 -s 2400000 -a 1 -x 20

    # receive from an RTL-SDR capture:
    rtl_sdr -f 906000000 -s 2400000 -g 40 capture.cu8
    python -m boxcar.cli rx capture.cu8 out.ts --fmt cu8 --fec

The IQ formats (cu8/cs8) are exactly what `rtl_sdr` and `hackrf_transfer` speak,
so BOXCAR drops into a real hardware chain with no glue.
"""

import argparse
import sys

from .modem import Config
from .sdr_io import read_iq, write_iq
from .stream import frames_to_ts, modulate_stream, receive_stream, ts_to_frames


def _cfg(args) -> Config:
    return Config(fec=args.fec, fec_payload=188 * args.packets)


def cmd_tx(args) -> int:
    data = open(args.input, "rb").read()
    cfg = _cfg(args)
    frames = ts_to_frames(data, args.packets)
    iq = modulate_stream(frames, cfg)
    write_iq(args.output, iq, args.fmt)
    print(f"tx: {len(data)} bytes -> {len(frames)} frames -> {len(iq)} IQ samples "
          f"-> {args.output} ({args.fmt}, fec={'on' if args.fec else 'off'})")
    print(f"    hackrf_transfer -t {args.output} -f 906000000 -s "
          f"{int(cfg.fs)} -a 1 -x 20")
    return 0


def cmd_rx(args) -> int:
    cfg = _cfg(args)
    iq = read_iq(args.input, args.fmt)
    got = receive_stream(iq, cfg)
    good = [p for p in got if p is not None]
    ts = frames_to_ts([p if p is not None else b"" for p in got])
    with open(args.output, "wb") as f:
        f.write(ts)
    print(f"rx: {len(iq)} IQ samples -> {len(good)}/{len(got)} frames "
          f"({len(got) - len(good)} CRC drops) -> {len(ts)} bytes -> {args.output}")
    return 0 if good else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="boxcar", description="BOXCAR digital-TV modem")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--fmt", choices=["cu8", "cs8"], default="cu8",
                        help="IQ byte format (cu8=RTL-SDR, cs8=HackRF)")
    common.add_argument("--fec", action="store_true", help="rate-1/2 FEC")
    common.add_argument("--packets", type=int, default=7,
                        help="TS packets per frame (payload size)")

    tx = sub.add_parser("tx", parents=[common], help="file -> IQ")
    tx.add_argument("input"); tx.add_argument("output"); tx.set_defaults(func=cmd_tx)

    rx = sub.add_parser("rx", parents=[common], help="IQ -> file")
    rx.add_argument("input"); rx.add_argument("output"); rx.set_defaults(func=cmd_rx)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
