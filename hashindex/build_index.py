#!/usr/bin/env python3
"""Build the cardsense pHash index from the Scryfall bulk dump.

Input  (extracted Scryfall dump):
    <scryfall>/data/bulk_data.json      all card records
    <scryfall>/data/images/<id>.jpg     one image per card (id = filename)
Output (git-ignored, ~9MB + ~16MB):
    hashindex/data/phash_index.npz      bits:[N,64] uint8 (full++art), ids:[N]
    hashindex/data/phash_meta.json      [{id,name,type_line,mana_cost,oracle_text}]

Usage:
    python3 build_index.py [--scryfall ~/Downloads/scryfall_extracted]
"""
import argparse
import json
import os
import time

import numpy as np
import cv2

from phash import dual_phash, DATA_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scryfall",
                    default=os.path.expanduser("~/Downloads/scryfall_extracted"),
                    help="dir containing data/bulk_data.json and data/images/")
    args = ap.parse_args()
    root = os.path.join(args.scryfall, "data")
    img_dir = os.path.join(root, "images")
    os.makedirs(DATA_DIR, exist_ok=True)

    t0 = time.time()
    cards = json.load(open(os.path.join(root, "bulk_data.json")))
    print(f"loaded {len(cards)} card records", flush=True)

    bits_list, ids, meta = [], [], []
    n_ok = n_missing = n_readfail = 0
    for c in cards:
        cid = c.get("id")
        p = os.path.join(img_dir, f"{cid}.jpg")
        if not os.path.exists(p):
            n_missing += 1
            continue
        g = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
        if g is None:
            n_readfail += 1
            continue
        bits_list.append(dual_phash(g))
        ids.append(cid)
        meta.append({"id": cid, "name": c.get("name"),
                     "type_line": c.get("type_line"),
                     "mana_cost": c.get("mana_cost"),
                     "oracle_text": c.get("oracle_text")})
        n_ok += 1
        if n_ok % 5000 == 0:
            print(f"  {n_ok} hashed ({time.time()-t0:.0f}s)", flush=True)

    bits = np.array(bits_list, dtype=np.uint8)   # [N,64]
    np.savez(os.path.join(DATA_DIR, "phash_index.npz"), bits=bits, ids=np.array(ids))
    json.dump(meta, open(os.path.join(DATA_DIR, "phash_meta.json"), "w"))
    print(f"DONE ok={n_ok} missing={n_missing} readfail={n_readfail} "
          f"bits={bits.shape} in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
