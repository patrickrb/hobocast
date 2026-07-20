#include "boxcar_rx.h"

#include <algorithm>
#include <cmath>

namespace hobocast {
namespace {

constexpr double PI = 3.14159265358979323846;

inline int popcount(unsigned x) {
    int c = 0;
    while (x) { x &= x - 1; ++c; }
    return c;
}

// --- CRC-32 (zlib / ISO-HDLC: poly 0xEDB88320, reflected) ------------------
uint32_t crc32(const uint8_t* p, size_t n) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; ++i) {
        crc ^= p[i];
        for (int b = 0; b < 8; ++b)
            crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1)));
    }
    return ~crc;
}

// --- root-raised-cosine taps (unit energy) — port of dsp.rrc_taps ----------
std::vector<double> rrcTaps(double beta, int sps, int span) {
    int n = span * sps;
    std::vector<double> h(n + 1);
    double energy = 0.0;
    for (int i = 0; i <= n; ++i) {
        double ti = (double(i) - n / 2.0) / sps;
        double v;
        if (std::fabs(ti) < 1e-8) {
            v = 1.0 - beta + 4.0 * beta / PI;
        } else if (beta > 0 &&
                   std::fabs(std::fabs(ti) - 1.0 / (4.0 * beta)) < 1e-8) {
            v = (beta / std::sqrt(2.0)) *
                ((1.0 + 2.0 / PI) * std::sin(PI / (4.0 * beta)) +
                 (1.0 - 2.0 / PI) * std::cos(PI / (4.0 * beta)));
        } else {
            double num = std::sin(PI * ti * (1.0 - beta)) +
                         4.0 * beta * ti * std::cos(PI * ti * (1.0 + beta));
            double den = PI * ti * (1.0 - std::pow(4.0 * beta * ti, 2));
            v = num / den;
        }
        h[i] = v;
        energy += v * v;
    }
    double norm = std::sqrt(energy);
    for (auto& x : h) x /= norm;
    return h;
}

// np.interp with endpoint clamping, over xp = 0,1,2,...,len-1.
double interp1(const std::vector<double>& fp, double pos) {
    if (pos <= 0.0) return fp.front();
    if (pos >= double(fp.size() - 1)) return fp.back();
    long i = (long)pos;
    double frac = pos - i;
    return fp[i] * (1.0 - frac) + fp[i + 1] * frac;
}

// Unwrap a phase sequence in place (numpy.unwrap semantics).
void unwrap(std::vector<double>& ph) {
    double prev = ph.empty() ? 0.0 : ph[0];
    double accum = 0.0;
    for (size_t i = 1; i < ph.size(); ++i) {
        double d = ph[i] - prev;
        prev = ph[i];
        while (d > PI) d -= 2.0 * PI;
        while (d < -PI) d += 2.0 * PI;
        accum += d;
        ph[i] = ph[0] + accum;
    }
}

// --- rate-1/2 K=7 (171,133) trellis, built once ----------------------------
struct Trellis {
    static constexpr int K = 7;
    static constexpr int STATES = 1 << (K - 1);  // 64
    static constexpr int TAIL = K - 1;           // 6
    int ns[STATES][2];        // next state
    int outb[STATES][2];      // 2-bit output symbol
    int predS[STATES][2];     // predecessor states
    int predU[STATES][2];     // input bit on that branch
    int predOut[STATES][2];   // expected 2-bit output on that branch

    static int parity(int x) { return popcount(x) & 1; }

    Trellis() {
        const int G0 = 0171, G1 = 0133;
        for (int s = 0; s < STATES; ++s)
            for (int u = 0; u < 2; ++u) {
                int reg = (u << 6) | s;
                outb[s][u] = (parity(reg & G0) << 1) | parity(reg & G1);
                ns[s][u] = ((s >> 1) | (u << 5)) & 0x3F;
            }
        int cnt[STATES] = {0};
        for (int s = 0; s < STATES; ++s)
            for (int u = 0; u < 2; ++u) {
                int d = ns[s][u];
                int k = cnt[d]++;
                predS[d][k] = s;
                predU[d][k] = u;
                predOut[d][k] = outb[s][u];
            }
    }
};

const Trellis TRELLIS;

inline int hamming2(int a, int b) { return popcount(a ^ b); }

// Hard-decision Viterbi decode; inverse of conv_encode, drops the tail.
// coded: 0/1 bits (length even). Returns decoded info bits.
std::vector<uint8_t> viterbiDecode(const std::vector<uint8_t>& coded) {
    const int S = Trellis::STATES;
    long t = (long)coded.size() / 2;
    std::vector<uint8_t> out;
    if (t == 0) return out;

    std::vector<double> pm(S, 1e9), pmNext(S);
    pm[0] = 0.0;
    std::vector<uint8_t> bp((size_t)t * S), bb((size_t)t * S);

    for (long i = 0; i < t; ++i) {
        int rx = (coded[2 * i] << 1) | coded[2 * i + 1];
        for (int d = 0; d < S; ++d) {
            double c0 = pm[TRELLIS.predS[d][0]] + hamming2(TRELLIS.predOut[d][0], rx);
            double c1 = pm[TRELLIS.predS[d][1]] + hamming2(TRELLIS.predOut[d][1], rx);
            int k = (c1 < c0) ? 1 : 0;
            pmNext[d] = k ? c1 : c0;
            bp[(size_t)i * S + d] = (uint8_t)TRELLIS.predS[d][k];
            bb[(size_t)i * S + d] = (uint8_t)TRELLIS.predU[d][k];
        }
        pm.swap(pmNext);
    }

    std::vector<uint8_t> bits((size_t)t);
    int s = 0;  // known terminating state
    for (long i = t - 1; i >= 0; --i) {
        bits[i] = bb[(size_t)i * S + s];
        s = bp[(size_t)i * S + s];
    }
    if (Trellis::TAIL && (long)bits.size() >= Trellis::TAIL)
        bits.resize(bits.size() - Trellis::TAIL);
    return bits;
}

// Soft-decision Viterbi: same trellis, but branch metrics come from the
// received QPSK amplitudes (real=first coded bit, imag=second) instead of
// hard-sliced bits. ~1.5 dB of coding gain; RX-only so the waveform is
// unchanged. Mirrors boxcar.fec.viterbi_decode_soft.
std::vector<uint8_t> viterbiDecodeSoft(const std::vector<cf>& syms) {
    const int S = Trellis::STATES;
    long t = (long)syms.size();
    std::vector<uint8_t> out;
    if (t == 0) return out;

    // Expected +/-1 amplitudes of the two coded bits for each 2-bit output o.
    static const double AMP0[4] = {1, 1, -1, -1};  // I: 1-2*(o>>1)
    static const double AMP1[4] = {1, -1, 1, -1};  // Q: 1-2*(o&1)

    std::vector<double> pm(S, 1e18), pmNext(S);
    pm[0] = 0.0;
    std::vector<uint8_t> bp((size_t)t * S), bb((size_t)t * S);

    for (long i = 0; i < t; ++i) {
        double y0 = syms[i].real(), y1 = syms[i].imag();
        double cost[4];
        for (int o = 0; o < 4; ++o) cost[o] = -(y0 * AMP0[o] + y1 * AMP1[o]);
        for (int d = 0; d < S; ++d) {
            double c0 = pm[TRELLIS.predS[d][0]] + cost[TRELLIS.predOut[d][0]];
            double c1 = pm[TRELLIS.predS[d][1]] + cost[TRELLIS.predOut[d][1]];
            int k = (c1 < c0) ? 1 : 0;
            pmNext[d] = k ? c1 : c0;
            bp[(size_t)i * S + d] = (uint8_t)TRELLIS.predS[d][k];
            bb[(size_t)i * S + d] = (uint8_t)TRELLIS.predU[d][k];
        }
        pm.swap(pmNext);
    }

    std::vector<uint8_t> bits((size_t)t);
    int s = 0;
    for (long i = t - 1; i >= 0; --i) {
        bits[i] = bb[(size_t)i * S + s];
        s = bp[(size_t)i * S + s];
    }
    if (Trellis::TAIL && (long)bits.size() >= Trellis::TAIL)
        bits.resize(bits.size() - Trellis::TAIL);
    return bits;
}

// --- bit/byte plumbing (MSB-first, matching numpy packbits/unpackbits) -----
std::vector<uint8_t> qpskToBits(const std::vector<cf>& sym) {
    std::vector<uint8_t> bits(sym.size() * 2);
    for (size_t i = 0; i < sym.size(); ++i) {
        bits[2 * i] = sym[i].real() < 0 ? 1 : 0;
        bits[2 * i + 1] = sym[i].imag() < 0 ? 1 : 0;
    }
    return bits;
}

std::vector<uint8_t> bitsToBytes(const std::vector<uint8_t>& bits) {
    std::vector<uint8_t> out(bits.size() / 8);
    for (size_t i = 0; i < out.size(); ++i) {
        uint8_t b = 0;
        for (int k = 0; k < 8; ++k) b = (b << 1) | (bits[8 * i + k] & 1);
        out[i] = b;
    }
    return out;
}

}  // namespace

// --- format converters -----------------------------------------------------
std::vector<cf> fromCu8(const uint8_t* buf, size_t nbytes) {
    size_t n = nbytes / 2;
    std::vector<cf> out(n);
    for (size_t i = 0; i < n; ++i)
        out[i] = cf(buf[2 * i] - 127.5, buf[2 * i + 1] - 127.5);
    return out;
}

std::vector<cf> fromCs8(const int8_t* buf, size_t nbytes) {
    size_t n = nbytes / 2;
    std::vector<cf> out(n);
    for (size_t i = 0; i < n; ++i)
        out[i] = cf(buf[2 * i], buf[2 * i + 1]);
    return out;
}

// --- receiver --------------------------------------------------------------
BoxcarRx::BoxcarRx(const Config& cfg) : cfg_(cfg) {
    taps_ = rrcTaps(cfg_.beta, cfg_.sps, cfg_.span);
    zc_.resize(cfg_.preamble_len);
    for (int n = 0; n < cfg_.preamble_len; ++n) {
        double ang = -PI * cfg_.zc_root * double(n) * double(n) / cfg_.preamble_len;
        zc_[n] = std::polar(1.0, ang);
    }
}

// Full convolution (np.convolve 'full'): out length = len(rx)+len(taps)-1.
std::vector<cf> BoxcarRx::matchedFilter(const std::vector<cf>& rx) const {
    size_t nt = taps_.size(), nr = rx.size();
    std::vector<cf> mf(nr + nt - 1, cf(0, 0));
    for (size_t k = 0; k < nr; ++k) {
        cf r = rx[k];
        if (r == cf(0, 0)) continue;
        for (size_t j = 0; j < nt; ++j) mf[k + j] += r * taps_[j];
    }
    return mf;
}

std::vector<cf> BoxcarRx::sampleSymbols(const std::vector<cf>& mf, double kf,
                                        int count) const {
    // np.interp over real and imag independently. Build the axis lazily via
    // interp1, which clamps at the endpoints exactly as numpy does.
    std::vector<cf> out(count);
    // interp1 needs contiguous real/imag; extract once.
    static thread_local std::vector<double> re, im;
    if (re.size() != mf.size()) { re.resize(mf.size()); im.resize(mf.size()); }
    for (size_t i = 0; i < mf.size(); ++i) { re[i] = mf[i].real(); im[i] = mf[i].imag(); }
    for (int i = 0; i < count; ++i) {
        double pos = kf + double(i) * cfg_.sps;
        out[i] = cf(interp1(re, pos), interp1(im, pos));
    }
    return out;
}

BoxcarRx::Acq BoxcarRx::acquire(const std::vector<cf>& mf, long start,
                                long search) const {
    int P = cfg_.preamble_len, sps = cfg_.sps;
    long room = (long)mf.size() - start - (long)P * sps;
    if (search < 0) search = room; else search = std::min(search, room);
    if (search <= 0) return {0, 0, 0, 0, false};

    std::vector<double> mag(search);
    if (cfg_.cfo_search_hz > 0.0) {
        // Coarse carrier search: a Zadoff-Chu correlation couples frequency to
        // timing, so an uncorrected offset (real tuner PPM error, ~27 kHz at
        // 906 MHz) shifts the peak and wrecks the phase fit. Sweep trial offsets
        // folded into the reference; the strongest peak un-shifts the timing.
        // (Mirrors boxcar.modem._acquire.) On the phone this is the difference
        // between locking and never locking.
        double df = 0.5 * cfg_.fs / (P * sps);
        double best = -1.0;
        std::vector<cf> reff(P);
        std::vector<double> m(search);
        for (double f = -cfg_.cfo_search_hz; f <= cfg_.cfo_search_hz + df / 2; f += df) {
            for (int p = 0; p < P; ++p)
                reff[p] = std::conj(zc_[p]) *
                          std::polar(1.0, -2.0 * PI * f * (double)(p * sps) / cfg_.fs);
            double peak = -1.0;
            for (long k = 0; k < search; ++k) {
                cf acc(0, 0);
                for (int p = 0; p < P; ++p) acc += reff[p] * mf[start + k + (long)p * sps];
                m[k] = std::abs(acc);
                if (m[k] > peak) peak = m[k];
            }
            if (peak > best) { best = peak; mag = m; }
        }
    } else {
        for (long k = 0; k < search; ++k) {
            cf acc(0, 0);
            for (int p = 0; p < P; ++p)
                acc += std::conj(zc_[p]) * mf[start + k + (long)p * sps];
            mag[k] = std::abs(acc);
        }
    }
    long k0 = (long)(std::max_element(mag.begin(), mag.end()) - mag.begin());

    std::vector<double> sorted = mag;
    std::nth_element(sorted.begin(), sorted.begin() + sorted.size() / 2, sorted.end());
    double median = sorted[sorted.size() / 2];
    if (sorted.size() % 2 == 0) {
        double lo = *std::max_element(sorted.begin(), sorted.begin() + sorted.size() / 2);
        median = 0.5 * (median + lo);
    }
    double ratio = mag[k0] / (median + 1e-12);

    double delta = 0.0;
    if (k0 >= 1 && k0 < search - 1) {
        double ym1 = mag[k0 - 1], y0 = mag[k0], yp1 = mag[k0 + 1];
        double denom = ym1 - 2.0 * y0 + yp1;
        if (denom != 0.0) delta = 0.5 * (ym1 - yp1) / denom;
    }
    double kf = double(start + k0) + delta;

    // Linear phase fit of the de-rotated preamble seeds the tracking loop.
    std::vector<cf> pre = sampleSymbols(mf, kf, P);
    std::vector<double> ph(P);
    for (int i = 0; i < P; ++i) ph[i] = std::arg(pre[i] * std::conj(zc_[i]));
    unwrap(ph);
    double meanN = (P - 1) / 2.0, meanPh = 0.0;
    for (int i = 0; i < P; ++i) meanPh += ph[i];
    meanPh /= P;
    double sxy = 0.0, sxx = 0.0;
    for (int i = 0; i < P; ++i) {
        double dn = i - meanN;
        sxy += dn * (ph[i] - meanPh);
        sxx += dn * dn;
    }
    double omega = sxx != 0.0 ? sxy / sxx : 0.0;
    double phi0 = meanPh - omega * meanN;
    return {kf, phi0, omega, ratio, true};
}

std::vector<cf> BoxcarRx::demodData(const std::vector<cf>& mf, double kf,
                                    double phi0, double omega, long nSyms) const {
    int P = cfg_.preamble_len, sps = cfg_.sps;
    long avail = (long)std::floor((double(mf.size()) - kf - 1) / sps) - P;
    nSyms = std::min(nSyms, std::max(0L, avail));
    if (nSyms <= 0) return {};
    std::vector<cf> data = sampleSymbols(mf, kf + (double)P * sps, (int)nSyms);

    double phi = phi0 + omega * P;
    double freq = omega;
    const double alpha = 0.05, betaPll = 0.001, inv = std::sqrt(2.0);
    std::vector<cf> out(nSyms);
    for (long i = 0; i < nSyms; ++i) {
        cf c = data[i] * std::polar(1.0, -phi);
        out[i] = c;
        cf d((c.real() >= 0 ? 1.0 : -1.0) / inv, (c.imag() >= 0 ? 1.0 : -1.0) / inv);
        double err = std::arg(c * std::conj(d));
        phi += freq + alpha * err;
        freq += betaPll * err;
    }
    return out;
}

long BoxcarRx::peekLength(const std::vector<cf>& mf, double kf, double phi0,
                          double omega) const {
    int P = cfg_.preamble_len;
    std::vector<cf> sym = sampleSymbols(mf, kf + (double)P * cfg_.sps, 16);
    std::vector<cf> corr(16);
    for (int i = 0; i < 16; ++i)
        corr[i] = sym[i] * std::polar(1.0, -(phi0 + omega * (P + i)));
    std::vector<uint8_t> bytes = bitsToBytes(qpskToBits(corr));
    long v = 0;
    for (int i = 0; i < 4; ++i) v = (v << 8) | bytes[i];
    return v;
}

// Streaming matched filter: each raw IQ sample yields one mf sample via a
// gather over the last taps_.size() raw samples. Reproduces np.convolve 'full'
// output indices 0..R-1 after R raw samples (the trailing taps-1 tail only
// finalizes at true end-of-stream, which a live receiver never needs).
void BoxcarRx::appendMatched(const cf* rx, size_t n) {
    long nt = (long)taps_.size();
    if ((long)ring_.size() != nt) ring_.assign(nt, cf(0, 0));
    for (size_t s = 0; s < n; ++s) {
        ring_[rawSeen_ % nt] = rx[s];
        cf m(0, 0);
        for (long j = 0; j < nt && rawSeen_ - j >= 0; ++j)
            m += taps_[j] * ring_[(rawSeen_ - j) % nt];
        sbuf_.push_back(m);
        ++rawSeen_;
    }
}

// Decode every frame fully contained in the current buffer. When !flush we only
// commit to a frame once a full acquisition window (and the whole frame) is
// buffered, so the decision is identical to what receiveStream would make with
// the complete signal in hand. flush() relaxes that at true end-of-stream.
void BoxcarRx::drainInto(std::vector<uint8_t>& ts, bool flush) {
    int P = cfg_.preamble_len, sps = cfg_.sps;
    const long search = 4096;
    const double minRatio = 4.0;
    int size = cfg_.fec_payload;

    long codedSyms = cfg_.fec ? (long)(2 + size + 4) * 8 + Trellis::TAIL : 0;
    long frameSyms0 = cfg_.fec ? codedSyms : (long)(8 + 0) * 4;
    long minFrame = (long)(P + frameSyms0) * sps;

    for (;;) {
        long rel = sCur_ - sBase_;
        long room = (long)sbuf_.size() - rel;
        if (room < minFrame) break;
        // Wait for a full search window before committing (unless flushing), so
        // acquisition sees the same neighbourhood the batch decoder would.
        if (!flush && room < search + minFrame) break;

        Acq a = acquire(sbuf_, rel, search);
        if (!a.ok) break;
        if (a.ratio < minRatio) {           // no preamble in this window
            if (flush) break;               // ...and no more data coming -> done
            sCur_ += search;                // ...otherwise skip the quiet window
            continue;
        }

        if (cfg_.fec) {
            long frameEnd = (long)(a.kf + (double)(P + codedSyms) * sps);
            if (frameEnd + 2 > (long)sbuf_.size()) { if (!flush) break; else break; }
            std::vector<cf> out = demodData(sbuf_, a.kf, a.phi0, a.omega, codedSyms);
            std::vector<uint8_t> info =
                cfg_.soft ? viterbiDecodeSoft(out) : viterbiDecode(qpskToBits(out));
            std::vector<uint8_t> data = bitsToBytes(info);
            sCur_ = sBase_ + frameEnd;
            if ((long)data.size() >= 2 + size + 4) {
                long length = (data[0] << 8) | data[1];
                uint32_t crcRx = ((uint32_t)data[2 + size] << 24) |
                                 ((uint32_t)data[3 + size] << 16) |
                                 ((uint32_t)data[4 + size] << 8) | data[5 + size];
                if (length <= size && crc32(data.data(), 2 + size) == crcRx) {
                    ts.insert(ts.end(), data.begin() + 2, data.begin() + 2 + length);
                    stats_.framesOk++;
                } else {
                    stats_.framesDropped++;
                }
            } else {
                stats_.framesDropped++;
            }
        } else {
            long length = peekLength(sbuf_, a.kf, a.phi0, a.omega);
            if (length < 0 || length > 10'000'000) {
                sCur_ = sBase_ + (long)(a.kf + (double)P * sps) + 1;
                continue;
            }
            long dSyms = (long)(8 + length) * 4;
            long frameEnd = (long)(a.kf + (double)(P + dSyms) * sps);
            if (frameEnd + 2 > (long)sbuf_.size()) { if (!flush) break; else break; }
            std::vector<cf> out = demodData(sbuf_, a.kf, a.phi0, a.omega, dSyms);
            std::vector<uint8_t> data = bitsToBytes(qpskToBits(out));
            sCur_ = sBase_ + frameEnd;
            if ((long)data.size() >= 8) {
                long len2 = ((long)data[0] << 24) | ((long)data[1] << 16) |
                            ((long)data[2] << 8) | data[3];
                if (len2 <= (long)data.size() - 8) {
                    uint32_t crcRx = ((uint32_t)data[4 + len2] << 24) |
                                     ((uint32_t)data[5 + len2] << 16) |
                                     ((uint32_t)data[6 + len2] << 8) | data[7 + len2];
                    if (crc32(data.data(), 4 + len2) == crcRx) {
                        ts.insert(ts.end(), data.begin() + 4, data.begin() + 4 + len2);
                        stats_.framesOk++;
                    } else {
                        stats_.framesDropped++;
                    }
                } else {
                    stats_.framesDropped++;
                }
            } else {
                stats_.framesDropped++;
            }
        }

        // Compact: drop everything before the cursor once it's grown enough.
        long newRel = sCur_ - sBase_;
        if (newRel > 65536) {
            sbuf_.erase(sbuf_.begin(), sbuf_.begin() + newRel);
            sBase_ = sCur_;
        }
    }
}

std::vector<uint8_t> BoxcarRx::feed(const cf* rx, size_t n) {
    appendMatched(rx, n);
    std::vector<uint8_t> ts;
    drainInto(ts, /*flush=*/false);
    return ts;
}

std::vector<uint8_t> BoxcarRx::flush() {
    std::vector<uint8_t> ts;
    drainInto(ts, /*flush=*/true);
    return ts;
}

std::vector<uint8_t> BoxcarRx::receiveStream(const std::vector<cf>& rx) {
    // One-shot decode = a single feed of the whole capture, then flush. Sharing
    // the streaming path guarantees the two can't drift apart.
    stats_ = Stats{};
    sbuf_.clear(); ring_.clear();
    sBase_ = sCur_ = rawSeen_ = 0;
    std::vector<uint8_t> ts = feed(rx.data(), rx.size());
    std::vector<uint8_t> tail = flush();
    ts.insert(ts.end(), tail.begin(), tail.end());
    return ts;
}

}  // namespace hobocast
