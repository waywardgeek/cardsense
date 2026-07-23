# cardsense — Next Steps

Status as of 2026-07-22 (Hewitt + Bill). This picks up on a personal laptop that
has **MTGA installed** for live testing. The hard technical risk — *can we
identify an on-screen card across the Scryfall↔MTGA render gap?* — is **retired**.
What remains is calibration, the live loop, tuning, and (optionally) a Go port.

---

## What works today (verified)

Pipeline: **localize the presented card by SIZE → dual pHash → scan 53,698 cards → speak.**

- **Matcher (solved).** Each card is fingerprinted by a 512-bit vector:
  `dual = phash(full_card) ++ phash(art_box)`, matched by Hamming distance.
  On 4 real MTGA captures (Badgermole Cub, Forest, Treetop Warden, Generous
  Stray) this identifies the correct card at **rank 0 of 53,698**, with
  correct-vs-nearest-wrong **margins of 30–58 bits** (whole-card pHash alone gave
  only 10–26; one case went 10→40). See `hashindex/phash.py` for the why.
- **Localization (works on clean frames).** `capture/detect.py:find_presented`
  keeps card-shaped contours (aspect 0.58–0.88) and returns the largest one with
  height ≥ 35% of the frame. Measured: presented cards ≈ 44–48% of frame height,
  hand cards ≈ 21%. It **misses** cards on busy/low-contrast backgrounds — this is
  what calibration fixes (below).
- **Confidence gate.** `CardIndex.identify` returns a card only if best distance
  ≤ `max_dist` (default 190) AND margin ≥ `min_margin` (default 20). Otherwise it
  stays **silent** — never guesses. Right default for an accessibility tool.

Quick check on the laptop once the index is built:
```bash
python3 capture/detect.py --test some_screenshot.png     # prints + speaks the card
python3 hashindex/match.py some_crop.png --expect "Card Name"   # debug/margins
```

---

## Laptop setup

1. **Python deps** (venv recommended):
   ```bash
   python3 -m venv venv
   ./venv/bin/pip install pillow numpy opencv-python-headless mss
   ```
   (`mss` is only needed for the live `--loop`; `--test` works without it.)
2. **TTS**: macOS uses `say` (built in), Linux uses `spd-say`. `detect.py:speak`
   auto-detects the platform — nothing to install on macOS.
3. **Build the index** (needs the Scryfall dump — see next). ~6 min for 53K cards.

### Getting the card data
The index is built from a Scryfall dump: `data/bulk_data.json` (all card records)
+ `data/images/<scryfall-id>.jpg` (one image per card). Two options:
- **Reuse the existing dump**: `scryfall_cards.zip` (~6 GB, 53,702 files). Unzip so
  you have `<dir>/data/bulk_data.json` and `<dir>/data/images/`, then:
  ```bash
  python3 hashindex/build_index.py --scryfall <dir>
  ```
- **Fresh from Scryfall**: download the "Default Cards" bulk JSON from
  <https://scryfall.com/docs/api/bulk-data>, then fetch each card's
  `image_uris.normal` into `data/images/<id>.jpg`. (The old `build_index.py`
  history has downloader code if useful.)

Output (git-ignored, ~25 MB): `hashindex/data/phash_index.npz` +
`hashindex/data/phash_meta.json`. **The index format is `bits:[N,64] uint8`** —
if you change `HASH_SIZE`/`ART_BOX`/`CW`/`CH` in `phash.py` you MUST rebuild it.

---

## Prioritized next steps

### 1. Bring up the live loop (`--loop`)  ← start here
```bash
python3 capture/detect.py --loop
```
- macOS will prompt for **Screen Recording permission** the first time `mss`
  grabs the screen (System Settings → Privacy & Security → Screen Recording).
  Grant it to your terminal/Python.
- Multi-monitor: `--loop` uses `sct.monitors[1]` (primary). If MTGA is on another
  display, add a `--monitor N` flag.
- Watch the console MATCH lines while hovering cards in a real game. This is the
  first true end-to-end test on live MTGA.

### 2. Size calibration (the key robustness lever)
Bill's idea, confirmed: the presented card's **size is constant** for a given
display × UI-scale (only its *position* varies). One-time calibration removes the
localization misses and tightens the threshold.
- **Flow**: `python3 capture/detect.py --calibrate` → prompt "hover a card and hold"
  → capture a before frame + an after frame → **diff** them; the changed region is
  the presented card (unambiguous, no fragile edge-detection needed). Record its
  **width×height in pixels** to `~/.cardsense/calib.json` keyed by screen
  resolution.
- **Payoff**: at runtime, region proposal only accepts components matching the
  calibrated size (±~10%) → far fewer misses/false regions, and the scale
  ambiguity in cropping goes away.
- **Bonus**: the calibration frame is a labeled `(MTGA-render, card-id)` pair —
  match it to measure the *actual* domain-gap distance on THIS display and set
  `max_dist`/`min_margin` from real data instead of the hardcoded 190/20.

### 3. Threshold tuning on live data
Collect `dist`/`margin` on a session of real hovers (correct + silent cases).
Set `max_dist`/`min_margin` so it never speaks a wrong card but rarely stays
silent on a real one. Current defaults (190/20) are conservative starting points
in the 512-bit space.

### 4. UX / read behavior (ask Bill)
- **Announce-on-change**: `--loop` already tracks `last_name`; only re-speak when
  the presented card changes (avoid repeating while you hold a hover).
- **What to read**: name only, or name + type + full oracle text? A **re-read
  hotkey** ("say it again, in full") is likely wanted since one pass is easy to miss.
- **Trigger model**: continuous polling vs. a **hotkey to read the current hover**
  (less chatter, more control). Bill decides — he's the user.
- **Speech rate**: `SAY_RATE_WPM`/`SPD_RATE` in `detect.py`. Bill listens fast.

### 5. Localization hardening
- With calibration (step 2), consider replacing Canny-contours with
  **background-diff → threshold → connected-components of the calibrated size**
  (simpler and Go-portable — no OpenCV-only ops).
- Handle the **hover-tooltip merge** case (a tooltip can fuse with the card into
  one blob): split on the size prior, or prefer the region matching calibrated W×H.

### 6. Go single-binary port (optional, for daily use)
The algorithm was kept Go-portable on purpose (resize / DCT / median / XOR /
popcount only). Matching is trivial Go (XOR + popcount over `[N,64]`). With
calibration, detection is diff + threshold + connected-components — **pure Go, no
gocv/OpenCV C dependency needed**. Ship as one `cardsense` binary (no venv rot)
for a tool used every game.

### 7. Rewrite `design.md` and `README.md`
Both are currently **stale CodeRhapsody copy-paste — ignore them entirely**.
Write a real `design.md` documenting the pipeline + the measured decisions
(dual full+art pHash, art-box coords, text-region-poison finding, size
calibration), and a `README.md` with the setup above.

---

## Key facts & gotchas (so nobody rediscovers them)

- **Domain gap is real but beaten.** Scryfall paper scans vs MTGA digital renders:
  the *correct* card lands at ~120–144 / 512 bits, nearest wrong at ~176–186.
  Separation exists; the full+art ensemble makes it comfortable.
- **Text regions are POISON.** Title/rules-text bands scored *negative* margins
  (MTGA fonts/anti-aliasing ≠ Scryfall). This is why we hash the **art box**
  `(y0,y1,x0,x1) = (0.11, 0.56, 0.06, 0.94)` and why **OCR-the-name was the wrong
  path**. Don't revisit OCR.
- **Single-scanline fingerprint: tested, dead.** Any single horizontal band is
  ~44% bit-error (near random) across the gap. Killed with data. The whole-card
  aggregate wins; the sub-region idea only works as a 2D hash of the *art*.
- **Search speed is NOT the bottleneck.** Linear XOR+popcount over 53K × 64 B is
  ~ms in numpy. Don't build a fancy ANN index; accuracy/margin was the problem,
  and that's solved. (Multi-index hashing would only matter at millions of cards.)
- **Basic lands have many printings** — treat any card with the matching *name* as
  correct; the matcher naturally picks the closest art printing.
- **macOS screenshot filenames** contain a narrow no-break space `\u202f` before
  "PM" — glob them, don't type the names.
- **Index is git-ignored** (`hashindex/data/`), as is `venv/` and the Scryfall
  dump. The repo ships code only; each machine builds its own index.

---

## Open questions for Bill
1. Trigger model: continuous polling, or hotkey-to-read-current-hover?
2. Read name-only or full oracle text? Re-read hotkey?
3. Ship as Python (simple now) or invest in the Go binary (nicer daily UX)?
