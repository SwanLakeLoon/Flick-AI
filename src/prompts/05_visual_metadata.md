# Visual Metadata Extraction

## Context
You are examining an image of a vehicle from a hotel parking lot surveillance camera.
The vehicle's license plate reads '{plate}'.

## Objective
Identify the vehicle's **Make**, **Model**, and **Color**.

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
