#!/usr/bin/env python3
"""Match a card image/crop against the cardsense index. Debug/eval CLI.

Usage:
    python3 match.py <crop.png> [--expect "Card Name"] [--no-sweep] [-k 6]
"""
import argparse
import os

import cv2
import numpy as np

from phash import CardIndex, dual_phash, hamming_scan, align_variants


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("crop")
    ap.add_argument("--expect", default=None)
    ap.add_argument("--no-sweep", action="store_true")
    ap.add_argument("-k", type=int, default=6)
    a = ap.parse_args()

    idx = CardIndex()
    g = cv2.imread(a.crop, cv2.IMREAD_GRAYSCALE)
    if g is None:
        raise SystemExit(f"cannot read {a.crop}")

    best = None
    for v in align_variants(g, sweep=not a.no_sweep):
        d = hamming_scan(dual_phash(v), idx.bits)
        best = d if best is None else np.minimum(best, d)
    order = np.argsort(best)

    print(f"\n=== {os.path.basename(a.crop)} ===")
    seen, shown, top_name, first = set(), 0, None, None
    runner = None
    for i in order:
        nm = idx.names[i]
        if nm in seen:
            continue
        seen.add(nm)
        dist = int(best[i])
        if shown == 0:
            top_name, first = nm, dist
        elif runner is None:
            runner = dist
        mark = "  <== EXPECTED" if a.expect and a.expect.lower() in (nm or "").lower() else ""
        print(f"  {dist:4d}  {nm}{mark}")
        shown += 1
        if shown >= a.k:
            break
    if first is not None and runner is not None:
        print(f"  margin: {runner - first}")
    if a.expect:
        ei = [i for i, n in enumerate(idx.names) if n and a.expect.lower() in n.lower()]
        if ei:
            eb = min(int(best[i]) for i in ei)
            print(f"  EXPECTED '{a.expect}' best_dist={eb} (rank ~{int((best < eb).sum())})")


if __name__ == "__main__":
    main()
