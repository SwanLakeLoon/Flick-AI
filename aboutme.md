# Flick AI — How It Works

Flick AI runs a series of sequential "Passes" over your security footage. The pipeline relies heavily on Gemini Flash for visual reasoning and PlateRecognizer for deterministic optical character recognition (OCR), combining their strengths for highly accurate results.

### 1. PASS 0 — Scene Analysis *(Location & Date)*
Before looking for plates, the pipeline gets context. It sends each video to Gemini Flash to identify the hotel or business name from signage visible in the footage. The date is automatically parsed from your folder name (e.g., `03082026`). Both pieces of context are stamped onto every row of the final output.

### 2. PASS 1a — PlateRecognizer ALPR Extraction *(Frames & OCR)*
The pipeline extracts 10 frames per second (10 FPS) from every video using `ffmpeg` locally. These high-density frames are securely streamed to the **PlateRecognizer** API. 
PlateRecognizer is incredibly good at reading the exact characters on a plate in motion but doesn't understand broader video context. This pass yields our initial pool of plate character readings.

### 3. PASS 1b — Gemini Flash Full-Video Extraction *(Visual Context)*
Parallel to the frame extraction, each full video is sent to **Gemini Flash**. Gemini watches the footage end-to-end and returns a list of plates it spotted, along with initial guesses for the vehicle's Make, Model, and Color. 
Since Gemini Flash is prone to "hallucinating" exact plate characters, the pipeline fuzzy-merges its output with the precise readings from PlateRecognizer to get the best of both worlds: accurate characters (Pass 1a) and rich visual context (Pass 1b). The merged result is deduplicated and filtered to drop obvious hallucinated false plates (e.g., `00000`, `TEST`).

### 4. PASS 2-4 — Plate Loop & The 7-Phase Escalation
The pipeline loops over every unique plate and performs a multi-phase escalation, using registration success as the ultimate **"Oracle"**. Once the DMV database returns a Registered Vehicle description (e.g. 2016 Ford Explorer) that visually matches the observed vehicle on camera, **the pipeline immediately "short-circuits"**. A successful `Y` match proves the OCR read was correct, completely stopping any further expensive Gemini or brute-force API calls for that plate.

#### The Escalation Steps:
1. **Visual Validation:** A cropped image of the vehicle is sent to Gemini Flash to verify the issuing US State based on the plate's physical design and finalize the vehicle constraints (Make, Model, Color).
   - *Fleet Plate Override:* If the pipeline detects a vertical "FP" prefix (IL) or suffix (WI) in the plate characters, it automatically crops it out and hard-biases the state to the correct region, completely skipping visual validation.
2. **Primary Registration Lookup (The Oracle):** The plate is queried against a local API. Out-of-state plates fall back to **PlateToVin**. If the return matches the visual constraints, **Short-Circuit**.
3. **Dynamic Format Biasing:** If no match is found, the script checks if the plate's character sequence (e.g. 3 letters, 4 numbers) mathematically violates the structure of the guessed state. If invalid, the pipeline identifies which states *do* allow that structure and forcefully biases the search towards them (capped at 20 lookups per plate and 100 queries globally per batch). If a format-biased candidate matches, **Short-Circuit**.
4. **Flash Confirm:** If a registration was found but the vehicle type didn't match (e.g. a Toyota registration for an observed Ford), Gemini Flash gets a second look at the cropped plate to correct any glaring OCR errors.
5. **OCR Substitution & Brute Force:** If still no match, the pipeline assumes common camera issues (e.g. misread `B` for `8`). A matrix of visual substitutions is generated, and the DMV databases are brute-forced in real-time until a valid registration hit is found. If it hits, **Short-Circuit**.
6. **Neighboring State Expansion:** If the guessed state yields no results, the pipeline searches the database across all adjacent states to the initial guess.
7. **Gemini Pro Escalation:** As a last resort, stubborn edge cases are fully escalated to **Gemini Pro**. It evaluates the crop from scratch and triggers one final set of brute-force OCR lookups.

### 7. PASS 6 — ICE Lookup
As the very last step, every plate is queried against the Defrost MN database (`defrostmn.net`). The result—`Y` (Confirmed ICE), `HS` (Highly suspected ICE), or `N` (no match)—populates the **ICE** column in the spreadsheet.

### 8. Write Outputs
All results are written to a timestamped `*_results.csv` (importable into Excel/Google Sheets), a `*_results.md` markdown table, an `*_edge_cases.txt` for flagged plates, and a `*_stats.json` with cost and run statistics.

---

> **Cost summary & Caching**: 
> The entire pipeline costs just fractions of a penny per video. **Gemini Flash** handles all the heavy lifting and reasoning incredibly cheaply. **PlateRecognizer** comes with generous quotas, and all DMV lookups (MN DVS and defrostmn.net) are free. **PlateToVin** adds a small optional cost (~$0.05 per unique out-of-state plate) to ensure good nationwide coverage.
> All API results are heavily cached in your local batch folder so that re-running the pipeline (or resuming from an error) skips already-processed steps and saves both time and quota.
