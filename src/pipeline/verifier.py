"""
Flick AI — Verifier Handlers (Pass 2 & 3)
===========================================
State Verification, Visual Metadata extraction, Pro Escalations, and Flash Rescores.

All per-frame image calls use inline base64 data (Part.from_bytes) instead of
the Files API resumable upload protocol, which is unreliable on some networks.
"""

import json
import re
import base64
import io
import os

from google.genai import types

from .config import client
from .prompts import load_prompt, STATE_KNOWLEDGE
from .merger import levenshtein_distance

# Try to import PIL for vehicle-region cropping; gracefully degrade if absent.
try:
    from PIL import Image as PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def _load_image_part(frame_path: str) -> types.Part:
    """Load a JPEG frame as an inline base64 Part (no file upload required)."""
    with open(frame_path, "rb") as f:
        data = f.read()
    return types.Part.from_bytes(data=data, mime_type="image/jpeg")


def _crop_to_vehicle_region(frame_path: str, vehicle_box: dict, padding_pct: float = 0.15) -> str | None:
    """
    Crop the frame to the vehicle bounding box (with padding) and save to a temp file.
    Returns the path to the cropped image, or None if cropping fails.
    vehicle_box format: {"xmin": int, "ymin": int, "xmax": int, "ymax": int}
    """
    if not _HAS_PIL or not vehicle_box:
        return None
    try:
        img = PILImage.open(frame_path)
        w, h = img.size
        xmin = vehicle_box.get("xmin", 0)
        ymin = vehicle_box.get("ymin", 0)
        xmax = vehicle_box.get("xmax", w)
        ymax = vehicle_box.get("ymax", h)
        # Add padding around the vehicle box
        pad_x = int((xmax - xmin) * padding_pct)
        pad_y = int((ymax - ymin) * padding_pct)
        crop_box = (
            max(0, xmin - pad_x),
            max(0, ymin - pad_y),
            min(w, xmax + pad_x),
            min(h, ymax + pad_y),
        )
        cropped = img.crop(crop_box)
        # Save to a temp path next to the original
        base, ext = os.path.splitext(frame_path)
        crop_path = f"{base}_vcrop{ext}"
        cropped.save(crop_path, "JPEG", quality=90)
        return crop_path
    except Exception as e:
        print(f"  [Crop warning] Could not crop vehicle region: {e}")
        return None


def verify_state_via_gemini(frame_path: str, plate: str) -> str:
    """
    Pass 2: Ask Gemini Flash what state this plate belongs to.
    Uses inline image data to avoid the Files API upload protocol.
    """
    numeric_hint = (
        "HINT: This plate contains only digits and is 6 characters long. "
        "This pattern is common in Illinois (e.g. IL standard passenger plates) "
        "or may be a temporary dealer/transport plate."
        if plate.isdigit() and len(plate) == 6 else ""
    )
    prompt = load_prompt("03_state_verification.md",
                          state_knowledge=STATE_KNOWLEDGE,
                          plate=plate,
                          numeric_hint=numeric_hint)
    try:
        image_part = _load_image_part(frame_path)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(temperature=0.0)
        )
        result = (response.text or "").strip().upper()
        if re.match(r'^[A-Z]{2}$', result):
            return result
    except Exception as e:
        print(f"  [State verify error] {e}")
    return ""


def extract_visual_metadata(frame_path: str, plate: str, vehicle_box: dict = None) -> dict:
    """
    Pass 3: Send a frame to Gemini Flash and extract Make, Model, Color.
    Uses inline image data to avoid the Files API upload protocol.
    Always sends the full frame so Gemini can see the entire vehicle.
    """
    prompt = load_prompt("05_visual_metadata.md", plate=plate)
    try:
        image_part = _load_image_part(frame_path)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        if not response.text:
            return {}
        return json.loads(response.text)
    except Exception as e:
        print(f"  [Visual extract error] {e}")
        return {}


def escalate_to_gemini_pro(frame_path: str, plate: str, current_state: str) -> tuple[str, str]:
    """
    Pass 5: Gemini Pro escalation for unregistered plates.
    Uses inline image data to avoid the Files API upload protocol.
    """
    prompt = load_prompt("04_pro_reeval.md",
                          state_knowledge=STATE_KNOWLEDGE,
                          plate=plate,
                          current_state=current_state)
    try:
        image_part = _load_image_part(frame_path)
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text.replace("```json", "", 1).replace("```", "", 1).strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text.replace("```", "", 1).replace("```", "", 1).strip()

        data = json.loads(raw_text)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]

        if not isinstance(data, dict):
            return "", ""

        suggested_state = (data.get('state') or '').strip().upper()
        suggested_plate = (data.get('plate') or '').upper().replace(" ", "").replace("-", "")

        if re.match(r'^[A-Z]{2}$', suggested_state) and len(suggested_plate) >= 4:
            return suggested_state, suggested_plate
    except Exception as e:
        print(f"  [Pro escalation error] {e}")
    return "", ""


def gemini_flash_confirm_plate(frame_path: str, plate: str) -> str:
    """
    Soft-escalation: Ask Gemini Flash to re-read plate characters only.
    Uses inline image data to avoid the Files API upload protocol.
    """
    prompt = load_prompt("06_plate_confirm.md", plate=plate)
    try:
        image_part = _load_image_part(frame_path)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        if not response.text:
            return plate

        data = json.loads(response.text)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        if not isinstance(data, dict):
            return plate

        confirmed = (data.get('plate') or '').upper().replace(" ", "").replace("-", "")
        changed = data.get('changed', False)

        if not confirmed or len(confirmed) < 4:
            return plate
        if not changed:
            return plate

        # Levenshtein guard
        if levenshtein_distance(plate, confirmed) > 3:
            print(f"    → Flash confirm suggested '{confirmed}', but distance from '{plate}' > 3. Rejecting.")
            return plate

        return confirmed
    except Exception as e:
        print(f"  [Flash confirm error] {e}")
        return plate


def gemini_flash_reeval(frame_path: str, plate: str, current_state: str, plate_specific_hints: str = "") -> tuple[str, str]:
    """
    Flash pre-read: Ask Flash to re-evaluate both plate characters and state.
    Uses inline image data to avoid the Files API upload protocol.
    """
    prompt = load_prompt("07_flash_reeval.md",
                          state_knowledge=STATE_KNOWLEDGE,
                          plate=plate,
                          current_state=current_state,
                          plate_specific_hints=plate_specific_hints)
    try:
        image_part = _load_image_part(frame_path)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        if not response.text:
            return "", ""

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text.replace("```json", "", 1).replace("```", "", 1).strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text.replace("```", "", 1).replace("```", "", 1).strip()

        data = json.loads(raw_text)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        if not isinstance(data, dict):
            return "", ""

        suggested_state = (data.get('state') or '').strip().upper()
        suggested_plate = (data.get('plate') or '').upper().replace(" ", "").replace("-", "")

        if not re.match(r'^[A-Z]{2}$', suggested_state) or len(suggested_plate) < 4:
            return "", ""

        if levenshtein_distance(plate, suggested_plate) > 4:
            print(f"    → Flash reeval suggested '{suggested_plate}' ({suggested_state}), but distance from '{plate}' > 4. Rejecting.")
            return "", ""

        return suggested_state, suggested_plate
    except Exception as e:
        print(f"  [Flash reeval error] {e}")
        return "", ""


def format_bias_reeval(
    frame_path: str,
    plate: str,
    current_state: str,
    candidate_states: list,
) -> tuple:
    """
    Format-biased state re-evaluation: Ask Gemini Flash to reconsider the state
    given that the plate format is structurally invalid for the originally guessed
    state, but matches the standard format for certain candidate states.

    Uses inline image data to avoid the Files API upload protocol.
    Returns (suggested_state, suggested_plate) or ("", "") on failure.
    """
    candidate_states_list = ", ".join(candidate_states)
    prompt = load_prompt(
        "08_format_bias_reeval.md",
        state_knowledge=STATE_KNOWLEDGE,
        plate=plate,
        current_state=current_state,
        candidate_states_list=candidate_states_list,
    )
    try:
        image_part = _load_image_part(frame_path)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        if not response.text:
            return "", ""

        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text.replace("```json", "", 1).replace("```", "", 1).strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text.replace("```", "", 1).replace("```", "", 1).strip()

        data = json.loads(raw_text)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        if not isinstance(data, dict):
            return "", ""

        suggested_state = (data.get('state') or '').strip().upper()
        suggested_plate = (data.get('plate') or '').upper().replace(" ", "").replace("-", "")

        if not re.match(r'^[A-Z]{2}$', suggested_state) or len(suggested_plate) < 4:
            return "", ""

        # Levenshtein guard — reject wild hallucinations
        if levenshtein_distance(plate, suggested_plate) > 4:
            print(f"    → Format bias reeval suggested '{suggested_plate}' ({suggested_state}), but distance from '{plate}' > 4. Rejecting.")
            return "", ""

        return suggested_state, suggested_plate
    except Exception as e:
        print(f"  [Format bias reeval error] {e}")
        return "", ""
