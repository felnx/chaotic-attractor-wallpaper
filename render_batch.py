#!/usr/bin/env python3
"""Render selected attractors at high resolution with a smooth, crisp smoky look.

Usage (cubnn venv python for numpy):
  python render_batch.py 155 149 184 480 [sigma] [Kmode]

For each N it reads output/N.raw (regenerate with ./quad2d output/N.txt) and
writes output/N_hd.png  (white background). K is auto-picked per attractor as a
percentile of its density so the strokes read clearly without harsh black.
"""
import struct
import sys

import numpy as np
from PIL import Image


def convolve1d_edge(a, k, axis):
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


def gauss_blur(img, sigma):
    r = int(2.5 * sigma + 0.5)
    i = np.arange(-r, r + 1)
    k = np.exp(-(i * i) / (2.0 * sigma * sigma))
    k /= k.sum()
    img = convolve1d_edge(img, k, axis=1)
    img = convolve1d_edge(img, k, axis=0)
    return img


def load_raw(path):
    data = open(path, "rb").read()
    W, H = struct.unpack("<ii", data[:8])
    d = np.frombuffer(data, dtype="<f4", count=W * H, offset=8).copy().reshape(H, W)
    return d


def render(n, sigma, K, gamma=0.9, floor=85):
    d = load_raw(f"output/{n}.raw")
    db = gauss_blur(d, sigma)
    t = np.where(db > 0, 1.0 - np.exp(-db / K), 0.0)
    g = 255.0 * (1.0 - t ** gamma)
    np.clip(g, floor, 255, out=g)
    px = g.round().astype(np.uint8)
    Image.fromarray(px, mode="L").save(f"output/{n}_hd.png")
    flat = px.ravel()
    ink = flat[flat < 250]
    return px.shape, int(np.median(ink)), round(100 * len(ink) / len(flat), 1), len(np.unique(flat))


def main():
    args = sys.argv[1:]
    sigma = float(args[-1]) if len(args) > 1 and args[-1].replace('.', '', 1).isdigit() and '.' in args[-1] else 4.0
    ns = [int(x) for x in args if x.lstrip('-').isdigit()]
    for n in ns:
        d = load_raw(f"output/{n}.raw")
        pos = d[d > 0]
        # auto K: a density that is ~p97 of the nonzero cells maps to a clear
        # mid-dark stroke; keeps faint parts visible but not the whole canvas gray
        K = float(np.percentile(pos, 97))
        shape, med, inkpct, levels = render(n, sigma, K)
        print(f"{n}: {shape[1]}x{shape[0]}  K={K:.0f}  median={med}  ink%={inkpct}  levels={levels}")


if __name__ == "__main__":
    main()
