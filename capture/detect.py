#!/usr/bin/env python3
"""
cardsense detector — event-driven zoomed-card detection + pHash matching.

Algorithm (see ../design.md):
  Stage A: cheap per-frame motion gate. Downsampled grayscale frame diff.
           A zoom animation produces motion; we wait for it to settle.
  Stage B: region proposal. Diff the settled frame against the pre-motion
           background frame, threshold, connected components. Card-shaped
           blobs (portrait aspect ~0.71, height 25-90% of frame) survive.
  Stage C: refine. Tight bbox of diff pixels at full resolution snaps the
           crop to the actual card border, independent of display scale.
  Stage D: match. Vectorized 256-bit pHash Hamming scan over all ~53K cards
           (numpy XOR + popcount table, ~ms). Accept only on confident
           match: best <= MAX_DIST and margin to the best *other-named*
           card >= MIN_MARGIN. Otherwise: silence (never guess).

Usage:
  python3 detect.py --loop              # live screen watching
  python3 detect.py --test shot.png     # offline: run stages B-D on an image
                                        # (diffed against a black background)
  python3 detect.py --test shot.png --bg empty_board.png
"""
import argparse
import os
import sqlite3
import subprocess
import sys
import time

import numpy as np
from PIL import Image

# --- Configuration ---
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "hashindex", "data", "index.sqlite")

# Geometry (all relative to frame height -> display-scale independent)
MIN_CARD_FRAC = 0.25    # zoomed card is at least 25% of frame height
MAX_CARD_FRAC = 0.92
ASPECT_MIN, ASPECT_MAX = 0.60, 0.85   # real card ratio ~0.716

# Motion gate
DOWNSAMPLE = 8          # stage-A works on 1/8 resolution grayscale
MOTION_THRESH = 6.0     # mean abs diff (0-255) above this = motion
SETTLE_FRAMES = 2       # quiet frames required after motion before we look
DIFF_PIX_THRESH = 25    # per-pixel diff threshold for the region mask

# Matching
MAX_DIST = 60           # of 256 bits; correct matches historically 0-16
MIN_MARGIN = 25         # best other-named card must be this much worse
INSETS = (-0.04, -0.02, 0.0, 0.02, 0.04)  # fractional crop adjustments
                                          # (negative = expand beyond box)

SPEECH_RATE = 350
COOLDOWN = 5.0
FRAME_INTERVAL = 0.20

POPCOUNT = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(1).astype(np.uint16)

current_say_proc = None


def speak(text, interrupt=True):
    global current_say_proc
    if interrupt and current_say_proc and current_say_proc.poll() is None:
        current_say_proc.kill()
    current_say_proc = subprocess.Popen(["say", "-r", str(SPEECH_RATE), text])


# ---------------- index loading / matching (Stage D) ----------------

class CardIndex:
    def __init__(self, db_path):
        if not os.path.exists(db_path):
            raise SystemExit(f"[cardsense] ERROR: index not found at {db_path}")
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT scryfall_id, name, mana_cost, type_line, oracle_text,"
            " power, toughness, phash FROM cards WHERE phash IS NOT NULL"
        ).fetchall()
        conn.close()
        self.meta = [r[:7] for r in rows]
        # 64 hex chars = 256 bits = 32 bytes per card
        self.hashes = np.frombuffer(
            bytes.fromhex("".join(r[7] for r in rows)), dtype=np.uint8
        ).reshape(len(rows), 32)
        print(f"[cardsense] loaded {len(rows)} card hashes")

    def query(self, img):
        """Return (best_dist, meta, margin_to_other_name). Vectorized scan."""
        import imagehash
        q = np.packbits(imagehash.phash(img, hash_size=16).hash.flatten())
        dists = POPCOUNT[np.bitwise_xor(self.hashes, q[None, :])].sum(axis=1)
        order = np.argsort(dists)
        best = order[0]
        best_name = self.meta[best][1]
        margin = 256
        for j in order[1:200]:
            if self.meta[j][1] != best_name:
                margin = int(dists[j]) - int(dists[best])
                break
        return int(dists[best]), self.meta[best], margin

    def match_crop(self, frame_rgb, box):
        """Try crops at several insets/outsets around box; most confident wins.
        Outsets recover card borders that blend into the background and get
        clipped by the diff-based tight bbox."""
        x, y, w, h = box
        H, W = frame_rgb.shape[:2]
        best = (999, None, 0)
        for adj in INSETS:
            dx, dy = int(w * adj), int(h * adj)
            x0, y0 = max(0, x + dx), max(0, y + dy)
            x1, y1 = min(W, x + w - dx), min(H, y + h - dy)
            if x1 - x0 < 50 or y1 - y0 < 50:
                continue
            sub = Image.fromarray(frame_rgb[y0:y1, x0:x1])
            d, meta, margin = self.query(sub)
            if d < best[0]:
                best = (d, meta, margin)
        return best


# ---------------- region proposal (Stages B & C) ----------------

def find_card_regions(frame_rgb, background_rgb):
    """Diff settled frame against background (max abs channel diff — catches
    dark card borders on dark felt that a grayscale diff misses); return list
    of (x, y, w, h) full-resolution card-shaped boxes."""
    from scipy import ndimage

    H = frame_rgb.shape[0]
    diff = np.abs(frame_rgb.astype(np.int16)
                  - background_rgb.astype(np.int16)).max(axis=2)
    mask = ndimage.binary_closing(diff > DIFF_PIX_THRESH,
                                  structure=np.ones((7, 7), bool))

    # Label on a downsampled mask so nearby noise doesn't merge and it's cheap.
    small = mask[::DOWNSAMPLE, ::DOWNSAMPLE]
    labels, n = ndimage.label(small)
    if n == 0:
        return []

    regions = []
    for sl in ndimage.find_objects(labels):
        y0, y1 = sl[0].start * DOWNSAMPLE, sl[0].stop * DOWNSAMPLE
        x0, x1 = sl[1].start * DOWNSAMPLE, sl[1].stop * DOWNSAMPLE
        h, w = y1 - y0, x1 - x0
        if not (MIN_CARD_FRAC * H <= h <= MAX_CARD_FRAC * H):
            continue

        # Stage C: snap to tight bbox of diff pixels at full resolution.
        pad = DOWNSAMPLE * 2
        ys = max(0, y0 - pad); ye = min(mask.shape[0], y1 + pad)
        xs = max(0, x0 - pad); xe = min(mask.shape[1], x1 + pad)
        sub = mask[ys:ye, xs:xe]
        rows = np.where(sub.any(axis=1))[0]
        cols = np.where(sub.any(axis=0))[0]
        if len(rows) == 0 or len(cols) == 0:
            continue
        fy0, fy1 = ys + rows[0], ys + rows[-1] + 1
        fx0, fx1 = xs + cols[0], xs + cols[-1] + 1
        fh, fw = fy1 - fy0, fx1 - fx0
        if fh == 0 or not (ASPECT_MIN <= fw / fh <= ASPECT_MAX):
            continue
        if not (MIN_CARD_FRAC * H <= fh <= MAX_CARD_FRAC * H):
            continue
        # Solidity: the diff blob should mostly fill its bbox (cards are solid)
        fill = mask[fy0:fy1, fx0:fx1].mean()
        if fill < 0.70:
            continue
        regions.append((fx0, fy0, fw, fh))

    return sorted(regions, key=lambda r: r[0])  # left-to-right


def to_gray(frame_rgb):
    return (0.299 * frame_rgb[:, :, 0] + 0.587 * frame_rgb[:, :, 1]
            + 0.114 * frame_rgb[:, :, 2]).astype(np.uint8)


# ---------------- main loops ----------------

def announce(matches):
    parts = []
    for dist, meta, margin in matches:
        name, mana, type_line, oracle = meta[1], meta[2], meta[3], meta[4]
        pt = f" {meta[5]}/{meta[6]}." if meta[5] else ""
        parts.append(f"{name}. {type_line}.{pt} {oracle}")
    speak(" ... ".join(parts))


def process_frame(frame_rgb, background_rgb, index, verbose=True):
    """Stages B-D on one settled frame. Returns list of confident matches."""
    regions = find_card_regions(frame_rgb, background_rgb)
    confident = []
    for (x, y, w, h) in regions:
        dist, meta, margin = index.match_crop(frame_rgb, (x, y, w, h))
        if verbose:
            status = "MATCH" if (dist <= MAX_DIST and margin >= MIN_MARGIN) else "reject"
            print(f"  region ({x},{y},{w}x{h}) -> {meta[1]!r} dist={dist} margin={margin} [{status}]")
        if dist <= MAX_DIST and margin >= MIN_MARGIN:
            confident.append((dist, meta, margin))
    return confident


def run_loop():
    import mss
    index = CardIndex(DB_PATH)
    speak("Card sense active")

    last_spoken_ids = frozenset()
    last_spoken_time = 0.0
    last_heartbeat = 0.0

    prev_small = None
    background_rgb = None    # last known quiet frame BEFORE motion started
    pending_bg = None        # candidate background, promoted when quiet
    motion_active = False
    quiet_count = 0

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        while True:
            now = time.time()
            if now - last_heartbeat > 10:
                print(f"[cardsense] {time.strftime('%H:%M:%S')} scanning...")
                last_heartbeat = now

            raw = sct.grab(monitor)
            frame = np.array(Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX"))
            gray = to_gray(frame)
            small = gray[::DOWNSAMPLE, ::DOWNSAMPLE].astype(np.int16)

            if prev_small is None:
                prev_small = small
                background_rgb = frame
                time.sleep(FRAME_INTERVAL)
                continue

            motion = float(np.abs(small - prev_small).mean())
            prev_small = small

            if motion > MOTION_THRESH:
                if not motion_active:
                    motion_active = True
                    # background = the quiet frame we were holding
                    if pending_bg is not None:
                        background_rgb = pending_bg
                quiet_count = 0
            else:
                quiet_count += 1
                if motion_active and quiet_count >= SETTLE_FRAMES:
                    # Motion just settled: look for newly-appeared cards.
                    motion_active = False
                    matches = process_frame(frame, background_rgb, index)
                    ids = frozenset(m[1][0] for m in matches)
                    if matches and (ids != last_spoken_ids
                                    or now - last_spoken_time > COOLDOWN):
                        print(f"[cardsense] >>> speaking: "
                              f"{', '.join(m[1][1] for m in matches)}")
                        announce(matches)
                        last_spoken_ids = ids
                        last_spoken_time = now
                elif not motion_active and quiet_count >= SETTLE_FRAMES:
                    pending_bg = frame  # a stable frame; future background

            time.sleep(FRAME_INTERVAL)


def run_test(image_path, bg_path=None):
    index = CardIndex(DB_PATH)
    frame = np.array(Image.open(image_path).convert("RGB"))
    if bg_path:
        bg = np.array(Image.open(bg_path).convert("RGB"))
    else:
        bg = np.zeros_like(frame)
        print("[cardsense] no --bg given: diffing against black "
              "(region proposal will be generous)")
    matches = process_frame(frame, bg, index)
    for dist, meta, margin in matches:
        print(f"MATCH: {meta[1]} (dist={dist}, margin={margin})")
        print(f"  {meta[3]} | {meta[4][:120]}")
    if not matches:
        print("No confident matches.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="live screen watching")
    ap.add_argument("--test", metavar="IMG", help="run detection on an image file")
    ap.add_argument("--bg", metavar="IMG", help="background image for --test")
    args = ap.parse_args()
    if args.test:
        run_test(args.test, args.bg)
    else:
        run_loop()
