#!/usr/bin/env python3
"""cardsense detector — find the PRESENTED (highlighted/zoomed) card on screen
and read it aloud.

Key idea (Bill's, confirmed on real captures): the presented card is
distinguished by SIZE — it renders much larger than hand/board cards. So we look
for the largest card-shaped region above a height threshold, crop it, and match
it against the pHash index (hashindex/phash.py). Text on the rest of the screen
is ignored entirely.

Pipeline:
  Stage L (localize): edge map -> contours -> keep card-shaped (aspect ~0.71)
      regions -> the presented card is the largest one with height fraction
      >= PRESENT_HF. If none, nothing is being presented -> stay silent.
  Stage M (match): dual full+art pHash -> Hamming scan over ~53K cards ->
      confident match or silence (never guess).
  Stage S (speak): spd-say the card name + type + oracle text.

Usage:
  python3 detect.py --test "shot.png"       # offline: identify card in a screenshot
  python3 detect.py --test "shot.png" --quiet   # print only, don't speak
  python3 detect.py --loop                   # live screen watching (needs mss)

Calibration (next): a one-time "hover a card, hold" gesture locks the presented
card SIZE for this display (position varies, size is constant per display x UI
scale), which removes localization misses and tightens the match threshold.
"""
import argparse
import os
import subprocess
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hashindex"))
from phash import CardIndex  # noqa: E402

# --- Localization geometry (fractions of frame height -> scale independent) ---
ASPECT_MIN, ASPECT_MAX = 0.58, 0.88     # real card ratio ~0.716
PRESENT_HF = 0.35                        # presented card >= 35% of frame height
                                         # (measured: presented ~0.44-0.48, hand ~0.21)
# --- Speech ---
SPEECH_RATE = 200                        # spd-say -r (words/min-ish)
_say_proc = None


def speak(text, rate=SPEECH_RATE, interrupt=True):
    """Speak via spd-say (Linux speech-dispatcher)."""
    global _say_proc
    if interrupt and _say_proc and _say_proc.poll() is None:
        _say_proc.terminate()
    _say_proc = subprocess.Popen(["spd-say", "-r", str(rate), text])


def find_presented(frame_bgr):
    """Return (x,y,w,h) of the presented card, or None if none is presented."""
    H, W = frame_bgr.shape[:2]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 40, 120), np.ones((5, 5), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None  # (height, box)
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if h == 0:
            continue
        ar, hf = w / h, h / H
        if ASPECT_MIN <= ar <= ASPECT_MAX and hf >= PRESENT_HF:
            if best is None or h > best[0]:
                best = (h, (x, y, w, h))
    return best[1] if best else None


def describe(meta):
    """Build the spoken/printed description of a card."""
    parts = [meta.get("name") or "Unknown card"]
    if meta.get("type_line"):
        parts.append(meta["type_line"])
    if meta.get("oracle_text"):
        parts.append(meta["oracle_text"])
    return ". ".join(parts)


def handle_frame(frame_bgr, idx, quiet=False, verbose=False):
    """Localize + identify the presented card in one frame. Returns meta or None."""
    box = find_presented(frame_bgr)
    if box is None:
        if verbose:
            print("  (no card presented)")
        return None
    x, y, w, h = box
    crop = cv2.cvtColor(frame_bgr[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    hit = idx.identify(crop)
    if hit is None:
        if verbose:
            print(f"  card at {box} but no confident match")
        return None
    meta, dist, margin = hit
    text = describe(meta)
    print(f"  MATCH: {meta['name']}  (dist={dist} margin={margin})")
    if not quiet:
        speak(text)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", metavar="IMG", help="identify the card in a screenshot")
    ap.add_argument("--loop", action="store_true", help="live screen watching (needs mss)")
    ap.add_argument("--quiet", action="store_true", help="print only, do not speak")
    ap.add_argument("--interval", type=float, default=0.5, help="loop poll seconds")
    a = ap.parse_args()

    idx = CardIndex()
    print(f"loaded index: {len(idx)} cards")

    if a.test:
        frame = cv2.imread(a.test)
        if frame is None:
            raise SystemExit(f"cannot read {a.test}")
        print(f"=== {os.path.basename(a.test)} ===")
        handle_frame(frame, idx, quiet=a.quiet, verbose=True)
        return

    if a.loop:
        try:
            import mss  # noqa
        except ImportError:
            raise SystemExit("live --loop needs mss: pip install mss")
        last_name = None
        with mss.mss() as sct:
            mon = sct.monitors[1]
            print("watching screen (Ctrl-C to stop)...")
            while True:
                shot = np.array(sct.grab(mon))[:, :, :3]  # BGRA->BGR
                meta = handle_frame(shot, idx, quiet=a.quiet)
                if meta and meta["name"] != last_name:
                    last_name = meta["name"]
                elif meta is None:
                    last_name = None
                time.sleep(a.interval)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
