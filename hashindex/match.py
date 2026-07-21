#!/usr/bin/env python3
"""
match.py — given an image (e.g. a cropped screen capture of a zoomed card),
find the nearest card in the hash index by Hamming distance.

Usage:
    python3 match.py path/to/cropped_card.png
    python3 match.py --self-test   # simulate a "screen capture" of an indexed
                                    # card (resize+recompress) and verify match

This is the runtime lookup half of the pipeline described in ../design.md.
No OCR anywhere — pure perceptual hash nearest-neighbor.
"""
import argparse
import glob
import os
import random
import sqlite3
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DATA_DIR, "index.sqlite")
IMAGES_DIR = os.path.join(DATA_DIR, "images")


def load_index(conn):
    """Load all (scryfall_id, name, phash) rows into memory as int hashes."""
    cur = conn.cursor()
    cur.execute("SELECT scryfall_id, name, phash, oracle_text, mana_cost, type_line FROM cards")
    rows = cur.fetchall()
    return rows


def hamming(hash_a: str, hash_b: str) -> int:
    """Hex-string hash Hamming distance."""
    a = int(hash_a, 16)
    b = int(hash_b, 16)
    return bin(a ^ b).count("1")


def match_image(img, rows, top_n=3):
    import imagehash
    query_hash = str(imagehash.phash(img, hash_size=16))
    scored = []
    for scryfall_id, name, phash, oracle_text, mana_cost, type_line in rows:
        d = hamming(query_hash, phash)
        scored.append((d, scryfall_id, name, oracle_text, mana_cost, type_line))
    scored.sort(key=lambda x: x[0])
    return scored[:top_n]


def self_test():
    """Pick a random indexed image, simulate a screen-capture crop
    (resize down then up, JPEG recompress) and confirm nearest match is itself."""
    from PIL import Image
    import io

    conn = sqlite3.connect(DB_PATH)
    rows = load_index(conn)
    if not rows:
        print("Index is empty — run build_index.py first.")
        sys.exit(1)

    image_files = glob.glob(os.path.join(IMAGES_DIR, "*.jpg"))
    if not image_files:
        print("No downloaded images found.")
        sys.exit(1)

    random.seed(42)
    sample = random.sample(image_files, min(10, len(image_files)))

    correct = 0
    for path in sample:
        cid = os.path.splitext(os.path.basename(path))[0]
        img = Image.open(path).convert("RGB")

        # Simulate degradation similar to a screen-capture crop: downscale,
        # upscale, recompress as JPEG at moderate quality — approximates what
        # a cropped screen region would look like vs. the pristine source image.
        w, h = img.size
        degraded = img.resize((w // 2, h // 2)).resize((w, h))
        buf = io.BytesIO()
        degraded.save(buf, format="JPEG", quality=70)
        buf.seek(0)
        degraded = Image.open(buf).convert("RGB")

        results = match_image(degraded, rows, top_n=3)
        best = results[0]
        second = results[1] if len(results) > 1 else None
        gap = (second[0] - best[0]) if second else None
        is_correct = best[1] == cid
        correct += is_correct
        status = "OK " if is_correct else "FAIL"
        print(f"[{status}] true={cid[:8]} matched={best[1][:8]} name={best[2]!r} "
              f"dist={best[0]} gap_to_2nd={gap} (2nd={second[2]!r} dist={second[0]})")
        if not is_correct:
            print(f"       (true card was: {[r for r in rows if r[0]==cid][0][1]!r})")

    print(f"\nSelf-test: {correct}/{len(sample)} correct")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?", help="path to image to match")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--top", type=int, default=3)
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.image:
        ap.error("provide an image path or --self-test")

    from PIL import Image
    conn = sqlite3.connect(DB_PATH)
    rows = load_index(conn)
    img = Image.open(args.image).convert("RGB")
    results = match_image(img, rows, top_n=args.top)
    for d, cid, name, oracle_text, mana_cost, type_line in results:
        print(f"dist={d:3d}  {name}  ({mana_cost})  {type_line}")
        if d == results[0][0]:
            print(f"          {oracle_text}")


if __name__ == "__main__":
    main()
