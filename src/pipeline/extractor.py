"""
Flick AI — Extraction Handlers (Pass 1)
=========================================
PlateRecognizer ALPR pass and Gemini Flash Full-Video pass.
"""

import os
import re
import json
import time
import glob
import subprocess
import requests
from pathlib import Path

from google.genai import types

from .config import (
    EPHEMERAL_DIR, client, _load_config_key,
    MN_LOGO_DIGIT_RE, normalize_color
)
from .prompts import load_prompt, STATE_KNOWLEDGE
from plate_formats import is_strict_format


def is_valid_plate(plate: str) -> bool:
    """Return False for fragments too short to be a real plate (noise filter)."""
    return len(plate) >= 4


def strip_phantom_prefixes(plate: str) -> tuple:
    """Remove known OCR hallucinations like the vertical 'FP' on fleet plates.
    
    Illinois: vertical 'FP' appears BEFORE a 4-7 digit number (prefix).
    Wisconsin: vertical 'FP' appears AFTER a standard plate (suffix).
    
    Returns (cleaned_plate, strip_type) where strip_type is:
      'IL_FP_PREFIX'  — Illinois fleet plate prefix was stripped
      'WI_FP_SUFFIX'  — Wisconsin fleet plate suffix was stripped
      None            — nothing was stripped
    """
    # IL: FP prefix followed by 4-7 digits → strip prefix
    match = re.match(r'^FP(\d{4,7})$', plate)
    if match:
        return match.group(1), 'IL_FP_PREFIX'
    # WI: standard plate characters followed by FP suffix → strip suffix
    match = re.match(r'^([A-Z]{2,4}\d{3,4})FP$', plate)
    if match:
        return match.group(1), 'WI_FP_SUFFIX'
    return plate, None


def load_alpr_tokens() -> list[str]:
    """Load ALPR tokens from .env (supports PLATERECOGNIZER_TOKENS or singular PLATERECOGNIZER_TOKEN)."""
    tokens_str = os.environ.get("PLATERECOGNIZER_TOKENS") or _load_config_key("PLATERECOGNIZER_TOKENS")
    if tokens_str:
        return [t.strip() for t in tokens_str.split(',') if t.strip()]
    
    token_str = os.environ.get("PLATERECOGNIZER_TOKEN") or _load_config_key("PLATERECOGNIZER_TOKEN")
    if token_str:
        return [token_str.strip()]
        
    return []


def run_alpr_pass(videos: list[str]) -> tuple[dict, list]:
    """Pass 1a: Extract 10 FPS frames and run PlateRecognizer ALPR.
    Returns (alpr_plates_dict, failure_messages_list)."""
    tokens = load_alpr_tokens()
    failure_msgs = []
    if not tokens:
        failure_msgs.append("No ALPR tokens found. Skipping Pass 1a.")
        print("  [Warning] " + failure_msgs[0])
        return {}, failure_msgs

    unique_plates = {}
    alpr_cache_file = os.path.join(EPHEMERAL_DIR, "alpr_cache.json")
    if os.path.exists(alpr_cache_file):
        with open(alpr_cache_file) as f:
            alpr_cache = json.load(f)
    else:
        alpr_cache = {}

    token_idx = 0

    for vid_path in videos:
        vid_name = os.path.basename(vid_path)
        stem = Path(vid_name).stem
        frames_dir = os.path.join(EPHEMERAL_DIR, "_alpr_frames", stem)
        os.makedirs(frames_dir, exist_ok=True)
        
        # Extract frames at 10fps if needed
        frame_files = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
        if not frame_files:
            print(f"\n[ALPR] Extracting frames for {vid_name} at 10 FPS (2K)...")
            cmd = [
                "ffmpeg", "-i", vid_path,
                "-r", "10",
                "-vf", "scale=2048:-2",
                "-q:v", "1",
                os.path.join(frames_dir, "frame_%04d.jpg")
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            frame_files = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))

        print(f"\n[ALPR] Processing {len(frame_files)} frames for {vid_name}...")
        
        for fpath in frame_files:
            fname = os.path.basename(fpath)
            if fname in alpr_cache:
                data = alpr_cache[fname]
            else:
                try:
                    with open(fpath, 'rb') as fp:
                        resp = requests.post(
                            "https://api.platerecognizer.com/v1/plate-reader/",
                            data={
                                "regions": "us",
                                "mmc": "true",
                                "config": json.dumps({
                                    "detection_rule": "strict",
                                    "zoom_in_vehicles": 4
                                })
                            },
                            files={"upload": fp},
                            headers={"Authorization": f"Token {tokens[token_idx]}"},
                            timeout=15
                        )
                    resp.raise_for_status()
                    res_json = resp.json()
                    data = {"results": res_json.get("results", [])}
                    alpr_cache[fname] = data
                    with open(alpr_cache_file, "w") as f:
                        json.dump(alpr_cache, f, indent=2)
                    time.sleep(0.2)
                except Exception as e:
                    err_text = str(e)
                    err_response = getattr(e, 'response', None)
                    if err_response is not None and hasattr(err_response, 'text'):
                        err_text = getattr(err_response, 'text')
                    
                    if "401" in err_text or "429" in err_text or "403" in err_text or "quota" in err_text.lower():
                        msg = f"Token {tokens[token_idx][:6]}... failed: {err_text}"
                        failure_msgs.append(msg)
                        print(f"  [ALPR Error] {msg}")
                        token_idx += 1
                        if token_idx < len(tokens):
                            print(f"  → Rotating to next token ({tokens[token_idx][:6]}...).")
                            continue
                        else:
                            msg2 = "All PlateRecognizer tokens exhausted. Aborting Pass 1a."
                            failure_msgs.append(msg2)
                            print(f"  [ALPR Error] {msg2}")
                            return unique_plates, failure_msgs
                    else:
                        print(f"  [ALPR Error] Frame {fname}: {err_text}")
                        continue
            
            for res in data.get("results", []):
                plate = res.get("plate", "").upper()
                score = res.get("score", 0.0)
                if not plate or len(plate) < 4: continue
                
                if score < 0.80:
                    print(f"  [Confidence filter] Skipping very low-confidence plate: '{plate}' ({score:.2f})")
                    continue
                
                plate = strip_phantom_prefixes(plate)
                fp_strip_type = plate[1]
                plate = plate[0]
                
                match = MN_LOGO_DIGIT_RE.match(plate)
                if match:
                    plate = match.group(1) + match.group(2)
                
                region_data = res.get("region", {})
                state = region_data.get("code", "UNKNOWN").upper()
                if state.startswith("US-"): state = state[3:]
                elif state == "US": state = "UNKNOWN"
                
                # If a WI suffix FP was stripped, force state to WI
                if fp_strip_type == 'WI_FP_SUFFIX':
                    state = 'WI'
                    print(f"  [FP Suffix] Detected WI fleet plate suffix → forcing state=WI for {plate}")
                    
                if score < 0.92 and not is_strict_format(plate, state):
                    print(f"  [Regex Gate] Discarding '{plate}' ({state}) — score {score:.2f} but fails strict format")
                    continue
                
                if plate not in unique_plates or score > unique_plates[plate]["score"]:
                    make, model, color = "", "", ""
                    if res.get("model_make") and len(res["model_make"]) > 0:
                        mm = res["model_make"][0]
                        if mm.get("score", 0) > 0.5:
                            make = mm.get("make", "")
                            model = mm.get("model", "")
                    if res.get("color") and len(res["color"]) > 0:
                        cc = res["color"][0]
                        if cc.get("score", 0) > 0.5:
                            color = cc.get("color", "")

                    unique_plates[plate] = {
                        "plate": plate,
                        "state": state if state != "UNKNOWN" else "",
                        "score": score,
                        "plate_confidence": score,
                        "state_confidence": score if state != "UNKNOWN" else 0.0,
                        "timestamp_sec": float(fname.split("_")[1].replace(".jpg", "")) / 10.0,
                        "best_frame": fpath,
                        "video": vid_name,
                        "video_path": vid_path,
                        "source": "ALPR",
                        "make": make, "model": model, "color": color
                    }
    
    print(f"\n[ALPR] → {len(unique_plates)} unique plates extracted.")
    return unique_plates, failure_msgs


def wait_for_gemini_file(gemini_file):
    """Poll until the Gemini-uploaded file is ACTIVE."""
    print(f"  Waiting for {gemini_file.name} to be ready...", end="", flush=True)
    info = client.files.get(name=gemini_file.name)
    while info.state.name == 'PROCESSING':
        print(".", end="", flush=True)
        time.sleep(8)
        info = client.files.get(name=gemini_file.name)
    print(f" {info.state.name}")
    if info.state.name == 'FAILED':
        raise RuntimeError(f"Gemini file processing failed: {gemini_file.name}")


def gemini_flash_video_pass(videos: list[str]) -> dict:
    """
    Pass 1b: Send each full video to Gemini 2.5 Flash for plate extraction.
    Returns unique_plates dict in the same format as run_alpr_pass().
    """
    prompt = load_prompt("02_plate_extraction.md", state_knowledge=STATE_KNOWLEDGE)

    unique_plates = {}
    gemini_cache_file = os.path.join(EPHEMERAL_DIR, "gemini_flash_cache.json")

    if os.path.exists(gemini_cache_file):
        with open(gemini_cache_file) as f:
            gemini_cache = json.load(f)
    else:
        gemini_cache = {}

    stale_keys = [
        vid for vid, entries in gemini_cache.items()
        if isinstance(entries, list) and entries and 'plate_confidence' not in entries[0]
    ]
    if stale_keys:
        print(f"  [Cache] Evicting {len(stale_keys)} stale entries missing confidence scores: {stale_keys}")
        for k in stale_keys:
            del gemini_cache[k]

    def _gemini_extract(vid_path: str, cache_key: str, depth: int = 0) -> list:
        if cache_key in gemini_cache:
            print(f"  → Found in Gemini cache ({cache_key}), skipping upload.")
            return gemini_cache[cache_key]

        try:
            import concurrent.futures as _cf
            gemini_file = client.files.upload(file=vid_path)
            wait_for_gemini_file(gemini_file)

            def _call_gemini():
                return client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[gemini_file, prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        response_mime_type="application/json"
                    )
                )

            _pool = _cf.ThreadPoolExecutor(max_workers=1)
            _future = _pool.submit(_call_gemini)
            try:
                response = _future.result(timeout=300)
                _pool.shutdown(wait=False)
            except _cf.TimeoutError:
                print(f"  [Gemini] generate_content timed out after 300s for '{cache_key}'. Treating as connection error.")
                _pool.shutdown(wait=False)
                raise RuntimeError("stream timeout after 300s")

            client.files.delete(name=gemini_file.name)

            if not response.text:
                print(f"  [Warning] Empty Gemini response for '{cache_key}'")
                return []

            plates_data = json.loads(response.text)
            gemini_cache[cache_key] = plates_data
            with open(gemini_cache_file, "w") as f:
                json.dump(gemini_cache, f, indent=2)
            return plates_data

        except Exception as e:
            error_str = str(e).lower()
            is_connection_error = any(kw in error_str for kw in [
                "server disconnected", "connection", "timeout", "stream", "eof", "reset"
            ])

            if is_connection_error and depth < 0:  # Disabled split-retries to prevent 35+ minute cascades
                import tempfile, shutil
                print(f"  [Gemini] Connection error on '{cache_key}': {e}")
                print(f"  [Gemini] Splitting video and retrying each half (depth={depth + 1})...")
                try:
                    probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1", vid_path],
                        capture_output=True, text=True, timeout=15
                    )
                    duration = float(probe.stdout.strip())
                    mid = duration / 2.0

                    tmp_dir = tempfile.mkdtemp(prefix="gemini_split_")
                    base = os.path.splitext(os.path.basename(vid_path))[0]
                    part_a = os.path.join(tmp_dir, f"{base}_pA.mp4")
                    part_b = os.path.join(tmp_dir, f"{base}_pB.mp4")

                    subprocess.run(
                        ["ffmpeg", "-y", "-i", vid_path, "-t", str(mid), "-c", "copy", part_a],
                        capture_output=True, check=True, timeout=60
                    )
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", vid_path, "-ss", str(mid), "-c", "copy", part_b],
                        capture_output=True, check=True, timeout=60
                    )

                    results_a = _gemini_extract(part_a, f"{cache_key}__pA", depth + 1)
                    results_b = _gemini_extract(part_b, f"{cache_key}__pB", depth + 1)
                    merged = results_a + results_b
                    print(f"  [Gemini] Split-retry: {len(results_a)} + {len(results_b)} = {len(merged)} plates for '{cache_key}'.")

                    gemini_cache[cache_key] = merged
                    with open(gemini_cache_file, "w") as f:
                        json.dump(gemini_cache, f, indent=2)

                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    return merged

                except Exception as split_err:
                    print(f"  [Gemini] Split-retry failed for '{cache_key}': {split_err}")
                    return []
            else:
                print(f"  [Gemini Flash error] {cache_key}: {e}")
                return []

    for vid_path in videos:
        vid_name = os.path.basename(vid_path)
        print(f"\n[Gemini Flash] Processing {vid_name}")

        plates_data = _gemini_extract(vid_path, vid_name)
        if not plates_data:
            continue
        
        # Guard against Gemini hallucinating an object instead of a list
        if not isinstance(plates_data, list):
            if isinstance(plates_data, dict):
                for k, v in plates_data.items():
                    if isinstance(v, list):
                        plates_data = v
                        break
            if not isinstance(plates_data, list):
                print(f"  [Warning] Gemini Flash returned non-list data: {type(plates_data)}")
                continue

        print(f"  → {len(plates_data)} plates extracted by Gemini Flash.")

        for item in plates_data:
            plate = (item.get('plate') or '').upper().replace(" ", "").replace("-", "")
            plate = strip_phantom_prefixes(plate)
            fp_strip_type = plate[1]
            plate = plate[0]
            
            state = (item.get('state') or 'UNKNOWN').upper()
            
            # If a WI suffix FP was stripped, force state to WI
            if fp_strip_type == 'WI_FP_SUFFIX':
                state = 'WI'
                print(f"  [FP Suffix] Detected WI fleet plate suffix → forcing state=WI for {plate}")
            
            if not plate:
                continue
            
            if not is_valid_plate(plate):
                print(f"  [Noise filter] Discarding short plate: '{plate}'")
                continue
                
            plate_confidence = float(item.get('plate_confidence') or 0.6)
            state_confidence = float(item.get('state_confidence') or 0.6)
            timestamp_sec = float(item.get('timestamp_sec') or 0.0)

            if plate_confidence < 0.80:
                print(f"  [Confidence filter] Discarding very low-confidence plate: '{plate}' ({plate_confidence:.2f})")
                continue
                
            if plate_confidence < 0.92 and not is_strict_format(plate, state):
                print(f"  [Regex Gate] Discarding '{plate}' ({state}) — confidence {plate_confidence:.2f} but fails strict format")
                continue

            if plate not in unique_plates:
                make = item.get('make') or ''
                model = item.get('model') or ''
                raw_color = item.get('color') or ''
                unique_plates[plate] = {
                    "plate": plate,
                    "state": state,
                    "score": plate_confidence,
                    "plate_confidence": plate_confidence,
                    "state_confidence": state_confidence,
                    "timestamp_sec": timestamp_sec,
                    "best_frame": None,
                    "video": vid_name,
                    "video_path": vid_path,
                    "source": "GEMINI_FLASH",
                    "make": make,
                    "model": model,
                    "color": normalize_color(raw_color),
                }

    print(f"\n[Gemini Flash] → {len(unique_plates)} unique plates from video pass.")
    return unique_plates


# ── Scene Analysis (Pass 0) ───────────────────────────────────────────────────
def detect_location_from_video(video_path: str) -> str:
    """Pass 0: Ask Gemini Flash to infer the hotel name."""
    vid_name = os.path.basename(video_path)
    cache_key = f"scene_{vid_name}"
    gemini_cache_file = os.path.join(EPHEMERAL_DIR, "gemini_flash_cache.json")

    if os.path.exists(gemini_cache_file):
        with open(gemini_cache_file) as f:
            gemini_cache = json.load(f)
    else:
        gemini_cache = {}

    if cache_key in gemini_cache:
        cached = gemini_cache[cache_key]
        location = cached.get("location", "")
        print(f"  [Scene] Cache hit — location: '{location}'")
        return location

    prompt = load_prompt("01_scene_location.md")
    try:
        print(f"  [Scene] Uploading {vid_name} to Gemini Flash for hotel identification...")
        gemini_file = client.files.upload(file=video_path)
        wait_for_gemini_file(gemini_file)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[gemini_file, prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        client.files.delete(name=gemini_file.name)
        if response.text:
            data = json.loads(response.text)
            location = data.get("location", "").strip()
            print(f"  [Scene] Detected location: '{location}'")
            gemini_cache[cache_key] = {"location": location}
            with open(gemini_cache_file, "w") as f:
                json.dump(gemini_cache, f, indent=2)
            return location
    except Exception as e:
        print(f"  [Scene analysis error] {e}")
    return ""
