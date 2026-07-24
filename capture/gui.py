#!/usr/bin/env python3
"""cardsense GUI — card detector with speed/voice controls.

Launch this instead of detect.py --loop for a controllable live session.
"""
import os
import platform
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hashindex"))
from phash import CardIndex  # noqa: E402

# ── Localization (frame-diff) ──────────────────────────────────────────────
ASPECT_MIN, ASPECT_MAX = 0.50, 0.95   # widened to catch hover + right-click zoom
PRESENT_HF = 0.25                      # lowered: hover cards ~35-48%, right-click ~80%
DIFF_THRESH = 25
MIN_BLOB_PX = 500


DS = 4  # downsample factor for fast diff


def find_presented(frame_bgr, background, debug=False):
    """Return (x,y,w,h) of the presented card, or None.

    Uses cv2.absdiff at full res (~22ms). The background must be recent
    (updated every quiet frame) so only the zoomed card shows in the diff.
    """
    if background is None:
        if debug:
            print("[FIND] no background", flush=True)
        return None
    H, W = frame_bgr.shape[:2]
    diff = np.max(cv2.absdiff(frame_bgr, background), axis=2)
    diff_mean = np.mean(diff)
    diff_max = np.max(diff)
    mask = (diff > DIFF_THRESH).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if debug:
        print(f"[FIND] diff mean={diff_mean:.1f} max={diff_max} labels={n_labels-1} mask_pct={np.count_nonzero(mask)*100/(H*W):.1f}%", flush=True)
    best = None
    for i in range(1, n_labels):
        x, y, w, h, area = stats[i]
        if area < MIN_BLOB_PX or h == 0:
            continue
        ar, hf = w / h, h / H
        if debug and area > 5000:
            passed = ASPECT_MIN <= ar <= ASPECT_MAX and hf >= PRESENT_HF
            print(f"  blob {i}: {w}x{h} ar={ar:.2f} hf={hf:.2f} area={area} {'PASS' if passed else 'FAIL'}", flush=True)
        if ASPECT_MIN <= ar <= ASPECT_MAX and hf >= PRESENT_HF:
            if best is None or h > best[0]:
                best = (h, (x, y, w, h))
    return best[1] if best else None


def find_all_candidates(frame_bgr, background):
    """Return list of (x,y,w,h) for all card-shaped diff blobs.

    Unlike find_presented which returns only the tallest, this returns all
    candidates so the caller can try identifying each one.
    """
    if background is None:
        return []
    H, W = frame_bgr.shape[:2]
    diff = np.max(cv2.absdiff(frame_bgr, background), axis=2)
    mask = (diff > DIFF_THRESH).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    results = []
    for i in range(1, n_labels):
        x, y, w, h, area = stats[i]
        if area < MIN_BLOB_PX or h == 0:
            continue
        ar, hf = w / h, h / H
        if ASPECT_MIN <= ar <= ASPECT_MAX and hf >= PRESENT_HF:
            results.append((x, y, w, h))
    return results


def describe(meta):
    parts = [meta.get("name") or "Unknown"]
    if meta.get("type_line"):
        parts.append(meta["type_line"])
    if meta.get("oracle_text"):
        parts.append(meta["oracle_text"])
    return ". ".join(parts)


# ── TTS (macOS NSSpeechSynthesizer — in-process, OS priority) ──────────────
class Speaker:
    """Uses NSSpeechSynthesizer for instant, OS-prioritized speech."""

    def __init__(self):
        from AppKit import NSSpeechSynthesizer
        voice = 'com.apple.eloquence.en-US.Reed'
        self._synth = NSSpeechSynthesizer.alloc().initWithVoice_(voice)
        self._synth.setRate_(550)
        self.rate = 550
        self.voice = voice

    def set_rate(self, rate):
        self.rate = rate
        self._synth.setRate_(rate)

    def set_voice(self, voice_name):
        """Set voice by display name (e.g. 'Reed (English (US))')."""
        from AppKit import NSSpeechSynthesizer
        # Map display names to voice IDs
        voices = NSSpeechSynthesizer.availableVoices()
        for v in voices:
            attrs = NSSpeechSynthesizer.attributesForVoice_(v)
            if attrs and voice_name in str(attrs.get('VoiceName', '')):
                self._synth.setVoice_(v)
                self.voice = voice_name
                return
        # Fallback: try matching by keyword
        key = voice_name.split('(')[0].strip().lower()
        for v in voices:
            if key in v.lower():
                self._synth.setVoice_(v)
                self.voice = voice_name
                return

    def cancel(self):
        self._synth.stopSpeaking()

    def is_speaking(self):
        return self._synth.isSpeaking()

    def speak(self, text):
        self._synth.stopSpeaking()
        self._synth.startSpeakingString_(text)


# ── Detector loop (runs in background thread) ─────────────────────────────
class Detector:
    def __init__(self, speaker, on_status=None):
        self.speaker = speaker
        self.on_status = on_status  # callback(str) for GUI status label
        self.running = False
        self._thread = None
        self.idx = None
        self.interval = 0.15  # seconds between frames
        self.fps = 0.0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        self.speaker.cancel()

    def _set_status(self, text):
        if self.on_status:
            self.on_status(text)

    def _loop(self):
        try:
            self._loop_inner()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[ERROR] Detector crashed: {e}", flush=True)
            self._set_status(f"ERROR: {e}")

    def _loop_inner(self):
        try:
            import mss
        except ImportError:
            self._set_status("ERROR: pip install mss")
            return

        if self.idx is None:
            self._set_status("Loading index...")
            self.idx = CardIndex()
            self._set_status(f"Index loaded: {len(self.idx)} cards")

        # Initial card box guess (fractions of screen) — left-side right-click zoom
        BOX_FRAC = (0.01, 0.04, 0.23, 0.65)  # (x_frac, y_frac, w_frac, h_frac)
        NO_CARD_FRAMES = 10

        last_name = None
        card_box = None
        calibrated = False
        no_card_count = 0

        with mss.MSS() as sct:
            mon = sct.monitors[1]
            H, W = mon["height"], mon["width"]

            bx = int(BOX_FRAC[0] * W)
            by = int(BOX_FRAC[1] * H)
            bw = int(BOX_FRAC[2] * W)
            bh = int(BOX_FRAC[3] * H)
            card_box = (bx, by, bw, bh)
            print(f"[INIT] screen={W}x{H} box=({bx},{by},{bw},{bh})", flush=True)

            self._set_status("Watching... right-click a card")
            while self.running:
                shot = np.array(sct.grab(mon))[:, :, :3]

                x, y, w, h = card_box
                crop = cv2.cvtColor(shot[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
                hit = self.idx.identify(crop)

                if hit:
                    meta, dist, margin = hit
                    name = meta["name"]

                    # Twiddle to refine the box on first successful match
                    if not calibrated:
                        print(f"[CALIBRATE] first match: {name} d={dist} m={margin}, twiddling...", flush=True)
                        debug = shot.copy()
                        cv2.rectangle(debug, (x, y), (x+w, y+h), (0, 255, 0), 3)
                        cv2.imwrite("/tmp/cardsense_box.png", debug)
                        cv2.imwrite("/tmp/cardsense_crop.png", crop)

                        card_box, dist, margin = self._twiddle(shot, card_box, self.idx)
                        calibrated = True
                        x, y, w, h = card_box
                        crop = cv2.cvtColor(shot[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
                        hit2 = self.idx.identify(crop)
                        if hit2:
                            meta, dist, margin = hit2
                            name = meta["name"]

                    no_card_count = 0
                    if name != last_name:
                        last_name = name
                        print(f"[DETECT] {name} d={dist} m={margin} box={card_box}", flush=True)
                        self._set_status(f"🃏 {name}  (d={dist} m={margin})")
                        self.speaker.speak(describe(meta))
                else:
                    no_card_count += 1
                    if no_card_count >= NO_CARD_FRAMES and last_name is not None:
                        last_name = None
                        self._set_status("Watching...")

        self._set_status("Stopped")

    @staticmethod
    def _twiddle(shot, box, idx):
        """Refine the crop box to minimize pHash distance.

        Nudge x, y, w, h by a percentage, keep if distance improves or
        stays equal. Run at 1% steps first, then 0.1% for fine tuning.
        """
        x, y, w, h = box
        H_max, W_max = shot.shape[:2]

        def score(bx, by, bw, bh):
            bx, by, bw, bh = int(bx), int(by), int(bw), int(bh)
            if bx < 0 or by < 0 or bw < 20 or bh < 20:
                return 9999
            if bx + bw > W_max or by + bh > H_max:
                return 9999
            crop = cv2.cvtColor(shot[by:by+bh, bx:bx+bw], cv2.COLOR_BGR2GRAY)
            hit = idx.identify(crop, max_dist=9999, min_margin=0)
            if hit is None:
                return 9999
            return hit[1]  # distance

        best_score = score(x, y, w, h)
        print(f"[TWIDDLE] start box=({x},{y},{w},{h}) dist={best_score}", flush=True)

        for pct in (0.01, 0.001):
            improved = True
            while improved:
                improved = False
                for dim in range(4):  # x, y, w, h
                    for sign in (+1, -1):
                        trial = [x, y, w, h]
                        step = max(1, int(trial[dim] * pct))
                        trial[dim] += sign * step
                        s = score(*trial)
                        if s <= best_score:
                            x, y, w, h = trial
                            best_score = s
                            improved = True

        print(f"[TWIDDLE] done  box=({x},{y},{w},{h}) dist={best_score}", flush=True)

        # Get margin for the final box
        crop = cv2.cvtColor(shot[y:y+h, x:x+w], cv2.COLOR_BGR2GRAY)
        hit = idx.identify(crop, max_dist=9999, min_margin=0)
        margin = hit[2] if hit else 0
        return (x, y, w, h), best_score, margin


# ── GUI ────────────────────────────────────────────────────────────────────
VOICES = [
    "Samantha", "Albert", "Daniel", "Eddy (English (US))", "Flo (English (US))",
    "Fred", "Junior", "Kathy", "Reed (English (US))", "Rocko (English (US))",
    "Sandy (English (US))", "Shelley (English (US))",
]


def build_gui():
    speaker = Speaker()
    detector = Detector(speaker)

    root = tk.Tk()
    root.title("CardSense")
    root.geometry("480x280")
    root.resizable(False, False)

    # Status label
    status_var = tk.StringVar(value="Press Start to begin")
    status_lbl = tk.Label(root, textvariable=status_var, font=("Helvetica", 14),
                          wraplength=460, justify="left", anchor="w")
    status_lbl.pack(padx=10, pady=(15, 5), fill="x")

    def set_status(text):
        status_var.set(text)

    detector.on_status = set_status

    # Speed slider
    speed_frame = tk.Frame(root)
    speed_frame.pack(padx=10, pady=5, fill="x")
    tk.Label(speed_frame, text="Speed (WPM):").pack(side="left")
    speed_val = tk.Label(speed_frame, text="700", width=4)
    speed_val.pack(side="right")
    speed_slider = tk.Scale(speed_frame, from_=150, to=900, orient="horizontal",
                            showvalue=False, length=300,
                            command=lambda v: _update_speed(v))
    speed_slider.set(550)
    speed_slider.pack(side="right", padx=(5, 5))

    def _update_speed(v):
        rate = int(float(v))
        speaker.set_rate(rate)
        speed_val.config(text=str(rate))

    # Voice picker
    voice_frame = tk.Frame(root)
    voice_frame.pack(padx=10, pady=5, fill="x")
    tk.Label(voice_frame, text="Voice:").pack(side="left")
    voice_combo = ttk.Combobox(voice_frame, values=VOICES, state="readonly", width=25)
    voice_combo.set("Reed (English (US))")
    voice_combo.pack(side="left", padx=(10, 0))

    def _update_voice(event):
        speaker.set_voice(voice_combo.get())

    voice_combo.bind("<<ComboboxSelected>>", _update_voice)

    # Test button
    def _test_voice():
        speaker.speak("Llanowar Elves. Creature, Elf Druid. Tap: Add one green mana.")

    tk.Button(voice_frame, text="Test", command=_test_voice).pack(side="left", padx=10)

    # Start / Stop
    btn_frame = tk.Frame(root)
    btn_frame.pack(padx=10, pady=15)

    def _start():
        detector.start()
        start_btn.config(state="disabled")
        stop_btn.config(state="normal")

    def _stop():
        detector.stop()
        start_btn.config(state="normal")
        stop_btn.config(state="disabled")
        set_status("Stopped")

    start_btn = tk.Button(btn_frame, text="▶  Start", command=_start,
                          font=("Helvetica", 13), width=10)
    start_btn.pack(side="left", padx=10)
    stop_btn = tk.Button(btn_frame, text="■  Stop", command=_stop,
                         font=("Helvetica", 13), width=10, state="disabled")
    stop_btn.pack(side="left", padx=10)

    def _on_close():
        detector.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()


if __name__ == "__main__":
    build_gui()
