#!/usr/bin/env python3
"""Render attractor param files as crisp high-resolution line plots on white.

Unlike the density/tone-map route (which smears points into a smoky wash),
this plots the orbit as connected line segments at high resolution -- the
same look as the original fractal.py output, but large and smooth (no
visible dots, no blur).

Usage (any python with PIL):
    python3 render_crisp.py 155 149 184 480 [long_side] [gray]

    long_side : pixels of the canvas's longer side (default 1600)
    gray      : ink gray value 0..255 (default 30; lower = darker)
"""
import struct  # noqa: F401  (kept for symmetry with other scripts)
import sys
from PIL import Image, ImageDraw


def read_param(path):
    with open(path) as f:
        lines = [l.split() for l in f.read().splitlines() if l.strip()]
    bounds = [float(v) for v in lines[0][:4]]
    a = [0.0] * 6
    b = [0.0] * 6
    for i in range(6):
        a[i] = float(lines[1 + i][0])
        b[i] = float(lines[1 + i][1])
    return bounds, a, b


def integrate(a, b, n, x0=0.0, y0=0.0):
    """Integrate n steps; returns (xs, ys) lists of kept points."""
    xs = [x0]
    ys = [y0]
    x, y = x0, y0
    a0, a1, a2, a3, a4, a5 = a
    b0, b1, b2, b3, b4, b5 = b
    for _ in range(n):
        xx = x * x
        yy = y * y
        xy = x * y
        xn = a0 + a1 * x + a2 * xx + a3 * xy + a4 * y + a5 * yy
        yn = b0 + b1 * x + b2 * xx + b3 * xy + b4 * y + b5 * yy
        x, y = xn, yn
        if x != x or y != y:
            x, y = 0.0, 0.0
        xs.append(x)
        ys.append(y)
    return xs, ys


def main():
    import os
    args = sys.argv[1:]
    nums = [int(x) for x in args if x.isdigit() and os.path.exists(f"output/{x}.txt")]
    long_side = 1600
    ink = 30
    opts = [x for x in args if x.isdigit() and not os.path.exists(f"output/{x}.txt")]
    if len(opts) >= 1:
        long_side = int(opts[0])
    if len(opts) >= 2:
        ink = int(opts[1])

    for n in nums:
        (xmin, ymin, xmax, ymax), a, b = read_param(f"output/{n}.txt")
        xs, ys = integrate(a, b, 8_000_000)
        # discard transient
        xs = xs[1000:]
        ys = ys[1000:]

        bw = xmax - xmin
        bh = ymax - ymin
        m = 1.02  # small white margin
        if bw >= bh:
            W = long_side
            H = int(long_side * bh / bw)
        else:
            H = long_side
            W = int(long_side * bw / bh)

        sx = W / (bw * m)
        sy = H / (bh * m)
        ox = (W - bw * sx) / 2 - xmin * sx
        oy = (H - bh * sy) / 2 - ymin * sy

        img = Image.new("L", (W, H), 255)
        d = ImageDraw.Draw(img)
        px = [x * sx + ox for x in xs]
        py = [y * sy + oy for y in ys]
        pts = [(px[i], py[i]) for i in range(len(px))]
        # draw in chunks to keep PIL happy
        CH = 200_000
        for i in range(0, len(pts) - 1, CH):
            chunk = pts[i:i + CH + 1]
            d.line(chunk, fill=ink, width=1, joint="curve")
        out = f"output/{n}_crisp.png"
        img.save(out)
        print(f"{n}: {W}x{H}  ink={ink}  -> {out}")


if __name__ == "__main__":
    main()
