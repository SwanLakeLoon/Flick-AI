# Flick AI

**Flick AI** is a multi-pass AI pipeline that extracts license plate information from  videos, looks up vehicle registrations, and flags mismatches. It combines deterministic OCR from PlateRecognizer with visual reasoning from Google Gemini Flash to process batches of video files recorded at a known location, producing a clean, reviewable spreadsheet.

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [Setup & Configuration](#setup--configuration)
4. [Organizing Your Videos](#organizing-your-videos)
5. [Running the Pipeline](#running-the-pipeline)
6. [Understanding the Output](#understanding-the-output)
7. [Cost Expectations & Quotas](#cost-expectations--quotas)
8. [Troubleshooting](#troubleshooting)

---

## How It Works

Flick AI runs several sequential passes over your videos to extract license plates as accurately as possible while minimizing cost:

| Pass | Engine | Cost | What It Does |
|------|--------|------|--------------|
| Pass 0 | Gemini Flash | Fractions of a cent | Identifies the hotel/location name from video signage; date from folder name |
| Pass 1a | PlateRecognizer | Generous free quota | Primary OCR. Extracts high-density frames and runs them through deterministic ALPR |
| Pass 1b | Gemini Flash | Very cheap | Watches the full video end-to-end for visual context. Results are fuzzy-merged with ALPR, deduplicated, and passed through a hallucination filter |
| Pass 2 | Gemini Flash | Very cheap | Crops to the vehicle and confirms which US state issued the plate based on its design |
| Pass 3-4 | Gemini Flash + APIs | Very cheap | Substitutes misread OCR characters, dynamically biases searches based on plate format, expands searches into neighboring states, and brute-forces registration lookup via PlateToVin + NHTSA |
| Pass 5 | Gemini Pro | Very cheap | Escalated re-evaluation of non-matching/unregistered plates to rescue difficult edge cases |
| Pass 6 | defrostmn.net | **Free** | Queries each plate against the Defrost MN ICE database; writes Y / HS / N to the ICE column |

For a detailed narrative on each pass, see [aboutme.md](./aboutme.md).

---

## Prerequisites

Before running Flick AI, you will need:

- **Google Gemini API Key** — (low-cost, paid)
- **PlateRecognizer Token** — (Generous free tier)
- **PlateToVin API Keys** — (Optional but highly recommended for full accuracy, approx $0.05 per lookup, requires pre-funded account)
- **Python 3.11+**
- **ffmpeg** — Installed via Homebrew
- **UV or pip** for managing dependencies

Install ffmpeg and the Python packages:

```bash
brew install ffmpeg
uv pip install requests google-genai
```

---

## Setup & Configuration

Flick AI manages all required API keys automatically from a single, centralized `.env` file at the root of the repository.

### 1. Create your `.env` File
Create a `.env` file in the same folder as this README. Add the following contents, replacing the placeholder values with your actual keys.

```env
# PlateRecognizer token (Get at: https://platerecognizer.com)
PLATERECOGNIZER_TOKEN=your_platerecognizer_token

# Google Gemini API key (Get at: https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key

# PlateToVin API keys (Get at: https://www.platetovin.com)
PLATETOVIN_API_KEYS=key1,key2,key3
```

> **Note on PlateToVin:** You can supply a comma-separated list of keys to automatically rotate through them when searching out-of-state plates. PlateToVin returns 5 free lookups per account.

### 2. Secure Your Keys (Gitignore)
The `.env` file is excluded from Git by default (`*.env` is in the `.gitignore` file). **Never commit your `.env` file to version control**, as Gemini API keys are directly tied to your Google billing account. Anyone with it can run charges against you.

### 3. API Key Fallbacks
If you do not wish to use the `.env` file, the pipeline will fully respect environment variables exported in your current shell session (e.g. `export GEMINI_API_KEY=your_key`).

---

## Organizing Your Videos

Flick AI processes one **batch folder** at a time. Folders should contain only video files (`.MOV`, `.mp4`, `.avi`).

**Recommended folder naming:** Use `MMDDYYYY` format. The pipeline will automatically parse the date and include it in the output.

```
flick-ai/
├── 03082026/          ← Videos from March 8, 2026
│   ├── IMG_2276.MOV
│   ├── IMG_2277.MOV
│   └── IMG_2278.MOV
├── 03092026/
│   ├── batch_1/       ← Sub-batches are supported
│   │   ├── IMG_2300.MOV
│   │   └── IMG_2301.MOV
│   └── batch_2/
│       └── IMG_2302.MOV
```

> **Automatic Connections & Retries:** Long videos (>2 minutes) and connection timeouts are handled completely automatically. The tool will aggressively split and recursively retry videos in half-increments until the entire batch is processed securely by Gemini.

---

## Running the Pipeline

From the root of the repository, point the pipeline at your batch folder:

```bash
PYTHONPATH=src python src/pipeline/orchestrator.py 03082026/
```

For an entire sub-batch:
```bash
PYTHONPATH=src python src/pipeline/orchestrator.py 03092026/batch_1/
```

### Automation Defaults & Overrides

By default, Flick AI is fully automated on context generation:
1. **Scene Analysis (Location):** Passes the first few seconds of every video to Gemini Flash to automatically detect the business or hotel name from signs.
2. **Date Parsing:** Walks up the folder tree to find an 8-digit `MMDDYYYY` folder name and formats it as `MM/DD/YYYY`.

If you prefer to bypass these automated steps and **hardcode** the values for the entire batch (saving a tiny amount of time and avoiding mismatched hotel names), you can use the command-line overrides:

```bash
# Override the location explicitly
PYTHONPATH=src python src/pipeline/orchestrator.py 03082026/ --location "Bloomington Fwy (both locations)"

# Override the date explicitly (or use "" to leave it completely blank)
PYTHONPATH=src python src/pipeline/orchestrator.py 03082026/ --date "03/08/2026"
```

### What Happens While It Runs

The pipeline prints its progress to the terminal in real time. You'll see output like:

```
PASS 0 — Scene Analysis (Location & Date)
  → Location: Homewood Suites by Hilton Edina MN
  → Date:     03/08/2026

PASS 1b — Gemini Flash Full-Video Extraction
  Processing IMG_2276.MOV
  → 4 plates extracted by Gemini Flash.
  ...

PASS 2-4 — State verification, visual metadata, DB lookup...
  [Lookup] Attempting MN DVS for XYZ789...
  ...

PASS 5 — Gemini Pro Escalation
  Re-evaluating XYZ789...
  ...

PASS 6 — ICE Lookup (defrostmn.net)
  [ICE] ABC123: N
  [ICE] XYZ789: Y
  ...

✓ Done! 17 plates written to 03082026/results.csv
```

> **Reruns are safe and cheap.** The pipeline caches API results locally (`gemini_flash_cache.json`, `lookup_cache.json`) inside each batch folder. Re-running after a crash or interruption will skip already-processed frames and plates, saving both time and quota.

---

## Understanding the Output

Two output files are created inside your batch folder:

- **`results.csv`** — Import directly into Excel or Google Sheets (with detailed columns).
- **`results.md`** — A human-readable markdown table for quick review directly in a code editor.

### Output Columns

| Column | Description |
|--------|-------------|
| **Plate** | License plate characters (best available reading resolved from the API searches) |
| **State** | 2-letter US state that issued the plate |
| **Make** | Vehicle manufacturer (e.g., Toyota, Ford) |
| **Model** | Vehicle model (e.g., Camry, F-150) |
| **Color** | 2-letter color code (see color mapping table in documentation) |
| **ICE** | Defrost MN ICE status: `Y` = Confirmed ICE · `HS` = Suspicious · `N` = No match |
| **Match** | `Y` = registration matches observed vehicle · `N` = mismatch · *(blank)* = no registration found |
| **Registration** | Registered vehicle description from the DMV database |
| **VIN Associated to Plate** | VIN number if available (from fallback lookup) |
| **Title Issues/Brands** | Registration status, brands (salvage, etc.) if available |
| **Notes** | Source video filename where the plate was seen |
| **Location** | Auto-detected hotel/location name from the video signage |
| **Date** | Date parsed from the root folder name |

### The "Match" Column Explained

- **Y** — The registered vehicle's make/model matches what was observed on camera. This is a normal and confirmed result.
- **N** — The registered vehicle doesn't match what was observed. This is flagged as highly suspicious in the edge-cases file (e.g., the plate belongs to a Toyota but the camera saw a Ford).
- *(blank)* — No registration was successfully resolved, even after brute-force substitution attempts.

---

## Cost Expectations & Quotas

Most of the pipeline's cost is offset by using **Gemini Flash**. Registration lookups (MN DVS and the Defrost MN ICE check) are entirely free.

### Typical Run — 10 Videos (~2–5 min each)

| Component | Cost Profile | Notes |
|-----------|-------------|-------|
| Gemini Flash (Passes 0, 1b, 2) | **~$0.01–$0.10** | Charged per second of video. Incredibly cost effective. |
| PlateRecognizer (Pass 1a) | **Free Quota** | High-quality OCR, handled locally via token rotation if needed. |
| PlateToVin (Registration) | **~$0.05 / lookup** | Handled natively via round-robin key rotation. |

### Quota Safety

Using the pipeline extensively might result in occasional rate limits. The script handles rate limiting intelligently:
- Real connection failures trigger split-and-retry video halving routines.
- Throttled lookups write `throttled` descriptors into the database so they are never permanently skipped as "Not Found".

---

## Troubleshooting

**`ERROR: ffmpeg not found`**
→ Install ffmpeg: `brew install ffmpeg`

**Pipeline complains about missing API keys**
→ Verify your `.env` file is named exactly `.env` (no extension) and sits at the root of the project directory.

**Videos fail or timeout via Gemini**
→ This is expected over long Wi-Fi or unstable connections. The pipeline will automatically split the video and retry the processing in chunks. Leave the script running; it is handling it transparently.

**Plate characters seem wrong but registration Match is `Y`**
→ The pipeline deliberately runs OCR substitution against visual similarity lists (e.g. replacing '8' with 'B'). If a substitution returns a perfect hit on a make/model match, the characters in the output are quietly *corrected* to the DMV's reading.
