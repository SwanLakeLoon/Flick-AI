---
name: Flick AI
description: Flick AI — Extract license plate numbers from images and videos using a multi-pass AI pipeline (PlateRecognizer, Gemini Flash, and Gemini Pro), reason about vehicle details, and cross-reference against online registration databases to detect mismatches.
---

# Flick AI

## Overview

This project extracts text (license plate numbers) from images and videos found within date-organized folders. Additional reasoning determines:

- **Location** of vehicle data capture
- **Make and model** of the vehicle
- **State** the license plate was issued in

Once extracted, this information is cross-referenced against vehicle registration databases to verify whether the registered vehicle matches the observed make and model, flagging any mismatches.

## Background & Context

- **Source media**: iPhone photos and videos (`.MOV`, `.HEIC`, `.JPG`, `.PNG`, etc.) captured in the field
- **Analysis method**: Built-in AI vision capabilities (no external OCR libraries required)
- **Output**: Two files per date folder — `results.csv` (for spreadsheet import) and `results.md` (for human-readable review)
- **Validation**: Manual review by the project owner

## Folder Structure

Tests are organized by date in `MMDDYYYY` format:

```
flick-ai/
├── SKILL.md              # This file — project instructions & context
├── 03082026/             # Images and video from March 8, 2026
│   ├── IMG_2276.MOV
│   ├── IMG_2277.MOV
│   ├── results.csv       # Extraction results (spreadsheet-ready)
│   └── results.md        # Extraction results (human-readable)
├── 03092026/             # Images and video from March 9, 2026
│   ├── results.csv
│   └── results.md
└── ...
```

Each date folder contains:
- **Input files**: Source images and videos (`.MOV`, `.HEIC`, `.JPG`, `.PNG`)
- **Output files**:
  - `results.csv` — CSV file for direct import/copy-paste into spreadsheets
  - `results.md` — Markdown table for quick human-readable review in the repo

## Tools & Dependencies

### Video/Image Analysis
Based on testing, direct video analysis by LLM models hits extreme token limits, and traditional OCR struggles with motion blur and distance. 

**The recommended brute-force pipeline:**
1. **Frame Extraction**: Extract frames from `.MOV` or `.mp4` video files using a tool like OpenCV or `av`.
2. **Sub-sampling**: Sample the frames (e.g. every 2nd or 3rd frame) to avoid hitting Free Tier rate limits.
3. **Resizing**: Resize the extracted frames (e.g. 50% scale) to save massive amounts of API tokens without losing legibility. 
4. **AI Vision Brute-Forcing**: Send every sampled, resized frame *directly* to the Gemini API (`gemini-2.5-flash` or `pro`). Prompt it to scour the entire image for any legible plates and return the Make, Model, Color, Plate, and State in JSON. This entirely bypasses the inaccuracy of local OCR bounding boxes.
5. **Rate-Limit Handling**: Implement `time.sleep()` delays between frames (e.g. 5 seconds) and catch 429 quota errors by pausing for longer durations.

### Vehicle Registration Lookup
- **[PlateToVIN API](https://platetovin.com)** — Primary lookup method
  - Endpoint: `https://platetovin.com/api/convert` (POST JSON)
  - Headers: `Authorization: V2YpGzegnHFDv2w`
  - Payload: `{"plate": "ABC1234", "state": "CA"}`
  - Note: This service costs $0.05 per lookup and must be pre-funded.

- **[Auto.dev API](https://auto.dev)** — Secondary lookup method
  - Endpoint: `https://database.auto.dev/graphql`
  - Requires a "Scale" or "Growth" tier subscription.

Fallback databases if Carsxe returns no data:
1. **[FindByPlate.com](https://findbyplate.com)** — Free license plate lookup
2. **[VinGurus](https://vingurus.com)** — Free plate-to-VIN lookup
3. **[LookupAPlate](https://lookupaplate.com)** — Free plate lookup with vehicle details



## Workflow

1. **Create/identify the date folder** for the current batch of media (format: `MMDDYYYY`)
2. **Place source files** (images, videos) into the date folder
3. **Analyze each file** using the Hybrid Pipeline:
   - Extract frames from video programmatically.
   - Sample and resize the frames to avoid token limits.
   - Send the frames sequentially to Gemini Vision API with rate-limit delays.
   - Instruct Gemini to find any plates and deduce the state, vehicle make/model, and color.
   - Determine the general location from video context (e.g. "Homewood Suites by Hilton Edina MN").
4. **Cross-reference** each plate against vehicle registration databases to find:
   - Registered vehicle make and model
   - Registration status
   - Any mismatch between observed and registered vehicle
5. **Generate output files** in the date folder:
   - `results.csv` — CSV with the columns below, for spreadsheet import
   - `results.md` — Markdown table with the same data, for in-repo review

   **Columns:**

   | File | Plate Number | Plate State | Observed Make/Model | Registration | VIN Associated to Plate (if available) | Title Issues Associated to VIN (if available) | Mismatch | Location |
   |------|-------------|-------------|--------------------|--------------|----------------------------------------|-----------------------------------------------|----------|----------|
   | IMG_2276.MOV | ABC1234 | TX | Toyota Camry | 2021 Toyota Camry | 4T1R11AK8RU123456 | Clean | Y | Any Location |
   | IMG_2277.MOV | XYZ5678 | CA | Honda Civic | 2018 Ford F-150 | 1FTFW1E84KFC55555 | Salvage | N | Any Location |
   | IMG_2278.MOV | LMN443 | MO | Chevy Silverado | registration not found | | | N/A | Any Location |

6. **Review**: The project owner will manually verify results for accuracy

## Evaluation Criteria

- **No ground truth data** — results are validated through manual review by the project owner
- **Key quality indicators**:
  - Plate numbers are correctly read (all characters accurate)
  - State identification is correct
  - Vehicle make/model observation is reasonable given the image
  - Registration lookup returns relevant results
  - Mismatches are clearly flagged

## Notes & Conventions

- **Folder naming**: `MMDDYYYY` format (e.g., `03082026` for March 8, 2026)
- **Output files**: Always named `results.csv` and `results.md` within each date folder
- **One table per folder**: Each output file contains a single table covering all media in that folder
- **Media formats**: `.MOV`, `.HEIC`, `.JPG`, `.PNG`, and other common image/video formats
- **Multiple plates per file**: If a single image or video contains multiple vehicles/plates, each gets its own row in the table
- **Unreadable plates**: If a plate cannot be read, note it as `UNREADABLE` in the Plate Number column with an explanation in Notes
- **Video files**: Extract frames as needed to identify plates; note the approximate timestamp if relevant
- **Retrospectives**: All retrospective and analysis documents MUST be saved to the `retrospectives/` directory (e.g., `retrospectives/03172026_babysteps_retrospective.md`). Never place retrospectives at the project root.
