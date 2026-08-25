// quad2d.cpp — Stage 1 (integration) for 2-D chaotic attractors.
//
// Original author: Felix Meli (felnx) — <felnx@users.noreply.github.com>
//
// License: MIT — see LICENSE.
//
// Adapted/inspired by:
//   * Paul Bourke's Lyapunov attractor generator (gen.c) —
//     http://local.wasp.uwa.edu.au/~pbourke/fractals/lyapunov/
//     (the 12-coefficient 2-D quadratic family + Lyapunov-exponent
//      validation used in the "polynomial" family here)
//   * Johan Bichel Lindegaard's Python port of that generator
//     (fractal.py in this repo, http://johan.cc)
//   * Paul Richards' Clifford-attractor animation (main.cpp), published at
//     http://paulbourke.net/fractals/clifford/paul_richards/main.cpp
//     (source of the "clifford" family + the standalone clifford.cpp)
//
// Two families (selected with --family, default polynomial):
//
//   polynomial (fractal.py / Paul Bourke family; 12 coefficients):
//     x' = a0 + a1*x + a2*x^2 + a3*x*y + a4*y + a5*y^2
//     y' = b0 + b1*x + b2*x^2 + b3*x*y + b4*y + b5*y^2
//
//   clifford (8 parameters p0..p7, p0..p3 = a[], p4..p7 = b[]):
//     x' = a[0]*sin(a[1]*y) + a[2]*cos(a[3]*x)
//     y' = b[0]*sin(b[1]*x) + b[2]*cos(b[3]*y)
//
// Reads one or more param files (same format fractal.py writes, with the
// parameter line count set by the family):
//   line 1 : xmin ymin xmax ymax [sx sy]
//            (sx sy = optional start point on the attractor; defaults to 0 0)
//   lines 2..7 : a[i] b[i]   (i=0..5 for polynomial)
//   lines 2..5 : a[i] b[i]   (i=0..3 for clifford)
//
// For each file: integrates a long orbit, accumulates a per-cell pass count in
// a 32-bit float density grid (raw occupancy histogram — NO tone curve here),
// then writes the raw grid to  <base>.raw  (binary: 2 int32 W,H then W*H floats)
// and prints density stats so the tone map can be tuned separately (in Python).
//
// Build: g++ -O2 -o quad2d quad2d.cpp
// Run:   ./quad2d output/684.txt [output/260.txt ...] [ITERS]
//   or:  ./quad2d --target 1600 --iters 20000000 --family clifford \
//               --raw out.raw 684.txt
//   --target N    long side of the density grid in pixels (default 900)
//   --iters N     orbit length (default 20000000; also accepted as the last
//                 positional number, legacy style)
//   --family F    polynomial (default) or clifford
//   --raw PATH    where to write the binary grid (default: <input>.raw next
//                 to the input file; only usable with a single input file)

#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cstring>
#include <vector>
#include <string>
#include <algorithm>

#ifndef DEFAULT_ITERS
#define DEFAULT_ITERS 20000000
#endif
#ifndef TARGET
#define TARGET 900   // target pixel size of the longer canvas side
#endif
#ifndef MARGIN
#define MARGIN 1.10  // expand bounding box by this factor (white margin)
#endif

struct P { double xmin,ymin,xmax,ymax; double a[6], b[6]; double sx, sy;
           const char *family; };

static bool readParam(const char *path, const char *family, P &p) {
    FILE *f = fopen(path, "rb");
    if (!f) { printf("cannot open %s\n", path); return false; }
    p.family = family;
    if (fscanf(f, "%lf%lf%lf%lf", &p.xmin,&p.ymin,&p.xmax,&p.ymax) != 4) { fclose(f); return false; }
    p.sx = p.sy = 0.0;
    if (fscanf(f, "%lf %lf", &p.sx, &p.sy) != 2) { /* keep defaults */ }
    int n = strcmp(family, "clifford") == 0 ? 4 : 6;
    for (int i = 0; i < n; i++) { if (fscanf(f, "%lf %lf", &p.a[i], &p.b[i]) != 2) { fclose(f); return false; } }
    fclose(f);
    return true;
}

static std::string baseOf(const char *path) {
    std::string s(path);
    size_t slash = s.find_last_of('/');
    std::string name = (slash == std::string::npos) ? s : s.substr(slash + 1);
    size_t dot = name.find_last_of('.');
    if (dot != std::string::npos) name = name.substr(0, dot);
    std::string dir = (slash == std::string::npos) ? std::string(".") : s.substr(0, slash);
    return dir + "/" + name;
}

static void integrate(const P &p, int W, int H, long long iters, std::vector<float> &grid, long long &kept, long long &disc,
                      double &tmnx, double &tmxx, double &tmny, double &tmxy, long long &outbox) {
    kept = disc = outbox = 0;
    tmnx = tmny = 1e100; tmxx = tmxy = -1e100;
    double x = p.sx, y = p.sy;
    const double bw = p.xmax - p.xmin, bh = p.ymax - p.ymin;
    const double cx = (p.xmin + p.xmax) * 0.5, cy = (p.ymin + p.ymax) * 0.5;
    const double hw = bw * MARGIN * 0.5, hh = bh * MARGIN * 0.5;
    const double lox = cx - hw, loy = cy - hh, hix = cx + hw, hiy = cy + hh;
    const double invw = 1.0 / (hix - lox), invh = 1.0 / (hiy - loy);
    for (long long i = 0; i < iters; i++) {
        double xn, yn;
        if (p.family[0] == 'c') {  // clifford
            xn = p.a[0]*sin(p.a[1]*y) + p.a[2]*cos(p.a[3]*x);
            yn = p.b[0]*sin(p.b[1]*x) + p.b[2]*cos(p.b[3]*y);
        } else {                    // polynomial (fractal.py family)
            double xx = x*x, yy = y*y, xy = x*y;
            xn = p.a[0] + p.a[1]*x + p.a[2]*xx + p.a[3]*xy + p.a[4]*y + p.a[5]*yy;
            yn = p.b[0] + p.b[1]*x + p.b[2]*xx + p.b[3]*xy + p.b[4]*y + p.b[5]*yy;
        }
        x = xn; y = yn;
        if (x != x || y != y || x < -1e10 || x > 1e10 || y < -1e10 || y > 1e10) {
            disc++;
            if (disc > 1000000) { printf("  diverged\n"); break; }
            x = 0.0; y = 0.0;
            continue;
        }
        if (i < 10000) continue; // discard transient
        if (x < tmnx) tmnx = x;   // true extent over ALL in-box-or-not points
        if (x > tmxx) tmxx = x;
        if (y < tmny) tmny = y;
        if (y > tmxy) tmxy = y;
        if (x < lox || x > hix || y < loy || y > hiy) { outbox++; continue; }
        int px = (int)((x - lox) * invw * W);
        int py = (int)((y - loy) * invh * H);
        if (px < 0) px = 0; else if (px >= W) px = W - 1;
        if (py < 0) py = 0; else if (py >= H) py = H - 1;
        grid[(size_t)py * W + px] += 1.0f;
        kept++;
    }
}

static void writeRaw(const char *path, int W, int H, const std::vector<float> &grid) {
    FILE *f = fopen(path, "wb");
    if (!f) { printf("cannot write %s\n", path); return; }
    int32_t wh[2] = {W, H};
    fwrite(wh, sizeof(int32_t), 2, f);
    fwrite(grid.data(), sizeof(float), grid.size(), f);
    fclose(f);
}

static void stats(const std::vector<float> &grid) {
    float mx = 0; long nz = 0;
    for (float v : grid) if (v > 0) { nz++; if (v > mx) mx = v; }
    // coarse percentile sampling (1% of nonzero)
    std::vector<float> s; s.reserve(1 << 16);
    for (size_t i = 0; i < grid.size(); i++) if (grid[i] > 0) { if ((i & 0x3f) == 0) s.push_back(grid[i]); }
    std::sort(s.begin(), s.end());
    if (!s.empty()) {
        auto pct = [&](float q) { size_t k = (size_t)(q * (s.size() - 1)); return s[k]; };
        printf("  nonzero=%ld  max=%g  p50=%g p90=%g p99=%g p99.9=%g\n",
               nz, mx, pct(0.50), pct(0.90), pct(0.99), pct(0.999));
    }
}

int main(int argc, char **argv) {
    int iters = DEFAULT_ITERS;
    int target = TARGET;
    const char *family = "polynomial";
    std::string rawpath;
    std::vector<std::string> files;
    for (int i = 1; i < argc; i++) {
        std::string s(argv[i]);
        if (s == "--target" && i + 1 < argc) { target = atoi(argv[++i]); continue; }
        if (s == "--iters" && i + 1 < argc) { iters = atoi(argv[++i]); continue; }
        if (s == "--family" && i + 1 < argc) { family = argv[++i]; continue; }
        if (s == "--raw" && i + 1 < argc) { rawpath = argv[++i]; continue; }
        if (!s.empty() && s[0] == '-' && s[1] == '-') {
            printf("unknown option %s (use --target N / --iters N / "
                   "--family polynomial|clifford / --raw PATH)\n", s.c_str());
            return 1;
        }
        files.push_back(s);
    }
    if (strcmp(family, "polynomial") != 0 && strcmp(family, "clifford") != 0) {
        printf("error: bad --family %s (use polynomial or clifford)\n", family);
        return 1;
    }
    // legacy: a trailing positional number is the iters count
    if (!files.empty()) {
        const std::string &last = files.back();
        bool isnum = !last.empty();
        for (char c : last) if (!isdigit((unsigned char)c) && c != '.') { isnum = false; break; }
        if (isnum && atof(last.c_str()) > 0) {
            iters = atoi(last.c_str());
            files.pop_back();
        }
    }
    if (target < 16 || target > 32768) {
        printf("error: --target must be between 16 and 32768 (got %d)\n", target);
        return 1;
    }
    if (iters < 1000) {
        printf("error: --iters too small (got %d)\n", iters);
        return 1;
    }
    if (!rawpath.empty() && files.size() != 1) {
        printf("error: --raw can only be used with a single input file\n");
        return 1;
    }
    if (files.empty()) {
        printf("usage: quad2d FILE [FILE ...] [ITERS] [--target N] [--iters N] "
               "[--family polynomial|clifford] [--raw PATH]\n");
        return 1;
    }
    for (const std::string &path : files) {
        P p;
        if (!readParam(path.c_str(), family, p)) continue;
        double bw = p.xmax - p.xmin, bh = p.ymax - p.ymin;
        int H, W;
        if (bw >= bh) { W = target; H = (int)(target * bh / bw); }
        else          { H = target; W = (int)(target * bw / bh); }
        if (W < 1) W = 1; if (H < 1) H = 1;
        std::string base = baseOf(path.c_str());
        printf("=== %s  (canvas %dx%d) ===\n", path.c_str(), W, H);
        printf("  bounds x[%.4f,%.4f] y[%.4f,%.4f]\n", p.xmin,p.xmax,p.ymin,p.ymax);
        std::vector<float> grid((size_t)W * H, 0.0f);
        long long kept, disc, outbox;
        double tmnx, tmxx, tmny, tmxy;
        integrate(p, W, H, iters, grid, kept, disc, tmnx, tmxx, tmny, tmxy, outbox);
        printf("  kept=%lld discarded=%lld outbox=%lld\n", kept, disc, outbox);
        if (outbox > 0)
            printf("  true_extent x[%.6f,%.6f] y[%.6f,%.6f]\n", tmnx, tmxx, tmny, tmxy);
        stats(grid);
        std::string raw = rawpath.empty() ? base + ".raw" : rawpath;
        writeRaw(raw.c_str(), W, H, grid);
        printf("  wrote %s\n", raw.c_str());
    }
    return 0;
}
