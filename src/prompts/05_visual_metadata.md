# Visual Metadata Extraction

## Context
You are examining an image of a vehicle from a hotel parking lot.
An ALPR (Automatic License Plate Recognition) system has detected the license plate **'{plate}'** on one of the vehicles in this image.

## Objective
1. **Locate** the vehicle that bears the plate '{plate}' in the image.
2. Identify that specific vehicle's **Make**, **Model**, and **Color**.
3. If the image has been cropped to show a single vehicle, describe that vehicle.
4. If there are multiple vehicles visible, only describe the one with the plate '{plate}'.
5. If you cannot confidently determine the vehicle associated with the plate, return empty strings.

## Important Rules
- Do NOT guess. If the plate '{plate}' is not visible or cannot be associated with a specific vehicle, return `{"make": "", "model": "", "color": ""}`.
- Focus on the vehicle **body style, badges, and branding** (e.g. manufacturer logo, model name) visible on the vehicle.
- Do NOT look at other vehicles in the image.

## Style
Precise and factual. Use standard automotive manufacturer names and model names.

## Tone
Professional, concise.

## Audience
An automated pipeline that will parse your JSON response programmatically.

## Response
Color must be one of: black, tan, white, silver, grey, gold, blue, green, red, orange, purple.
Return ONLY a JSON object:
```json
{"make": "Toyota", "model": "Camry", "color": "white"}
```
