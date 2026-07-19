"""Forward error correction: rate-1/2, K=7 convolutional code with Viterbi decode.

This is the classic (171,133) octal code (constraint length 7, free distance 10)
used everywhere from Voyager to 802.11 to DVB. It roughly halves the raw bitrate
but buys several dB of coding gain — turning the ragged ~1e-2 bit error rate at a
cell edge into clean, decodable video.

Encoder and decoder are built from the SAME trellis tables, so they're guaranteed
consistent regardless of bit-ordering conventions. The decoder is hard-decision
and vectorised across the 64 states for speed.
"""

import numpy as np

K = 7                    # constraint length
STATES = 1 << (K - 1)    # 64
G0 = 0o171
G1 = 0o133
TAIL = K - 1             # zero-flush bits to terminate the trellis in state 0


def _parity(x: int) -> int:
    return bin(x).count("1") & 1


def _build_trellis():
    ns = np.zeros((STATES, 2), dtype=np.int64)   # next state
    out = np.zeros((STATES, 2), dtype=np.int64)  # 2-bit output symbol (o0<<1|o1)
    for s in range(STATES):
        for u in range(2):
            reg = (u << 6) | s               # current bit in MSB, 6-bit history below
            out[s, u] = (_parity(reg & G0) << 1) | _parity(reg & G1)
            ns[s, u] = ((s >> 1) | (u << 5)) & 0x3F
    # Each state has exactly two predecessors; tabulate them for the ACS step.
    pred_s = np.zeros((STATES, 2), dtype=np.int64)
    pred_u = np.zeros((STATES, 2), dtype=np.int64)
    cnt = np.zeros(STATES, dtype=np.int64)
    for s in range(STATES):
        for u in range(2):
            d = ns[s, u]
            k = cnt[d]
            pred_s[d, k] = s
            pred_u[d, k] = u
            cnt[d] += 1
    pred_out = out[pred_s, pred_u]  # expected output symbol on each incoming branch
    return ns, out, pred_s, pred_u, pred_out


_NS, _OUT, _PRED_S, _PRED_U, _PRED_OUT = _build_trellis()
# Hamming distance between two 2-bit symbols.
_HAM = np.array([[bin(a ^ b).count("1") for b in range(4)] for a in range(4)])


def coded_symbol_count(n_info_bits: int) -> int:
    """QPSK data symbols produced for n_info_bits after coding (2 coded bits/sym)."""
    return n_info_bits + TAIL  # (n+TAIL) info+tail bits -> 2x coded bits -> /2 per QPSK


def conv_encode(bits: np.ndarray) -> np.ndarray:
    """Rate-1/2 encode a bit array (0/1), zero-terminated. Returns 2*(len+TAIL) bits."""
    bits = np.concatenate([np.asarray(bits, dtype=np.uint8), np.zeros(TAIL, dtype=np.uint8)])
    out = np.empty(len(bits) * 2, dtype=np.uint8)
    s = 0
    for i, u in enumerate(bits):
        o = _OUT[s, u]
        out[2 * i] = o >> 1
        out[2 * i + 1] = o & 1
        s = _NS[s, u]
    return out


def viterbi_decode(coded: np.ndarray) -> np.ndarray:
    """Hard-decision Viterbi decode; inverse of conv_encode (drops the tail)."""
    coded = np.asarray(coded, dtype=np.int64)
    t = len(coded) // 2
    if t == 0:
        return np.zeros(0, dtype=np.uint8)
    rx = (coded[0:2 * t:2] << 1) | coded[1:2 * t:2]  # received 2-bit symbols

    pm = np.full(STATES, 1e9)
    pm[0] = 0.0
    bp = np.empty((t, STATES), dtype=np.int64)  # chosen predecessor state
    bb = np.empty((t, STATES), dtype=np.uint8)  # input bit into this state
    ar = np.arange(STATES)

    for i in range(t):
        bm = _HAM[_PRED_OUT, rx[i]]        # (STATES,2) branch metrics
        cand = pm[_PRED_S] + bm            # (STATES,2)
        choice = np.argmin(cand, axis=1)
        pm = cand[ar, choice]
        bp[i] = _PRED_S[ar, choice]
        bb[i] = _PRED_U[ar, choice]

    # Traceback from the known terminating state 0.
    s = 0
    bits = np.empty(t, dtype=np.uint8)
    for i in range(t - 1, -1, -1):
        bits[i] = bb[i, s]
        s = bp[i, s]
    return bits[:-TAIL] if TAIL else bits
