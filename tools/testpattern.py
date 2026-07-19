"""Generate a color test pattern as raw PPM (P6) bytes — no image libraries needed.

PPM is trivial and uncompressed; it stands in for "an MPEG-TS chunk of color
video" in the loopback demo. The point is only to prove that arbitrary color
image bytes survive the BOXCAR radio channel intact.
"""

import numpy as np

# SMPTE-ish 75% color bars, top to bottom order left-to-right.
_BARS = np.array(
    [
        [192, 192, 192],  # gray
        [192, 192, 0],    # yellow
        [0, 192, 192],    # cyan
        [0, 192, 0],      # green
        [192, 0, 192],    # magenta
        [192, 0, 0],      # red
        [0, 0, 192],      # blue
        [0, 0, 0],        # black
    ],
    dtype=np.uint8,
)


def color_bars(width: int = 160, height: int = 100) -> bytes:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for i in range(8):
        img[:, i * width // 8 : (i + 1) * width // 8] = _BARS[i]
    # A little gradient strip along the bottom quarter so it's not just flat bars.
    grad = np.linspace(0, 255, width, dtype=np.uint8)
    img[3 * height // 4 :, :, :] = grad[None, :, None]
    header = f"P6\n{width} {height}\n255\n".encode()
    return header + img.tobytes()


if __name__ == "__main__":
    import sys

    sys.stdout.buffer.write(color_bars())
