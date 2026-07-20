// BOXCAR digital-TV receiver — pure C++ port of the Python reference in
// boxcar/. No platform dependencies, so it builds identically for the desktop
// verification harness and the Android NDK library (mirrors the layout of
// hobocon-app's :tv-sdr ntsc_demod).
//
// The receiver is data-aided QPSK: RRC matched filter -> Zadoff-Chu preamble
// acquisition (correlate, parabolic sub-sample timing, linear phase fit) ->
// decision-directed 2nd-order carrier PLL -> QPSK slice -> (optional) rate-1/2
// Viterbi -> CRC-checked frames -> reassembled MPEG-TS.
//
// It is verified byte-exact against the Python modem: Python `boxcar.cli tx`
// writes a .cu8, this decodes it, and the bytes match the source .ts. See
// native/harness.cpp.
#pragma once

#include <complex>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace hobocast {

using cf = std::complex<double>;

struct Config {
    double fs = 2'400'000.0;  // capture rate (Hz)
    int sps = 4;              // samples per symbol
    double beta = 0.35;       // RRC rolloff
    int span = 8;             // RRC length in symbols
    int preamble_len = 64;    // Zadoff-Chu preamble length (symbols)
    int zc_root = 25;         // ZC root
    bool fec = false;         // rate-1/2 convolutional coding
    int fec_payload = 1316;   // fixed payload bytes per coded frame
};

struct Stats {
    int framesOk = 0;       // frames that passed CRC
    int framesDropped = 0;  // frames acquired but failed CRC
};

// Convert the raw 8-bit interleaved IQ a dongle delivers into complex baseband.
std::vector<cf> fromCu8(const uint8_t* buf, size_t nbytes);  // RTL-SDR unsigned
std::vector<cf> fromCs8(const int8_t* buf, size_t nbytes);   // HackRF signed

class BoxcarRx {
public:
    explicit BoxcarRx(const Config& cfg);

    // Decode a whole burst-train capture into the reassembled transport stream.
    // Frames that fail CRC are skipped (and counted in stats); this mirrors
    // boxcar.stream.receive_stream + frames_to_ts with CRC drops dropped.
    std::vector<uint8_t> receiveStream(const std::vector<cf>& rx);

    const Stats& stats() const { return stats_; }

private:
    Config cfg_;
    Stats stats_;
    std::vector<double> taps_;  // RRC matched filter
    std::vector<cf> zc_;        // preamble reference

    struct Acq { double kf; double phi0; double omega; double ratio; bool ok; };

    std::vector<cf> matchedFilter(const std::vector<cf>& rx) const;
    Acq acquire(const std::vector<cf>& mf, long start, long search) const;
    std::vector<cf> sampleSymbols(const std::vector<cf>& mf, double kf,
                                  int count) const;
    std::vector<cf> demodData(const std::vector<cf>& mf, double kf, double phi0,
                              double omega, long nSyms) const;
    long peekLength(const std::vector<cf>& mf, double kf, double phi0,
                    double omega) const;
};

}  // namespace hobocast
