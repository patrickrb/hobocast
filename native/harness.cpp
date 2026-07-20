// Desktop verification harness for the C++ BOXCAR receiver.
//
//   boxcar_harness <capture.cu8|.cs8> <out.ts> [--cs8] [--fec] [--packets N]
//
// Reads an IQ capture produced by the Python `boxcar.cli tx`, decodes it with
// the pure-C++ receiver, and writes the reassembled transport stream. Compare
// out.ts against the source .ts to prove the port matches the Python reference
// byte-for-byte. Exits non-zero if nothing decoded.
#include "boxcar_rx.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace hobocast;

static std::vector<uint8_t> readFile(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return {};
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::vector<uint8_t> buf(n > 0 ? n : 0);
    if (n > 0 && fread(buf.data(), 1, n, f) != (size_t)n) buf.clear();
    fclose(f);
    return buf;
}

int main(int argc, char** argv) {
    if (argc < 3) {
        fprintf(stderr,
                "usage: %s <capture.cu8|.cs8> <out.ts> [--cs8] [--fec] [--packets N]\n",
                argv[0]);
        return 2;
    }
    const char* inPath = argv[1];
    const char* outPath = argv[2];
    bool cs8 = false;
    long chunk = 0;  // >0: stream via feed() in chunks of this many IQ samples
    Config cfg;
    for (int i = 3; i < argc; ++i) {
        if (!strcmp(argv[i], "--cs8")) cs8 = true;
        else if (!strcmp(argv[i], "--fec")) cfg.fec = true;
        else if (!strcmp(argv[i], "--soft")) cfg.soft = true;
        else if (!strcmp(argv[i], "--cfo-search") && i + 1 < argc)
            cfg.cfo_search_hz = atof(argv[++i]);
        else if (!strcmp(argv[i], "--packets") && i + 1 < argc)
            cfg.fec_payload = 188 * atoi(argv[++i]);
        else if (!strcmp(argv[i], "--chunk") && i + 1 < argc)
            chunk = atol(argv[++i]);
    }

    std::vector<uint8_t> raw = readFile(inPath);
    if (raw.empty()) { fprintf(stderr, "cannot read %s\n", inPath); return 2; }

    std::vector<cf> iq =
        cs8 ? fromCs8((const int8_t*)raw.data(), raw.size())
            : fromCu8(raw.data(), raw.size());

    BoxcarRx rx(cfg);
    std::vector<uint8_t> ts;
    if (chunk > 0) {
        // Stream the capture in small chunks, exactly as a live dongle delivers
        // it. Result must be byte-identical to the one-shot receiveStream().
        for (size_t off = 0; off < iq.size(); off += chunk) {
            size_t m = std::min((size_t)chunk, iq.size() - off);
            std::vector<uint8_t> part = rx.feed(iq.data() + off, m);
            ts.insert(ts.end(), part.begin(), part.end());
        }
        std::vector<uint8_t> tail = rx.flush();
        ts.insert(ts.end(), tail.begin(), tail.end());
    } else {
        ts = rx.receiveStream(iq);
    }
    const Stats& s = rx.stats();

    FILE* out = fopen(outPath, "wb");
    if (!out) { fprintf(stderr, "cannot write %s\n", outPath); return 2; }
    if (!ts.empty()) fwrite(ts.data(), 1, ts.size(), out);
    fclose(out);

    fprintf(stderr,
            "decoded %zu IQ samples | frames ok=%d dropped=%d | %zu bytes -> %s\n",
            iq.size(), s.framesOk, s.framesDropped, ts.size(), outPath);
    if (s.framesOk == 0) { fprintf(stderr, "FAIL: no frames decoded\n"); return 1; }
    fprintf(stderr, "OK\n");
    return 0;
}
