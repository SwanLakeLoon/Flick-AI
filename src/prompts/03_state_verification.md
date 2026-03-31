# State Verification

## Context
You are examining a single image of a vehicle license plate.
The plate number is '{plate}'.

Here is detailed guidance on US state plate designs:

{state_knowledge}

{numeric_hint}

## Objective
Examine the provided image to identify the issuing state or territory of the vehicle's license plate.

You MUST follow this investigation order:
1. **Read the state name text** — Explicitly locate and read the state name printed on the plate header (top) or footer (bottom). Most US plates print the state name in large text.
2. **Read any slogans or taglines** — Look for known slogans like "Land of Lincoln" (IL), "10,000 Lakes" (MN), "America's Dairyland" (WI), "dmv.ca.gov" (CA), etc.
3. **Examine visual design markers** — Use colors, gradients, graphics, icons, logos, fonts, and sticker placement as secondary confirmation.
4. **If the state name is obscured** — Use the secondary visual markers, fonts, sticker placement, or logos to make your best determination.

## Style
Investigatory and categorical. Break down your reasoning into specific visual evidence before reaching a final conclusion.

## Tone
Technical, objective, and cautious. If the image is too blurry for a 90% confidence reading, state your best guess along with the specific reasons for your uncertainty.

## Audience
A technical developer building a forensic vehicle logging system. Return ONLY the 2-letter state abbreviation.

## OCR Character Confusion Guide

When verifying the state, also sanity-check the plate characters against the **expected format for each state**. A wrong state guess and a misread character often go hand-in-hand.

| Confusion | Impact on state ID | Example from field |
|---|---|---|
| `M ↔ N` | `AMB` → `ANB`: MN reads as WI (3L+4D prefix `ANB` is common WI) | `AMB1116` misread as `ANB1116`, triggering wrong state |
| `1 ↔ T` | Digit becomes letter, changing format from `3L+3D` (MN) to `4L+2D` | `0BB1T` → `088TT` |
| `B ↔ 8` | Letter becomes digit, shifting format group | `0BB1T` misread, affecting letter/digit split |
| `5 ↔ S` | Leading digit becomes letter, changes format interpretation | `5A0618` → `SA0618` |
| `D ↔ 0` | Leading char ambiguity — `D` looks like `0` in low contrast | `D4624547` → `04624547` |
| `Y ↔ K` | Mid-plate swap, does not change format but changes likely state DB match | `EGY287` → `EGK287` |

**Cross-validation rule:** If the detected plate format (letter/digit pattern) does NOT match the detected state's standard format, **recheck both**:
- If the plate serial format contains 7 characters matching the pattern of 3 letters followed by 4 numbers (e.g., `ABC-1234` or `BBP-7711`), it is highly uncharacteristic of a standard Minnesota plate. When you see this 7-character pattern, explicitly direct your attention to the top 15% of the license plate and check if the word "WISCONSIN" or "America's Dairyland" is written there.
- If format fits MN (`ABC123`) but image says WI → re-examine for "MINNESOTA" text or blue-white-blue bands
- If plate has 4 letters at the start, it is likely a **vanity plate** and format-checking does not apply

**State format reference:**
| State | Standard passenger format | Notes |
|---|---|---|
| MN | `LLL NNN` (3 letters, 3 digits) | Blackout, standard, and collector variants exist |
| WI | `LLL NNNN` (3 letters, 4 digits) | Fleet plates have "FP" prefix — exclude from plate |
| IA | `LLL NNNN` or county-digit prefix | Sometimes 3L+3D for older plates |
| ND | `LLL NNN` or up to 6 alphanumeric | Very similar to MN format — always check header |
| SD | `LLL NNN` or county prefix | Mount Rushmore graphic |

## Reference Edge Cases & Logic

**Blackout Plates:** If the background is black/dark and text is white/light, you MUST read the top-center text to distinguish between MINNESOTA, IOWA, or WISCONSIN.

**Minnesota:** Look for "MINNESOTA" header text. Standard plates have blue-white-blue horizontal bands. Blackout plates have white text on black. Tab stickers appear on the rear plate only.

**Wisconsin:** Identify the "WISCONSIN" header text. Key distinguishing features:
- **Standard plates** prominently display the slogan **"America's Dairyland"** — always look for this text. If you see "America's Dairyland", the plate is WI, not MN.
- **Fleet plates** have **NO validation stickers** (month/year) in the corners and display vertically aligned letters **"FP"** on the far right side of the plate (at the end of the plate numbers). The "FP" is a fleet marker and should **NOT** be included in the plate characters. Be highly alert to this: models frequently hallucinate this vertically stacked "FP" as a trailing "F" or "AF" (e.g., reading "35577A" as "35577AF"). If you see this, strip it and confirm as WI.
- Common WI passenger plate prefixes include letter combinations like `AFB`, `AGN`, `AKU`, `ANB`, `ASB`, `AZL`, `BCB` (letter-heavy starts are common in WI but rare in MN standard plates).
- WI plates starting with 3 letters followed by 4 digits (e.g., `AFB1747`) look similar to MN plates — always check for "America's Dairyland" or "WISCONSIN" header to differentiate.

**Illinois:** Look for the "Land of Lincoln" slogan and the Abraham Lincoln graphic silhouette on the left side of the plate.

**California:** Confirm the red script "California" font and the "dmv.ca.gov" footer. Check for month sticker (left) and year sticker (right).

**Georgia:** Look for the "America 250" stars (2026 standard issue) or the classic peach icon in the center of the plate.

**Iowa:** Look for "IOWA" header. County name may appear at the bottom. Standard plates have a farm/barn scene or gradient background.

**South Dakota:** Look for Mount Rushmore graphic. "SOUTH DAKOTA" header text. "Great Faces. Great Places." slogan.

## Visual Evidence Checklist
Before answering, confirm you have examined:
- **Header/Footer Text:** What state name or slogan is printed on the plate?
- **Colors/Gradients:** (e.g., "Solid black background, white embossed text" or "blue-white-blue bands")
- **Graphics/Icons:** (e.g., "Lincoln silhouette," "Peach icon," "Mount Rushmore," "Red stars")
- **Sticker Presence/Location:** (e.g., "No stickers found (Fleet)," "Year sticker top-right")
- **Font Style:** (e.g., "Red script font = California," "Block capitals = standard state")

## Response
Return ONLY the 2-letter US state abbreviation. Nothing else.
