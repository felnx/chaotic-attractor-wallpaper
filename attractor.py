#!/usr/bin/env python3
"""attractor.py — random chaotic attractors (2-D polynomial or Clifford
family): render to wallpaper and save the parameter set as a compact
text/number code.

Just run it:

    python3 attractor.py            # one new random attractor: PNG + config
    python3 attractor.py -n 5       # five of them
    python3 attractor.py -n 3 --seed 42   # reproducible

Re-render a saved one (e.g. to change colors later):

    python3 attractor.py C7K3M9...          # by code
    python3 attractor.py output/C7K3M9.cfg  # or by config file path

What happens per attractor
--------------------------
1. Random parameters are drawn for a --family of attractors:

     polynomial (default): the 12-coefficient 2-D quadratic family of
                           fractal.py:
          x' = a0 + a1 x + a2 x^2 + a3 x y + a4 y + a5 y^2
          y' = b0 + b1 x + b2 x^2 + b3 x y + b4 y + b5 y^2
     clifford: the 8-parameter trigonometric family
          x' = a sin(b y) + c cos(d x)
          y' = e sin(f x) + g cos(h y)

   Parameter sets are kept only if a real orbit + largest Lyapunov exponent
   shows them bounded and genuinely chaotic (divergers / periodic / point
   attractors are discarded and re-drawn).
2. The parameters are quantized (default 16 bits each = ~5 decimal digits
   of accuracy) and packed into one base32 code of letters+digits,
   e.g. "3KQ7M9...". That code IS the configuration: it fully determines the
   attractor and can be typed back into this script at any time. The .cfg
   file also keeps the full-precision coefficients so re-renders stay
   faithful.
3. A config file output/<CODE>.cfg is written in a simple, hand-editable
   key/value text format: the code, the full-precision coefficients, the
   bounding box, the start point, and the style (sigma/pct/gamma/fg/bg).
   Edit fg/bg there (or pass --fg/--bg) to re-render the same attractor in
   other colors/contrast later. Each attractor's files are split into
   subfolders of the output dir (default output/):

       <CODE>.cfg        parameters (hand-editable, at the output root)
       images/<CODE>.png the wallpaper
       raw/<CODE>.raw    binary density grid
       txt/<CODE>.txt    quad2d input (box, start, coefficients)
4. The orbit is integrated with ./quad2d (C, 20M steps, density grid whose
   long side is --res pixels, default 1600) and tone-mapped to color:
   crisp fg strokes on a bg ground (defaults: pure black on pure white;
   fg/bg accept a gray level 0-255 or a hex color like #1a2b3c), K
   auto-picked per attractor so strokes read well. The result is a WALLPAPER:
   the tone-mapped attractor is centered on a canvas of --size WxH
   (default 1920x1080) in --fit contain|cover style. If the orbit only
   covers a tiny fraction of the grid (filamentary, near-empty), it is
   discarded and re-rolled (--min-coverage).

Style overrides (applied to this run; the .cfg keeps its own defaults):
    --family polynomial   attractor family: 'polynomial' (default; the
                  12-coefficient 2-D quadratic) or 'clifford' (8-parameter
                  trigonometric; drawn from [-3,3])
    --sigma 1.0   Gaussian blur (crisper = smaller)
    --pct   50    tone-curve knee as a percentile of the density
    --gamma 1.0   tone-curve exponent
    --fg    0     foreground color: a gray level 0-255 (0 = black) or a hex
                  color like #1a2b3c (default: black)
    --bg    255   background color: a gray level 0-255 (255 = white) or a
                  hex color like #f5f2ea (default: white)
    --bits  16    code precision (16 = 39-char codes; 8 -> 20-char codes,
                  coarser)
    --out PATH    explicit PNG path (single render only)

Wallpaper options:
    --size 1920x1080  output canvas WxH (default 1920x1080; try 3840x2160
                      for 4K, or 1080x1920 for portrait)
    --res   1600      attractor resolution: long side of the density grid
                      in pixels (higher = smoother lines, slower; 900 was
                      the pre-wallpaper default)
    --fit   contain   place the attractor whole, centered on the canvas
                      (no cropping); 'cover' fills the frame edge-to-edge
                      and crops the excess (good when the attractor's shape
                      is close to the canvas ratio)
    --margin 0.0      for --fit contain: extra margin per side as a fraction
                      of the canvas (0.03 = 3% breathing room)

Rendering needs numpy -> use the cubnn venv:
    /home/felix/projects/cubnn/.venv/bin/python attractor.py -n 3
Generation only (--params-only or no render) works with plain python3.

The stats printed after each render (median/ink%/levels) are objective
sanity checks only; judge the look by eye.
"""
import argparse
import math
import os
import random
import re
import struct
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
QUAD2D = os.path.join(HERE, "quad2d")
DEFAULT_OUTDIR = os.path.join(HERE, "output")

# defaults: crisp black strokes on white; fg/bg are (r, g, b) floats 0-255
DEF = dict(sigma=1.0, pct=50.0, gamma=1.0, fg=(0.0, 0.0, 0.0),
           bg=(255.0, 255.0, 255.0),
           bits=16, iters=20_000_000)
# wallpaper defaults
WALL_DEFAULT = (1920, 1080)   # --size
RES_DEFAULT = 1600            # --res: long side of the attractor grid
# output layout: one subfolder per object type (.cfg stays at the root)
DIR_IMAGES = "images"         # <CODE>.png
DIR_RAW = "raw"               # <CODE>.raw (binary density grid)
DIR_TXT = "txt"               # <CODE>.txt (quad2d input)


def object_paths(code, outdir):
    """All files one attractor produces, in the subfolder layout."""
    return [os.path.join(outdir, code + ".cfg"),
            os.path.join(outdir, DIR_TXT, code + ".txt"),
            os.path.join(outdir, DIR_RAW, code + ".raw"),
            os.path.join(outdir, DIR_IMAGES, code + ".png")]


def parse_size(s):
    """'1920x1080' (also 'X'/'x'/'X'/':' separators) -> (W, H)."""
    m = re.fullmatch(r"\s*(\d+)\s*[xX:]\s*(\d+)\s*", str(s))
    if not m:
        raise ValueError(f"bad --size {s!r}: expected WxH like 1920x1080")
    return int(m.group(1)), int(m.group(2))


def parse_color(s):
    """A color: a gray level '0'..'255' or a hex '#RGB'/'#RRGGBB'.

    Returns (r, g, b) floats in 0-255. The '#' prefix is required for hex
    so a plain number always means a gray level (backward compatible).
    """
    s = str(s).strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            raise ValueError(f"bad hex color {s!r}: use #RGB or #RRGGBB")
        try:
            v = int(h, 16)
        except ValueError:
            raise ValueError(f"bad hex color {s!r}: non-hex digits")
        return float((v >> 16) & 255), float((v >> 8) & 255), float(v & 255)
    try:
        g = float(s)
    except ValueError:
        raise ValueError(f"bad color {s!r}: use a gray level 0-255 or #RRGGBB")
    if not (0.0 <= g <= 255.0):
        raise ValueError(f"gray color {s!r} out of range (0-255)")
    return g, g, g


def color_str(c):
    """(r, g, b) -> compact .cfg text: one gray number, or #rrggbb."""
    if abs(c[0] - c[1]) < 0.5 and abs(c[1] - c[2]) < 0.5:
        return "%.6g" % c[0]
    return "#%02x%02x%02x" % (int(round(c[0])), int(round(c[1])),
                              int(round(c[2])))

ALPHA = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # Crockford base32 (no I L O U)
VAL = {c: i for i, c in enumerate(ALPHA)}


# =============================================================================
# code <-> parameters (a code encodes the family's full parameter list)
# =============================================================================
def encode(params, family, bits=16):
    """Family parameters -> one base32 letter/digit string.

    Each parameter is stored quantized as (p / scale + 1) / 2 in [0, 1], so
    the code is family-relative: a clifford parameter of -3 maps to 0 and
    +3 to 1 (scale 3).
    """
    f = FAMILIES[family]
    n = 2 ** bits
    scale = f["scale"]
    v = 0
    for c in params:
        q = int(round((c / scale + 1.0) / 2.0 * (n - 1)))
        q = max(0, min(n - 1, q))
        v = (v << bits) | q
    digs = []
    while True:
        v, r = divmod(v, 32)
        digs.append(ALPHA[r])
        if v == 0:
            break
    s = "".join(reversed(digs))
    return s.zfill(math.ceil(f["n"] * bits / 5))


def decode(code, family=None, bits=16):
    """base32 code -> full-precision parameter list (inverse of encode).

    family=None infers the family from the code length (unambiguous: the
    families' codes have different lengths for any bits value)."""
    code = code.strip().upper()
    if family is None:
        family = infer_family(code, bits)
    f = FAMILIES[family]
    nparams = f["n"]
    scale = f["scale"]
    want = math.ceil(nparams * bits / 5)
    if len(code) != want:
        raise ValueError(f"code must be exactly {want} chars "
                         f"({nparams} x {bits}-bit params), got {len(code)}: "
                         f"{code!r}")
    v = 0
    for ch in code:
        if ch not in VAL:
            raise ValueError(f"bad character {ch!r} in code {code!r}")
        v = v * 32 + VAL[ch]
    n = 2 ** bits
    qs = []
    for _ in range(nparams):
        qs.append(v & (n - 1))
        v >>= bits
    if v != 0:
        raise ValueError(f"code {code!r} longer than {nparams}x{bits} bits")
    # bits were packed high-first (q0 = most significant), so q0 comes out last
    return [q / (n - 1) * 2.0 - 1.0 * scale for q in reversed(qs)]


# =============================================================================
# attractor families
# =============================================================================
# Each family: n = number of parameters, range = the random-draw range,
# scale = code scaling (the code stores p/scale, so p = code_value * scale).
FAMILIES = {
    "polynomial": dict(n=12, range=(-1.0, 1.0), scale=1.0),
    "clifford":   dict(n=8,  range=(-3.0, 3.0), scale=3.0),
}


def infer_family(code, bits=16):
    """Which family a code belongs to, from its length (unambiguous: codes
    of different families always have different lengths)."""
    for name, f in FAMILIES.items():
        if len(code.strip().upper()) == math.ceil(f["n"] * bits / 5):
            return name
    want = {name: math.ceil(f["n"] * bits / 5) for name, f in FAMILIES.items()}
    raise ValueError(
        f"code length {len(code.strip().upper())} matches no family at "
        f"{bits} bits (expected {want['polynomial']} chars for polynomial "
        f"or {want['clifford']} for clifford)")


def random_coeffs(family, rng):
    """Random (a, b) parameter lists for `family`; a = first n/2 params."""
    f = FAMILIES[family]
    n = f["n"]
    lo, hi = f["range"]
    ps = [rng.uniform(lo, hi) for _ in range(n)]
    return ps[:n // 2], ps[n // 2:]


def make_step(family, a, b):
    """One map iteration as step(x, y).

    polynomial (12 coefficients):
        x' = a0 + a1 x + a2 x^2 + a3 x y + a4 y + a5 y^2
        y' = b0 + b1 x + b2 x^2 + b3 x y + b4 y + b5 y^2
    clifford (8 parameters, a = p0..p3, b = q0..q3):
        x' = p0 sin(p1 y) + p2 cos(p3 x)
        y' = q0 sin(q1 x) + q2 cos(q3 y)
    """
    if family == "polynomial":
        def step(x, y):
            xx, yy, xy = x * x, y * y, x * y
            return (a[0] + a[1] * x + a[2] * xx + a[3] * xy + a[4] * y
                    + a[5] * yy,
                    b[0] + b[1] * x + b[2] * xx + b[3] * xy + b[4] * y
                    + b[5] * yy)
        return step

    def step(x, y):
        return (a[0] * math.sin(a[1] * y) + a[2] * math.cos(a[3] * x),
                b[0] * math.sin(b[1] * x) + b[2] * math.cos(b[3] * y))
    return step


def make_jacobian(family, a, b):
    """Jacobian J(x, y) = (j11, j12, j21, j22) of the family's map, used
    for the Lyapunov computation."""
    if family == "polynomial":
        def jac(x, y):
            return (a[1] + 2.0 * a[2] * x + a[3] * y,
                    a[3] * x + a[4] + 2.0 * a[5] * y,
                    b[1] + 2.0 * b[2] * x + b[3] * y,
                    b[3] * x + b[4] + 2.0 * b[5] * y)
        return jac

    def jac(x, y):
        return (-a[2] * a[3] * math.sin(a[3] * x),
                a[0] * a[1] * math.cos(a[1] * y),
                b[0] * b[1] * math.cos(b[1] * x),
                -b[2] * b[3] * math.sin(b[3] * y))
    return jac


# =============================================================================
# parameter generation + validation (pure Python, no numpy)
# =============================================================================


def validate(family, a, b, x0, y0, lyap_min=1e-4, transient=20_000, window=80_000):
    """Bounded orbit + largest Lyapunov exponent + bounds of the tail.

    Starts the orbit at (x0, y0). The first `transient` steps are discarded
    so the measured Lyapunov exponent describes the long-time behavior
    (transiently chaotic orbits that settle onto a fixed point are rejected).
    Also checks that the tail of the orbit is still alive (not sitting on a
    point / tiny cycle).

    Returns (ok, lyap, info); info = (xmin, ymin, xmax, ymax, x0, y0) where
    (x0, y0) is the tail end of the orbit — a point ON the attractor to
    restart quad2d from (it integrates from a fixed start, so some
    attractors are never reached from the origin).
    ok = bounded + tail alive + lyap > lyap_min.
    """
    step = make_step(family, a, b)
    jac = make_jacobian(family, a, b)
    x, y = x0, y0

    for _ in range(transient):                 # discard transient
        x, y = step(x, y)
        if x != x or y != y or x < -1e10 or x > 1e10 or y < -1e10 or y > 1e10:
            return False, float("inf"), None

    ex, ey, s = 1.0, 0.0, 0.0
    for _ in range(window):                    # Lyapunov over the settled orbit
        j11, j12, j21, j22 = jac(x, y)
        x, y = step(x, y)
        if x != x or y != y or x < -1e10 or x > 1e10 or y < -1e10 or y > 1e10:
            return False, float("inf"), None
        nx, ny = j11 * ex + j12 * ey, j21 * ex + j22 * ey
        ln = math.hypot(nx, ny)
        if ln > 0:
            s += math.log(ln)
            ex, ey = nx / ln, ny / ln
    lyap = s / window

    # tail liveness: after another stretch the orbit must still be moving
    x1, y1 = x, y
    for _ in range(20_000):
        x1, y1 = step(x1, y1)
        if x1 != x1 or y1 != y1 or x1 < -1e10 or x1 > 1e10:
            return False, lyap, None
    if (abs(x1 - x) < 1e-9 and abs(y1 - y) < 1e-9) or \
       (x1 - x) ** 2 + (y1 - y) ** 2 < 1e-12:
        return False, lyap, None              # settled onto a point/cycle

    # coarse bounds of the settled orbit (tighten() refines them later)
    xmin = xmax = x
    ymin = ymax = y
    for _ in range(20_000):
        x, y = step(x, y)
        if x < xmin: xmin = x
        if x > xmax: xmax = x
        if y < ymin: ymin = y
        if y > ymax: ymax = y
    return (lyap > lyap_min), lyap, (xmin, ymin, xmax, ymax, x, y)


def tighten(family, a, b, x, y, n=300_000):
    """Continue the orbit n more steps, refining the bounding box.

    The validate() bounds come from ~100k samples and can miss rarely
    visited extreme corners of the attractor; a box built from them is too
    small and quad2d's orbit then leaves it. Cheap: pure map iteration, no
    Jacobian. Returns (xmin, ymin, xmax, ymax, x, y) or None if diverged.
    """
    step = make_step(family, a, b)
    xmin = xmax = x
    ymin = ymax = y
    for _ in range(n):
        x, y = step(x, y)
        if x != x or y != y or x < -1e10 or x > 1e10 or y < -1e10 or y > 1e10:
            return None
        if x < xmin: xmin = x
        elif x > xmax: xmax = x
        if y < ymin: ymin = y
        elif y > ymax: ymax = y
    return xmin, ymin, xmax, ymax, x, y


# =============================================================================
# config file (hand-editable key/value text)
# =============================================================================
def write_config(path, code, info, style, family="polynomial", exact=None):
    """info = (xmin, ymin, xmax, ymax, x0, y0); (x0,y0) is on the attractor.
    exact = optional list of full-precision parameters (12 for polynomial,
    8 for clifford)."""
    xmin, ymin, xmax, ymax, x0, y0 = info
    n = FAMILIES[family]["n"]
    lines = [
        "# chaoticattractors config v2",
        "# re-render with:   python3 attractor.py " + code,
        "# The 'exact' line below has full-precision parameters, so a",
        "# re-render from this file is faithful even though the code is",
        "# quantized (a chaotic map amplifies coarse parameters).",
        "# Edit fg/bg/sigma/pct/gamma to change colors or contrast, then",
        "# re-run the command above.",
        "code    " + code,
        "family  " + family,
    ]
    if exact:
        lines.append("exact   " + " ".join("%.17g" % c for c in exact))
    lines += [
        "bounds  %.17g %.17g %.17g %.17g" % (xmin, ymin, xmax, ymax),
        "start   %.17g %.17g" % (x0, y0),
        "sigma   %.6g" % style["sigma"],
        "pct     %.6g" % style["pct"],
        "gamma   %.6g" % style["gamma"],
        "fg      " + color_str(style["fg"]),
        "bg      " + color_str(style["bg"]),
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def read_config(path):
    cfg = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, rest = line.partition(" ")
            cfg[key.strip()] = rest.strip()
    if "code" not in cfg:
        return None
    return cfg


# =============================================================================
# rendering (needs numpy + PIL; imported lazily)
# =============================================================================
def _numpy_pil():
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        sys.exit("error: numpy/PIL not found. Use the cubnn venv:\n"
                 "  /home/felix/projects/cubnn/.venv/bin/python attractor.py ...")
    return np, Image


def conv1d(a, k, axis, np):
    r = len(k) // 2
    a = np.moveaxis(a, axis, 0)
    L = a.shape[0]
    pw = [(0, 0)] * a.ndim
    pw[0] = (r, r)
    ap = np.pad(a, pw, mode="edge")
    out = np.zeros_like(a)
    for j, kv in enumerate(k):
        out += kv * ap[j:j + L]
    return np.moveaxis(out, 0, axis)


def gauss_blur(d, sigma, np):
    r = int(2.5 * sigma + 0.5)
    i = np.arange(-r, r + 1)
    k = np.exp(-(i * i) / (2.0 * sigma * sigma))
    k /= k.sum()
    return conv1d(conv1d(d, k, axis=1, np=np), k, axis=0, np=np)


def load_raw(path, np):
    data = open(path, "rb").read()
    W, H = struct.unpack("<ii", data[:8])
    return np.frombuffer(data, dtype="<f4", count=W * H,
                         offset=8).copy().reshape(H, W)


def tonemap(d, sigma, K, gamma, fg, bg, np, Image):
    """fg/bg are (r, g, b) tuples in 0-255; returns an RGB image."""
    db = gauss_blur(d, sigma, np)
    t = np.where(db > 0, 1.0 - np.exp(-db / K), 0.0) ** gamma
    out = np.empty((d.shape[0], d.shape[1], 3), dtype=np.uint8)
    for i in range(3):
        c = bg[i] - (bg[i] - fg[i]) * t
        out[..., i] = np.clip(c, 0.0, 255.0).round()
    return Image.fromarray(out, mode="RGB")


def ensure_quad2d():
    if os.path.exists(QUAD2D):
        return
    if os.path.exists(os.path.join(HERE, "quad2d.cpp")):
        print("quad2d binary missing -> building ...")
        subprocess.run(["g++", "-O2", "-o", QUAD2D,
                        os.path.join(HERE, "quad2d.cpp")], check=True)
    else:
        sys.exit("error: no quad2d binary and no quad2d.cpp to build from")


class RenderError(Exception):
    """A code could not be rendered (diverges, empty grid, blank image...)."""


def render(code, outdir=DEFAULT_OUTDIR, out=None, overrides=None,
           iters=DEF["iters"], bits=DEF["bits"], verbose=True,
           size=WALL_DEFAULT, res=RES_DEFAULT, fit="contain", margin=0.0,
           family=None):
    """Render one code: quad2d orbit -> density -> tone-mapped PNG.

    family=None infers it from the code length (unambiguous). The
    tone-mapped attractor (long side ~`res` px) is placed on a `size`
    WxH wallpaper canvas: 'contain' keeps it whole and centered, 'cover'
    crops it to fill the frame. Files are written as <outdir>/<CODE>.cfg,
    <outdir>/images/<CODE>.png, <outdir>/raw/<CODE>.raw, <outdir>/txt/<CODE>.txt.
    Returns (png_path, stats_str, meta); raises RenderError on any failure,
    so a bad code can never end a run silently.
    """
    np, Image = _numpy_pil()
    if family is None:
        family = infer_family(code, bits)
    n = FAMILIES[family]["n"]
    ps = decode(code, family, bits)
    a, b = ps[:n // 2], ps[n // 2]

    cfg_path = os.path.join(outdir, code + ".cfg")
    for d in (os.path.join(outdir, DIR_TXT), os.path.join(outdir, DIR_RAW),
              os.path.join(outdir, DIR_IMAGES)):
        os.makedirs(d, exist_ok=True)
    info, style = None, dict(DEF)
    if os.path.exists(cfg_path):
        cfg = read_config(cfg_path)
        if cfg:
            # a .cfg from an older version without a family line: trust the
            # length-inferred family (existing .cfgs are polynomial)
            if "family" in cfg and cfg["family"] != family:
                raise RenderError(
                    f"code {code} is {family} but its .cfg says "
                    f"{cfg['family']}")
            if "exact" in cfg:
                try:
                    exact = [float(v) for v in cfg["exact"].split()]
                    if len(exact) == n:
                        a, b = exact[:n // 2], exact[n // 2:]
                except ValueError:
                    pass
            try:
                info = tuple(map(float, cfg["bounds"].split()))
            except (KeyError, ValueError):
                info = None
            try:
                info = info + tuple(map(float, cfg["start"].split()))
            except (KeyError, ValueError):
                pass
            for k in ("sigma", "pct", "gamma"):
                try:
                    style[k] = float(cfg[k])
                except (KeyError, ValueError):
                    pass
            for k in ("fg", "bg"):
                try:
                    style[k] = parse_color(cfg[k])
                except (KeyError, ValueError):
                    pass
    if info is None or len(info) != 6:
        # no config: find a chaotic orbit from a few deterministic starts
        info = None
        for sx, sy in ((0.0, 0.0), (0.5, 0.5), (-0.5, -0.5)):
            ok, _, t = validate(family, a, b, sx, sy)
            if ok:
                t2 = tighten(family, a, b, t[4], t[5])
                info = t2 if t2 is not None else t
                break
        if info is None:
            raise RenderError(f"code {code} gives no chaotic bounded orbit")
    if overrides:
        style.update({k: v for k, v in overrides.items() if v is not None})

    # run quad2d with the given box/start; returns (nonzero_cells, outbox, extent)
    # where extent = (xmin,xmax,ymin,ymax) of ALL orbit points (or None).
    # The input goes to <outdir>/txt/, the binary grid to <outdir>/raw/
    # (quad2d is told the raw location via --raw).
    qtxt = os.path.join(outdir, DIR_TXT, code + ".txt")
    raw = os.path.join(outdir, DIR_RAW, code + ".raw")
    ensure_quad2d()

    def run_quad2d(box, x0, y0):
        if os.path.exists(raw):
            os.remove(raw)        # never read a stale grid from an old run
        with open(qtxt, "w") as f:
            f.write(f"{box[0]} {box[1]} {box[2]} {box[3]} {x0} {y0}\n")
            for i in range(n // 2):
                f.write(f"{a[i]} {b[i]}\n")
        if verbose:
            print(f"=== {code}  ({family}, grid long side {res} px) ===")
        try:
            r = subprocess.run([QUAD2D, "--target", str(int(res)),
                                "--iters", str(int(iters)),
                                "--family", family,
                                "--raw", raw, qtxt],
                               cwd=HERE, capture_output=True, text=True)
        except OSError as e:
            raise RenderError(f"quad2d failed for {code}: {e}")
        if r.returncode != 0:
            raise RenderError(f"quad2d failed for {code}: "
                              f"{r.stderr.strip() or 'no error text'}")
        if verbose:
            for ln in r.stdout.splitlines():
                print(" ", ln)
        diverged = "diverged" in r.stdout
        outbox = 0
        m = re.search(r"outbox=(\d+)", r.stdout)
        if m:
            outbox = int(m.group(1))
        ext = None
        m = re.search(r"true_extent x\[(-?[\d.eE+]+),(-?[\d.eE+]+)\] "
                      r"y\[(-?[\d.eE+]+),(-?[\d.eE+]+)\]", r.stdout)
        if m:
            ext = tuple(float(v) for v in m.groups())
        if not os.path.exists(raw):
            raise RenderError(f"quad2d wrote no grid for {code}"
                              + (" (orbit diverged)" if diverged else ""))
        data = open(raw, "rb").read()
        W, H = struct.unpack("<ii", data[:8])
        if len(data) != 8 + 4 * W * H:
            raise RenderError(f"corrupt grid file for {code}")
        grid = np.frombuffer(data, dtype="<f4", count=W * H, offset=8)
        return int((grid > 0).sum()), outbox, ext, diverged

    xmin, ymin, xmax, ymax, x0, y0 = info
    kept, outbox, ext, diverged = run_quad2d((xmin, ymin, xmax, ymax),
                                             x0, y0)
    if kept == 0 or (ext and outbox > 0.01 * max(1, kept + outbox)):
        # grid empty, or the orbit exceeds the box (lines would be clipped at
        # the frame) -> grow the box to the true extent + 6% margin and re-run
        if verbose:
            print("  box too small -> re-expanding to true extent and retrying")
        if ext:
            xmn, xmx, ymn, ymx = ext
        else:
            t = tighten(family, a, b, x0, y0)
            if t is None:
                raise RenderError(
                    f"code {code} diverges from its own start point")
            xmn, xmx, ymn, ymx = t[0], t[1], t[2], t[3]
        mx_ = 0.5 * (xmx - xmn) * 0.10 + 1e-9
        my_ = 0.5 * (ymx - ymn) * 0.10 + 1e-9
        xmn -= mx_; xmx += mx_; ymn -= my_; ymx += my_
        kept, outbox, ext2, diverged = run_quad2d((xmn, ymn, xmx, ymx),
                                                  x0, y0)
        if ext2 and outbox > 0.01 * max(1, kept + outbox) and verbose:
            print("  warning: orbit still exceeds the box; image may clip")
        if kept > 0 and os.path.exists(cfg_path):
            # persist the good bounds so future re-renders skip the retry
            lines = open(cfg_path).read().splitlines()
            new = []
            for ln in lines:
                if ln.startswith("bounds"):
                    ln = ("bounds  %.17g %.17g %.17g %.17g"
                          % (xmn, ymn, xmx, ymx))
                new.append(ln)
            open(cfg_path, "w").write("\n".join(new) + "\n")
    if kept == 0:
        raise RenderError(
            f"no points in the box for {code}: "
            + ("the orbit diverges from its saved start point"
               if diverged else "the orbit never reaches the attractor"))

    d = load_raw(raw, np)
    pos = d[d > 0]
    if pos.size == 0:
        raise RenderError(
            f"density grid for {code} is empty (orbit diverged?)")
    K = float(np.percentile(pos, style["pct"]))
    img = tonemap(d, style["sigma"], K, style["gamma"],
                  style["fg"], style["bg"], np, Image)

    # ---- compose the wallpaper ---------------------------------------
    W, H = int(size[0]), int(size[1])
    bw, bh = img.size
    m = max(0.0, min(margin, 0.5))
    if fit == "contain":
        s = min((W * (1.0 - 2.0 * m)) / bw, (H * (1.0 - 2.0 * m)) / bh)
        tw, th = max(1, int(round(bw * s))), max(1, int(round(bh * s)))
        art = img.resize((tw, th), Image.LANCZOS)
        canvas = Image.new("RGB", (W, H),
                           (int(round(style["bg"][0])),
                            int(round(style["bg"][1])),
                            int(round(style["bg"][2]))))
        canvas.paste(art, ((W - tw) // 2, (H - th) // 2))
    elif fit == "cover":
        s = max(W / bw, H / bh)
        tw, th = max(W, int(round(bw * s))), max(H, int(round(bh * s)))
        art = img.resize((tw, th), Image.LANCZOS)
        canvas = art.crop(((tw - W) // 2, (th - H) // 2,
                           (tw + W) // 2, (th + H) // 2))
    else:
        raise RenderError(f"bad --fit {fit!r}: use 'contain' or 'cover'")
    if verbose and (W, H) != (bw, bh):
        mode = f"contain margin={m:.3f}" if fit == "contain" else "cover"
        print(f"  wallpaper {W}x{H}: attractor {bw}x{bh} placed "
              f"{mode} -> {canvas.size[0]}x{canvas.size[1]} area"
              if fit == "contain" else
              f"  wallpaper {W}x{H}: attractor {bw}x{bh} cropped "
              f"cover -> {canvas.size[0]}x{canvas.size[1]}")
    img = canvas

    flat = np.asarray(img).reshape(-1, 3)
    # background = the exact canvas color (tonemapped low-density areas also
    # converge to it), so 'ink' = every pixel visibly different from bg
    bgt = np.array([int(round(c)) for c in style["bg"]])
    mask = (abs(flat.astype(np.int16) - bgt).max(axis=1) > 10)
    ink = flat[mask]
    if ink.size == 0:
        raise RenderError(
            f"image for {code} would be blank (orbit has {kept} points in "
            "the box but none render visible) - re-roll or try a different "
            "--fg")
    png = out if out else os.path.join(outdir, DIR_IMAGES, code + ".png")
    if os.path.dirname(png):
        os.makedirs(os.path.dirname(png), exist_ok=True)
    img.save(png)

    stats = (f"{img.size[0]}x{img.size[1]}  "
             f"ink%={100.0*len(ink)/len(flat):.1f}  "
             f"levels={len(np.unique(flat, axis=0))}")
    meta = dict(kept=int(kept), nz=int(pos.size),
                cells=int(d.size), coverage=pos.size / d.size)
    if verbose:
        print(f"  saved {png}")
        print(f"  [{stats}]")
    return png, stats, meta


# =============================================================================
# main
# =============================================================================
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Random chaotic attractors (polynomial or Clifford "
                    "family): render to wallpaper and save the parameters "
                    "as a compact code.",
        epilog="examples:\n"
               "  python3 attractor.py -n 5\n"
               "  /home/felix/projects/cubnn/.venv/bin/python attractor.py -n 3 --seed 42\n"
               "  python3 attractor.py -n 2 --family clifford\n"
               "  python3 attractor.py <CODE>          # re-render a saved one\n"
               "  python3 attractor.py <CODE> --fg 60 --bg 255   # different contrast\n"
               "  python3 attractor.py <CODE> --fg '#1b2735' --bg '#e8e4d8'\n"
               "  python3 attractor.py -n 2 --size 3840x2160 --res 2400   # 4K, high res\n")
    ap.add_argument("codes", nargs="*",
                    help="re-render these CODEs (or paths to .cfg files); "
                         "omit to generate random ones")
    ap.add_argument("--family", choices=sorted(FAMILIES), default=None,
                    help="attractor family: 'polynomial' (the 12-coefficient "
                         "2-D quadratic; the default for generation) or "
                         "'clifford' (8-parameter trigonometric: x' = a sin(b "
                         "y) + c cos(d x), y' = e sin(f x) + g cos(h y)). "
                         "Re-renders infer the family from the code length; "
                         "passing it there is a check, not a switch")
    ap.add_argument("-n", "--count", type=int, default=1,
                    help="how many random attractors to make (default 1)")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed")
    ap.add_argument("--sigma", type=float, default=None,
                    help=f"blur sigma (default {DEF['sigma']})")
    ap.add_argument("--pct", type=float, default=None,
                    help=f"tone knee percentile (default {DEF['pct']:.0f})")
    ap.add_argument("--gamma", type=float, default=None,
                    help=f"tone exponent (default {DEF['gamma']})")
    ap.add_argument("--fg", default=None,
                    help="foreground color: gray level 0-255 (0=black) or a "
                         "hex color like #1a2b3c (default: black)")
    ap.add_argument("--bg", default=None,
                    help="background color: gray level 0-255 (255=white) or "
                         "a hex color like #f5f2ea (default: white)")
    ap.add_argument("--bits", type=int, default=DEF["bits"],
                    help=f"code precision bits (default {DEF['bits']} = 39-char "
                         "polynomial / 26-char clifford codes; 8 -> 20/13-char, "
                         "coarser)")
    ap.add_argument("--iters", type=int, default=DEF["iters"],
                    help="orbit length (default 20000000)")
    ap.add_argument("--size", default="1920x1080",
                    help="wallpaper canvas WxH (default 1920x1080; "
                         "e.g. 3840x2160 for 4K, 1080x1920 portrait)")
    ap.add_argument("--res", type=int, default=RES_DEFAULT,
                    help=f"attractor resolution: long side of the density "
                         f"grid in px (default {RES_DEFAULT}; 900 was the "
                         "pre-wallpaper value; higher = smoother, slower)")
    ap.add_argument("--fit", choices=("contain", "cover"), default="contain",
                    help="'contain' (default) keeps the attractor whole and "
                         "centered on the canvas; 'cover' scales it to fill "
                         "the frame and crops the excess")
    ap.add_argument("--margin", type=float, default=0.0,
                    help="for --fit contain: margin per side as a fraction "
                         "of the canvas (default 0.0; e.g. 0.03 for 3%%)")
    ap.add_argument("--lyap-min", type=float, default=1e-4,
                    help="min Lyapunov exponent to count as chaotic")
    ap.add_argument("--min-coverage", type=float, default=0.005,
                    help="min fraction of canvas cells the orbit must visit "
                         "(default 0.005 = 0.5%%, normalized to the 900-px "
                         "reference grid: at other --res values the default "
                         "is auto-scaled by (900/res)^2 so sparse-attractor "
                         "rejection doesn't change with resolution; an "
                         "explicit value is used as-is)")
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR, help="output dir")
    ap.add_argument("--out", default=None,
                    help="explicit PNG path (single render / code list only)")
    ap.add_argument("--params-only", action="store_true",
                    help="save configs only, skip rendering (no numpy needed)")
    args = ap.parse_args(argv)

    os.makedirs(args.outdir, exist_ok=True)
    try:
        size = parse_size(args.size)
        fg = parse_color(args.fg) if args.fg is not None else None
        bg = parse_color(args.bg) if args.bg is not None else None
        overrides = dict(sigma=args.sigma, pct=args.pct, gamma=args.gamma,
                         fg=fg, bg=bg)
    except ValueError as e:
        sys.exit(f"error: {e}")
    if not (10 <= args.res <= 32000):
        sys.exit("error: --res must be between 10 and 32000")
    # coverage falls ~ (900/res)^2 for the same orbit at higher resolution,
    # so auto-scale the DEFAULT threshold to keep the same rejection rate
    if args.min_coverage == 0.005:
        min_cov = 0.005 * (900.0 / args.res) ** 2
    else:
        min_cov = args.min_coverage
    wp = dict(size=size, res=args.res, fit=args.fit, margin=args.margin)

    # ---- re-render existing codes --------------------------------------
    if args.codes:
        for arg in args.codes:
            if arg.endswith(".cfg") and os.path.exists(arg):
                cfg = read_config(arg)
                if not cfg:
                    sys.exit(f"error: {arg} has no code line")
                code = cfg["code"]
            else:
                code = arg.upper()
            try:
                decode(code, bits=args.bits)      # also validates length/family
            except ValueError as e:
                sys.exit(f"error: {e}")
            if args.out and len(args.codes) > 1:
                sys.exit("error: --out only makes sense for a single code")
            try:
                render(code, outdir=args.outdir, out=args.out,
                       overrides=overrides, iters=args.iters, bits=args.bits,
                       family=args.family, **wp)
            except RenderError as e:
                sys.exit(f"error: {e}")
        return

    # ---- generate + render N random ones -------------------------------
    fam = args.family or "polynomial"
    rng = random.Random(args.seed)
    style_saved = dict(DEF, **{k: v for k, v in overrides.items()
                               if v is not None})
    made = 0
    attempts = 0
    stamp = int(time.time())
    while made < args.count:
        attempts += 1
        a, b = random_coeffs(fam, rng)
        # try a few deterministic starts; chaotic from any of them qualifies
        info = None
        lyap = 0.0
        for sx, sy in ((0.0, 0.0), (0.5, 0.5), (-0.5, -0.5), (0.3, -0.4)):
            ok, lyap, t = validate(fam, a, b, sx, sy, lyap_min=args.lyap_min)
            if ok:
                info = t
                break
        if info is None:
            continue
        # refine the bounding box (validate's 100k-sample box can be too
        # small; quad2d's orbit would leave it and the grid would be empty)
        t = tighten(fam, a, b, info[4], info[5])
        if t is not None:
            info = t
        code = encode(a + b, fam, args.bits)
        if os.path.exists(os.path.join(args.outdir, code + ".cfg")):
            # collision with a saved attractor: re-roll instead of suffixing
            # (a suffixed code would no longer decode)
            continue
        cfg_path = os.path.join(args.outdir, code + ".cfg")
        write_config(cfg_path, code, info, style_saved, family=fam,
                     exact=a + b)
        if args.params_only:
            made += 1
            print(f"[{made}/{args.count}] lyap={lyap:+.4f}  code={code}")
            print(f"  config {cfg_path}")
            continue
        try:
            png, stats, meta = render(code, outdir=args.outdir,
                                      overrides=overrides, iters=args.iters,
                                      bits=args.bits, family=fam, **wp)
        except RenderError as e:
            # this draw cannot be rendered (diverges / empty / blank):
            # discard its partial files and re-roll a fresh random set
            for p in object_paths(code, args.outdir):
                try:
                    os.remove(p)
                except OSError:
                    pass
            print(f"  [skip] code={code}: {e}")
            continue
        if meta["coverage"] < min_cov:
            # too sparse / filamentary -> looks near-empty; discard and retry
            for p in object_paths(code, args.outdir):
                try:
                    os.remove(p)
                except OSError:
                    pass
            print(f"  [retry] code={code} too sparse "
                  f"(coverage {100*meta['coverage']:.3f}% < "
                  f"{100*min_cov:.3f}%)")
            continue
        made += 1
        print(f"[{made}/{args.count}] lyap={lyap:+.4f}  code={code}")
        print(f"  config {cfg_path}")
    print(f"done: {made} of {attempts} random draws kept "
          f"(lyap_min={args.lyap_min:g})")


if __name__ == "__main__":
    main()
