#!/usr/bin/env python3
"""
detect.py — screen capture loop that finds zoomed MTG cards using static
image edge detection (OpenCV), looks them up via pHash, and speaks the result.

Detection strategy (Static Image):
- Convert frame to grayscale, apply Canny edge detection.
- Find contours and their bounding boxes.
- Filter by size (~200-280px wide, ~300-450px tall) and aspect ratio (0.52-0.82).
- Sort left-to-right to handle multiple cards naturally.
- TTS Interruption: If a new card is detected, instantly kill the old speech.

Run modes:
    python3 detect.py --loop          # continuous loop with TTS (main mode)
    python3 detect.py --loop --debug  # also saves crops to /tmp
"""

import argparse
import os
import sqlite3
import subprocess
import sys
import time

import cv2
import mss
import numpy as np
from PIL import Image

HASHINDEX_DIR = os.path.join(os.path.dirname(__file__), "..", "hashindex")
DB_PATH = os.path.join(HASHINDEX_DIR, "data", "index.sqlite")

# --- Tunable constants ---
MIN_CARD_W   = 160   # minimum card width in actual pixels
MIN_CARD_H   = 250   # minimum card height in actual pixels
MAX_CARD_W   = 380   # upper bound (bigger = it's a tooltip or screen transition)
MAX_CARD_H   = 520
ASPECT_MIN   = 0.52  # width/height
ASPECT_MAX   = 0.82
COOLDOWN     = 2.0   # don't re-announce same exact set of cards this soon
MAX_DIST     = 20    # max pHash Hamming distance to accept a match (256-bit)

# Global tracker for the TTS process so we can interrupt it
current_say_proc = None


def load_index(db_path):
    if not os.path.exists(db_path):
        print(f"[cardsense] WARNING: no index at {db_path} — run build_index.py first")
        return []
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""SELECT scryfall_id, name, mana_cost, type_line,
                          oracle_text, power, toughness, phash FROM cards""")
    rows = cur.fetchall()
    conn.close()
    print(f"[cardsense] {len(rows)} cards in index")
    return rows


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def match_card(img: Image.Image, rows):
    import imagehash
    q = str(imagehash.phash(img, hash_size=16))
    best_dist, best_row = 9999, None
    for row in rows:
        d = hamming(q, row[7])
        if d < best_dist:
            best_dist, best_row = d, row
    return best_dist, best_row


def card_speech(row):
    _, name, mana_cost, type_line, oracle_text, power, toughness, _ = row
    parts = [name]
    if mana_cost:
        cost = mana_cost.replace("{", "").replace("}", " ").strip()
        parts.append(cost)
    if type_line:
        parts.append(type_line)
    if oracle_text:
        parts.append(oracle_text.strip())
    if power and toughness:
        parts.append(f"{power} slash {toughness}")
    return ". ".join(parts)


def speak(text: str):
    global current_say_proc
    # Interrupt previous speech if it's still running
    if current_say_proc is not None and current_say_proc.poll() is None:
        current_say_proc.kill()
    
    current_say_proc = subprocess.Popen(["say", "-r", "260", text])


def grab_frame(sct) -> np.ndarray:
    raw = sct.grab(sct.monitors[1])
    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    return np.array(img)


def find_card_regions_static(frame: np.ndarray, debug=False):
    """
    Find portrait-shaped card-sized regions using OpenCV edge detection.
    Returns list of (x, y, w, h) sorted left-to-right.
    """
    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    
    # Canny edge detection
    edges = cv2.Canny(gray, 50, 150)
    
    # Dilate edges slightly to close gaps in card borders
    kernel = np.ones((5, 5), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    
    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    candidates = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        
        if w < MIN_CARD_W or h < MIN_CARD_H:
            continue
        if w > MAX_CARD_W or h > MAX_CARD_H:
            continue
            
        aspect = w / float(h)
        if not (ASPECT_MIN <= aspect <= ASPECT_MAX):
            continue
            
        candidates.append((x, y, w, h))
        
    # Sort left-to-right
    candidates.sort(key=lambda r: r[0])
    
    # Deduplicate overlapping bounding boxes (sometimes contours nest)
    deduped = []
    for c in candidates:
        x, y, w, h = c
        overlap = False
        for dx, dy, dw, dh in deduped:
            # Simple intersection check
            if not (x + w < dx or dx + dw < x or y + h < dy or dy + dh < y):
                overlap = True
                break
        if not overlap:
            deduped.append(c)
            
    return deduped


def crop_region(frame: np.ndarray, x, y, w, h) -> Image.Image:
    inset = 6
    return Image.fromarray(
        frame[max(0,y+inset):min(frame.shape[0],y+h-inset),
              max(0,x+inset):min(frame.shape[1],x+w-inset)]
    )


def run_loop(debug=False):
    index = load_index(DB_PATH)
    if not index:
        print("[cardsense] no index — run hashindex/build_index.py first")
        sys.exit(1)

    print("[cardsense] watching screen... Ctrl-C to stop")
    last_spoken_ids = set()
    last_spoken_time = 0.0

    with mss.MSS() as sct:
        while True:
            frame = grab_frame(sct)
            regions = find_card_regions_static(frame, debug)

            if regions:
                current_ids = []
                speech_parts = []
                
                for i, (x, y, w, h) in enumerate(regions):
                    crop = crop_region(frame, x, y, w, h)
                    dist, row = match_card(crop, index)
                    
                    if dist <= MAX_DIST:
                        card_id = row[0]
                        current_ids.append(card_id)
                        speech_parts.append(card_speech(row))
                        
                        if debug:
                            crop.save(f"/tmp/cs_{row[1].replace(' ','_')}_{i}.png")
                    else:
                        if debug:
                            crop.save(f"/tmp/cs_unmatched_{int(time.time())}_{i}.png")
                
                current_ids_set = frozenset(current_ids)
                
                # If we found valid cards, and they are DIFFERENT from what we just spoke
                # OR enough time has passed (cooldown), speak them.
                if current_ids and (current_ids_set != last_spoken_ids or time.time() - last_spoken_time > COOLDOWN):
                    combined_speech = " ... ".join(speech_parts)
                    names = [p.split('.')[0] for p in speech_parts]
                    print(f"[cardsense] Detected: {', '.join(names)}")
                    
                    speak(combined_speech)
                    
                    last_spoken_ids = current_ids_set
                    last_spoken_time = time.time()

            time.sleep(0.10)   # ~10fps


def main():
    ap = argparse.ArgumentParser(description="cardsense — MTGA card reader")
    ap.add_argument("--loop",  action="store_true", help="run capture loop (default)")
    ap.add_argument("--debug", action="store_true", help="save card crops to /tmp")
    args = ap.parse_args()
    run_loop(debug=args.debug)


if __name__ == "__main__":
    main()
