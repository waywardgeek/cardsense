# cardsense — design doc

*Started 2026-07-20. Author: Bill Cox + CodeRhapsody.*

## Problem

Bill has macular dystrophy (20/180 vision) and plays MTG Arena, a Unity game with
zero native accessibility support (no NSAccessibility tree, no VoiceOver hooks —
Unity draws everything itself in a single Metal surface). He wants to hear a
description of whatever card the game is currently showing him large, without
hunting for it with a mouse and without learning ~40 keyboard shortcuts (the
approach taken by the Windows-only AccessibleArena mod, see prior art below).

## Key insight (Bill's, 2026-07-20)

MTGA already does the accessibility work for us, incidentally: whenever a
player needs to actually look closely at a card, the game **zooms it — large,
vertically oriented, centered, held steady for at least a moment.** This is a
UI convention built for sighted players who can't read a tiny board card either,
and it happens to be exactly the "I want this described to me" signal we need.
So: no mouse tracking, no hover-debounce tuning, no keyboard shortcuts. Just
watch the screen for that event.

Second insight, discussed same session: once we have a full, clean, stable
image of a zoomed card, we don't need OCR at all. The card's exact identity can
be recovered by **perceptual-hash matching against Scryfall's public card
image database** — this sidesteps every OCR failure mode (stylized fonts,
foils, mana symbols, non-English text, reminder-text formatting) and gives a
strictly better result: instead of reading noisy recognized text, we speak
Scryfall's ground-truth oracle text for the exact card/printing matched.

## Prior art: AccessibleArena

`https://jeanstiletto.github.io/AccessibleArena/` — Windows-only MelonLoader
mod that IL-patches (Harmony) directly into MTGA's Unity runtime, reads the
game's real internal card/zone objects, and speaks them via Tolk → NVDA/JAWS.
Extremely accurate (ground-truth data, not vision) but: Windows-only, fragile
across game patches (IL hooks break on internal structure changes), and
navigation-heavy (~40 keyboard shortcuts for zone/stack/target navigation,
modeled on Hearthstone Access). Built almost entirely with Claude Opus per
project's own disclosure.

cardsense deliberately takes the opposite architecture: **screen-only, no game
memory access, no code injection, no game-version coupling** — trading perfect
ground-truth accuracy for portability (works on Mac, survives every game patch
unmodified) and radically simpler interaction (zero shortcuts, one automatic
trigger).

## Architecture

```
[Screen capture loop] --diff--> [stable-region detector] --crop--> [pHash]
                                                                       |
                                                                       v
                                                   [Scryfall hash index] --match-->
                                                                       |
                                                                       v
                                                        [oracle text lookup] --> [TTS]
```

### 0. Multiple simultaneous cards (Bill, 2026-07-20)

MTGA sometimes shows **two zoomed cards side by side at once** — e.g. a
double-faced card's front and back, or a source card next to a token it
creates. The region detector must not assume "one card-shaped region per
event." Handling:

- The stable-region detector should find **all** card-shaped rectangles in
  the frame simultaneously, not just the first/largest one, and treat each
  independently through the matching + speech pipeline.
- When two regions appear together, speak both, left-to-right (matches
  natural reading order and is very likely how MTGA lays them out:
  front-then-back, or source-then-token).
- Double-faced cards: Scryfall already models these as `card_faces[0]`
  (front) and `card_faces[1]` (back) on a single `id` — if both faces are
  detected as separate on-screen regions, we may get two independent pHash
  matches to the *same* Scryfall card id (once per face image, since
  Scryfall also publishes per-face images for DFCs). That's fine and
  expected: dedupe by id if needed, or just read "front: X, back: Y" using
  `card_faces[0]`/`card_faces[1]` text directly instead of two separate
  lookups.
- Token cards: Scryfall has real entries for most official tokens (type
  line `Token`), so a source-card + its token side by side should resolve to
  two distinct, correct matches through the same pipeline — no special
  casing needed beyond "don't assume exactly one region."
- Open question to validate once we can watch real MTGA footage: are the two
  regions always the same size/shape, or does one sometimes render smaller
  (e.g. a token preview thumbnail vs. a full zoomed card)? If sizes differ
  a lot, the "portrait rectangle, ratio ≈0.71" detector needs a size *range*
  tolerance, not just an aspect-ratio check, and very small thumbnails might
  need to be excluded (or a separate smaller-region detector added) if pHash
  reliability drops at low resolution — untested.

### 1. Screen capture loop

- Periodic capture (~100-150ms interval) via `ScreenCaptureKit` (modern) or
  `CGWindowListCreateImage` (simpler, may need Screen Recording permission
  either way). Scope capture to the MTGA window only if possible, to cut cost
  and avoid false positives from other windows.

### 2. Stable-region detector

- Frame-diff consecutive captures. Look for a newly-appeared large rectangular
  region with card aspect ratio (~2.5:3.5 portrait, ratio ≈ 0.71, some
  tolerance).
- Require 2-3 consecutive frames with near-zero diff in that region before
  triggering — MTGA's zoom uses an easing animation, so we must wait for it to
  settle before we crop and hash, or we'll hash a half-scaled intermediate
  frame.
- Cooldown/dedup: don't re-trigger repeatedly on a card that stays zoomed;
  cancel/interrupt in-flight TTS if a new card appears before the old
  announcement finishes (fast-flick-through behavior).
- False-positive risks to tune against: mulligan screen, deck-builder preview
  panes, any other large portrait-ish popup. Likely solvable with position
  heuristics (zoomed card tends to appear centered) plus a confidence
  threshold from the matching stage (see below) — if hashing doesn't produce
  a confident match, say nothing rather than announcing garbage.

### 3. Perceptual hash matching (no OCR)

- **Offline, one-time index build:**
  1. Download Scryfall bulk data (`default_cards` or `unique_artwork` — see
     `https://scryfall.com/docs/api/bulk-data`), which includes image URIs and
     full card JSON (name, mana_cost, type_line, oracle_text, power/toughness,
     set, collector number).
  2. Fetch card images (full card frame, not just art_crop — the frame
     disambiguates alternate arts/foils/showcase treatments sharing a name).
  3. Compute a perceptual hash (pHash via DCT, or simpler aHash/dHash to start)
     for each image; store `hash -> scryfall_id` in a flat file or SQLite
     table. ~30-60 min one-time job, a few hundred MB of images (can discard
     after hashing).
- **Runtime lookup:** crop the stabilized card region, compute the same hash,
  nearest-neighbor search by Hamming distance against the index (trivial at
  ~30k entries — flat scan is sub-millisecond, no ANN index needed).
- Distance threshold gives a built-in confidence signal: below threshold =
  confident match, speak the card; above = stay silent or retry next frame.

### 4. Oracle text lookup + TTS

- On confident match, look up the card's full Scryfall JSON (already have it
  from the offline index or a live API call) and read a to-be-designed
  summary: name → mana cost → type line → oracle text → power/toughness if
  present. Speak via `AVSpeechSynthesizer`.
- Consider caching the last N spoken cards so repeat sightings of the same
  card in a game don't force a re-speak of the full text (maybe just the name
  on repeats, full text on first sighting — TBD, ask Bill for preference).

## Why this beats the two earlier ideas discussed this session

1. **vs. hover + OCR of small text region:** no mouse tracking required at
   all (the actual accessibility gap — finding a small board card with a
   cursor — disappears entirely), and no OCR fragility on tiny/stylized game
   text.
2. **vs. hover + title-OCR + fuzzy Scryfall name match:** matching the full
   card image is strictly more informative than matching just a garbled
   title string — disambiguates alternate arts/foils, and removes all OCR
   error modes, not just some of them.

## Future feature: keeping the hash index current with new card releases

The offline hash index (see hashindex/) is built from a point-in-time
Scryfall bulk-data snapshot. MTG gets new sets/cards roughly every few weeks,
plus Arena-exclusive rebalanced cards and Alchemy-only cards that sometimes
lag behind or diverge from paper Scryfall data. If cardsense ships and then
a new set drops, newly-played cards won't be in the index and will either
silently fail to match (large hash-distance, no confident result) or, worse,
false-match to a visually similar older card.

Not needed for the initial prototype, but worth solving before any real
ship date:

- **Detect staleness:** check Scryfall's bulk-data `updated_at` timestamp
  (returned by the `/bulk-data` manifest endpoint we already call) against
  our locally stored index build time on startup; warn/refresh if stale.
- **Incremental refresh:** rather than a full 30-60 min re-download+rehash
  on every start, only fetch/hash cards newer than our last build (Scryfall
  bulk data doesn't offer a delta feed directly, but we could diff card IDs
  against what's already in our sqlite index and only hash the new ones).
- **Where to learn about new releases early:** Scryfall usually has
  card data live before or shortly after a set's Arena release; also worth
  watching Wizards' official Arena patch notes / MTG Arena's own "new to
  Arena" set announcements for Arena-exclusive timing quirks (Alchemy
  rebalances, Arena-only cards, early-access events) that might not track
  paper Magic's spoiler season 1:1.
- **Graceful unknown-card handling in the meantime:** when a zoomed card
  doesn't confidently match anything in the index (large hash distance to
  every entry), say something like "unrecognized card" rather than staying
  silent or guessing — gives Bill a clear signal to manually check rather
  than being misled by silence.

## Open questions (ask Bill)

- Exact TTS phrasing/order for a card readout — full oracle text every time,
  or abbreviated on repeat sightings?
- Should activated/triggered abilities' reminder text be included or
  stripped? (Scryfall oracle_text includes reminder text in parens by
  default.)
- Any other large-vertical-rectangle screens in MTGA we should explicitly
  exclude (mulligan, deck builder, sideboard) — need a session of manual
  observation to build the exclude list before this can ship confidently.
- macOS Screen Recording permission UX — first-run flow.

## Status

Design only. No code written yet. Next step: validate the "stable card-shaped
region" detector against real MTGA screen captures, and build the offline
Scryfall hash-index script as a standalone, testable piece before touching
the capture loop.
