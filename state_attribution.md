# How Flick AI Determines License Plate States

> This document explains the complete pipeline for determining which US state (or Canadian province) issued a license plate. State attribution is one of the hardest problems in automated license plate recognition — this doc covers how we solve it, what the failure modes are, and what guardrails protect accuracy.

---

## Why State Attribution Is Hard

Every US state has its own plate designs, color schemes, and formats. Many look visually similar (Minnesota and Wisconsin standard plates are nearly identical at a distance). The ALPR engine must reason simultaneously about:

- The characters on the plate
- The visual design of the plate background
- The text printed on the plate header/footer ("MINNESOTA", "America's Dairyland", etc.)
- Whether those characters match that state's known format rules

A single wrong state assignment cascades into wrong registration lookups, wrong neighbor-state searches, and failed verification — ultimately losing a plate from the output entirely.

---

## The 10-Layer Pipeline

State is not resolved in one step. It flows through a series of passes, each correcting or refining the previous result.

```
Layer 1 ── PlateRecognizer ALPR          reads plate, guesses regional state
Layer 2 ── Gemini Flash Video Pass       reads plate + state from video context
Layer 3 ── Union Merge                   ALPR takes priority when both detect same plate
Layer 4 ── Gemini Flash State Verify     visual image check on the plate itself
Layer 5 ── Format Analyzer               checks plate character pattern (L/N) vs state formats
Layer 6 ── Early Format Bias Reeval      if format doesn't match state, ask Flash early
Layer 7 ── Registration Lookup           state-anchored PlateToVin lookup
Layer 8 ── Neighbor State Expansion      tries geo + format + venue + Canadian states
Layer 9 ── OCR Substitution + CrossState fixes character errors AND state in tandem
Layer 10 ── Final Output Gate            plates without registration AND wrong format → dropped
```

---

## Layer 1: PlateRecognizer ALPR — The Starting Prior

**What it does:** Sends video frames to PlateRecognizer's cloud API. Returns the plate characters + a `region` field with a guessed US state code (e.g., `us-mn`).

**What it gets right:** Excellent at reading plate characters quickly under good lighting.

**Limitation:** The state guess is a probabilistic classifier tuned to the `regions` hint we pass in. We pass `["us-mn", "us-wi", "us-ia", "us-nd"]` as the likely regional context. If the real state isn't in that list, the engine tends to fall back to the most-likely state from the hint set.

**Key field:** `region.score` — this reflects how certain PlateRecognizer is about the **state** specifically. It is stored separately as `state_confidence`.

> ⚠️ **Common mistake:** Previously, the code conflated plate read quality (`score`) with state certainty (`state_confidence`). These are now tracked independently.

---

## Layer 2: Gemini Flash Video Pass

**What it does:** Sends full video segments to Gemini Flash, which reads plates holistically from the video context and returns plate + state in a single response.

**Strength:** More contextual — can see multiple frames, vehicle approach/departure, and the plate from different angles.

**Limitation:** State is based on what's visible of the plate in the video. Out-of-state plates with similar visual designs to MN/WI are commonly misassigned here too.

---

## Layer 3: Union Merge Priority

When both ALPR and Gemini Flash detect the same plate, ALPR takes priority. ALPR is generally more accurate for character reading, but its state signal is weaker.

---

## Layer 4: Gemini Flash State Verification (Pass 2)

**What it does:** For plates where state confidence is below threshold, sends the best extracted frame image directly to Gemini Flash and asks: *"What state is this plate from?"*

**Threshold:** State verification fires if `state_confidence < 0.90`.

> ⚠️ **Previously:** This check was incorrectly skipped when the plate was read with high confidence. A plate read at 0.95 quality would have `state_confidence` set to 0.95 and skip flash state verify — even if PlateRecognizer had no real idea about the state. This has been fixed: state confidence now comes from PlateRecognizer's `region.score` field, not the plate quality score.

**What the prompt checks:**
1. The state name text printed on the plate header/footer
2. Known slogans: "America's Dairyland" (WI), "Land of Lincoln" (IL), "10,000 Lakes" (MN), etc.
3. Plate colors, gradients, sticker placement, graphics
4. Format cross-validation (WI = 3L+4D, MN = 3L+3D, IL = 2L+5D, etc.)

**Special logic for WI:** Wisconsin "Fleet" plates have no tab stickers and display a vertical "FP" on the far right. The prompt explicitly instructs Gemini to strip this suffix — it is not part of the plate number.

**Override rule:** If a flash state suggestion conflicts with an already-confirmed registration, the confirmed registration wins and the state is not changed.

---

## Layer 5: Format Analyzer

**What it does:** Converts a plate string into its abstract `L/N` format (L = letter, N = digit) and maps it against a database of known state formats.

**Examples:**

| Plate | Abstract Format | Probable States |
|---|---|---|
| `ARJ4356` | `LLLNNNN` | WI, TN, MI, NY, OH, PA, TX, VA, WA, GA, NC |
| `MTY440` | `LLLNNN` | MN, IA, ND, AK, HI, IN, LA, ME, ... |
| `DW12827` | `LLNNNNN` | IL, CT |
| `29AS33` | `NNNLLL` | (not matched — unusual SD format) |

**Important limitation:** Vanity/custom plates do not follow standard formats. If a plate is all letters (e.g., `SUMGA`) it will return no matches, which is expected — vanity plates bypass format checking and go directly to registration as the arbiter.

**Format table last updated:** 03312026 retrospective. Added TN (matches `LLLNNNN` like WI), CO/FL mixed patterns, and IL pure-numeric.

---

## Layer 6: Early Format Bias Reeval (Item F)

**What it does:** If the plate format clearly does not match the assigned state *before* the first registration lookup, Flick AI calls Gemini Flash with a targeted prompt:

> *"This plate reads `BRN5134`. That format (LLLNNNN) does not match Minnesota's standard format (LLLNNN). The plate format matches: TN, WI, MI, NY. Please look at the image and identify the correct state."*

**Why this matters:** Without this early check, the system would burn a PlateToVin API call on `BRN5134/MN` which is guaranteed to fail, then enter the long escalation chain. The early correction routes the lookup to the right state immediately.

**When it fires:** Only when `is_strict_format(plate, state) == False` AND format candidates exist AND a best frame is available.

---

## Layer 7: Registration Lookup

**What it does:** Calls PlateToVin with the plate + resolved state. Caches all results to avoid duplicate API calls.

**State default rule:** If state is still unknown at this point, the format analyzer picks the best guess (e.g., `WI` for a `LLLNNNN` plate) instead of blindly defaulting to `MN`. This change prevents the entire escalation chain from being anchored to the wrong state.

**Match logic:** Registration is compared to the observed Make/Model/Color. A registration is accepted as `Match=Y` only if the vehicle description overlaps with what was visually observed.

---

## Layer 8: Neighbor State Expansion

When a plate does not register in its assigned state, Flick AI expands the search to other states in a structured, prioritized order.

### Four Tiers

**Tier 1 — Geographic neighbors that match the plate format**
> e.g., for `MTY440` assigned to MN: IA is a geographic neighbor AND matches `LLLNNN` format. IA is tried first.

**Tier 2 — Remaining geographic neighbors**
> Other adjacent states in case OCR errors broke the format match.

**Tier 3 — Non-neighbor states matching the plate format** (capped at 5)
> e.g., for `BRM5134` (LLLNNNN) starting from MN: TN is not a geographic neighbor but matches the format. TN gets tried here.

**Tier 4 — Venue-frequency states**
> MSP airport hotel guests arrive from all 50 states, especially via direct Delta routes. States regularly found in historical data:
>
> `CO, TN, GA, TX, FL, CA, OH, IN, MO, PA, NE, AZ, NC, VA, MA, NY, MI, OR, WA, UT`
>
> These are tried after geographic and format tiers fail.

**Tier 5 (last resort) — Canadian provinces**
> `MB, ON, BC, AB, SK, QC` — tried last. Manitoba plates appear occasionally near the MSP border. PlateToVin handles these gracefully (returns not-found if unsupported).

### Geographic Neighbor Map

```
MN → WI, IA, ND, SD, IL
WI → MN, IL, IA
IA → MN, WI, IL, MO, SD
ND → MN, SD, MT
SD → MN, ND, IA, NE, WY
IL → IN, MO, WI, IA, KY
IN → IL, OH, MI, KY
OH → IN, MI, PA, WV, KY
MI → OH, IN, WI
MO → IA, IL, KS, NE, KY, TN, AR
NE → SD, IA, MO, KS, WY, CO
CO → NE, KS, WY, UT, NM, OK
TX → NM, OK, AR, LA
TN → KY, MO, AR, MS, AL, GA, NC, VA
```

---

## Layer 9: OCR Substitution with Cross-State Retry

**What it does:** Generates all Levenshtein-1 variants of a plate by substituting each character with its common OCR-confusion doubles, then tries each variant against the registration database.

**Cross-state retry (Item A):** After each variant fails in the primary state, it is also tried against the top-2 format-probable states. This catches cases where both the character *and* the state are wrong simultaneously.

**Example:** `MTY448` (MN) → substitution generates `MTY440` → tried as MN (fails) → tried as IA (hit! 2022 Ram 1500) ✅

### Most Common OCR Character Confusions

| Character | Top Confusions | Notes |
|---|---|---|
| `0` | **`8`**, D, O, Q | `0↔8` swap is #1 error — 3 missed plates in 03312026 |
| `8` | **`0`**, B, 3, N | Bidirectional with 0 |
| `Q` | **`0`**, O | EEGQ92 → EEG092 confirmed from 03312026 |
| `M` | **`N`**, W | BRM5134 → BRN5134 confirmed from 03312026 |
| `N` | M, W | Symmetric with M |
| `1` | L, 0, I, T, 7 | |
| `5` | S, 6 | |
| `G` | C, Z, 6, U, R | |
| `T` | I, Y, 7, 1 | |

---

## Layer 10: Final Output Gate

Every plate that reaches the CSV output must pass this final check:

1. **Length gate:** Plate must be ≥ 5 characters OR have a registration hit
2. **Format gate:** Plate must match the strict format for its assigned state OR have a registration hit

This is the primary false-positive defense. Plates that were allowed through the "Vanity/Custom" bypass in the ALPR gate (due to high confidence) will still be dropped here if no registration was found.

---

## State Verification Prompt Reference

The Gemini Flash state verification prompt (`03_state_verification.md`) contains:

- Full visual design descriptions for MN, WI, IA, ND, SD, IL, CA, FL, GA, TN, CO and others
- OCR character confusion cross-validation rules
- Sticker placement conventions per state
- Format cross-check logic ("if this plate is 7 chars LLLNNNN, check for WI not MN")
- Explicit instructions for Wisconsin fleet plates ("FP" suffix handling)
- Blackout plate disambiguation rules

---

## Debugging State Attribution

When a plate gets the wrong state, check these log lines in the pipeline output:

| Log prefix | What it means |
|---|---|
| `[State verify]` | Flash state check was triggered |
| `[State default]` | Format analyzer overrode the MN fallback |
| `[Early Format Bias]` | Format mismatch caught before lookup — Flash asked for correct state |
| `[State expansion]` | Neighbor expansion started — lists all states being tried |
| `[State expansion] Hit!` | Correct state found in the expansion |
| `[Canadian fallback]` | Canadian province tier being tried |
| `[OCR sub cross-state hit!]` | Character sub + wrong state both corrected in tandem |
| `[Format Bias]` | Format mismatch in escalation path |

---

## Known Limitations

| Limitation | Notes |
|---|---|
| **Canadian plates beyond MB** | PlateToVin doesn't cover Canadian plates. MB is tried but rarely hits. |
| **Diplomatic / government plates** | Not in PlateToVin. Will appear as `registration not found`. |
| **Temporary / dealer plates** | Pure numeric 6-char plates map to IL, DE, MA. Correct state is unreliable. |
| **Older format variants** | Some states have multiple active formats (IA: county-digit prefix). Only the primary format is in the table. |
| **Vanity plates** | Cannot be format-validated. Pass through if confidence ≥ 0.95 and registration is found. |
| **Manitoba → PlateToVin** | Canadian provinces may not resolve via PlateToVin. HFP692 (Manitoba) will log as `registration not found`. |
