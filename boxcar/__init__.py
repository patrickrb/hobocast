"""BOXCAR — a narrowband digital TV waveform that fits inside a $30 RTL-SDR.

The whole point of hobocast: analog NTSC can't carry color to an RTL-SDR (the
3.58 MHz chroma subcarrier falls outside the dongle's ~2.4 MHz window). Go
digital instead — since *we* own the transmitter, we design a signal that fits.
A QPSK link at fs/sps symbols/s carries an MPEG-TS of H.264 color video + AAC
audio in well under 2.4 MHz. Color and sound stop being an RF problem and become
"just bytes."

This package is the pure-Python reference modem: a real TX -> channel -> RX
loopback you can run with no radio attached. See demos/loopback.py.
"""

from .modem import Config, modulate, receive, receive_symbols
from .channel import apply_channel
from .stream import (
    frames_to_ts,
    modulate_stream,
    modulate_stream_iter,
    receive_stream,
    ts_to_frames,
)
from .sdr_io import from_cs8, from_cu8, read_iq, to_cs8, to_cu8, write_iq

__all__ = [
    "Config",
    "modulate",
    "receive",
    "receive_symbols",
    "apply_channel",
    "modulate_stream",
    "modulate_stream_iter",
    "receive_stream",
    "ts_to_frames",
    "frames_to_ts",
    "to_cu8",
    "from_cu8",
    "to_cs8",
    "from_cs8",
    "read_iq",
    "write_iq",
]
