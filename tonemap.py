#!/usr/bin/env python3
"""Stage 2: tone-map a raw density grid (quad2d output) to a smoky grayscale PNG.

Runs on the cubnn venv (has numpy):
    /home/felix/projects/cubnn/.venv/bin/python tonemap.py RAWFILE OUT_PNG [sigma] [K] [gamma] [floor]

The float density is blurred at FULL float precision (separable Gaussian,
numpy) and THEN tone-mapped, per the author's two-stage method:

    gray = max(floor, 255 * (1 - (1 - exp(-d/K))^gamma))

An 8-bit-channel blur quantizes the density to a handful of levels and
produces the banded / pixelated look; full-precision float blur gives the
smooth smoky gradient.

Winning recipe for candidate 684 (reference: median ~125, ink ~40%, no
harsh black): sigma=10, K=300, gamma=0.9, floor=85.
"""
import sys
import struct

import numpy as np
from PIL import Image


def gauss_blur(img: np.ndarray, sigma: float) -> np.ndarray:
    r = int(2.5 * sigma + 0.5)
    i = np.arange(-r, r + 1)
    k = np.exp(-(i * i) / (2.0 * sigma * sigma))
    k /= k.sum()
    # separable: rows then columns, with edge replication
    img = np.pad(img, r, mode="edge")
    img = np.apply_along_axis(lambda row: np.convolve(row, k, mode="same"), 1, img)
    img = np.apply_along_axis(lambda col: np.convolve(col, k, mode="same"), 0, img)
    return img[r:-r, r:-r]


def main():
    raw, out = sys.argv[1], sys.argv[2]
    sigma = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    K = float(sys.argv[4]) if len(sys.argv) > 4 else 300.0
    gamma = float(sys.argv[5]) if len(sys.argv) > 5 else 0.9
    floor = float(sys.argv[6]) if len(sys.argv) > 6 else 85.0

    with open(raw, "rb") as f:
        data = f.read()
    W, H = struct.unpack("<ii", data[:8])
    n = W * H
    d = np.frombuffer(data, dtype="<f4", count=n, offset=8).copy().reshape(H, W)

    # 1) full-precision float blur
    db = gauss_blur(d, sigma)

    # 2) tone map with a dark floor (no harsh black)
    t = np.where(db > 0, 1.0 - np.exp(-db / K), 0.0)
    g = 255.0 * (1.0 - t ** gamma)
    np.clip(g, floor, 255, out=g)
    px = g.round().astype(np.uint8)

    Image.fromarray(px, mode="L").save(out)

    flat = px.ravel()
    ink = flat[flat < 250]
    print("wrote %s  (%dx%d)  sigma=%.1f K=%.1f gamma=%.2f floor=%.0f"
          % (out, W, H, sigma, K, gamma, floor))
    print("  ink%%: %.1f   median: %d   min: %d   distinct gray levels: %d"
          % (100.0 * len(ink) / len(flat), int(np.median(ink)), int(ink.min()), len(np.unique(flat))))


if __name__ == "__main__":
    main()
