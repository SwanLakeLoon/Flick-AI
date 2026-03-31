#!/usr/bin/env python3
"""
Flick AI — Modularized Batch Pipeline Orchestrator
===================================================
Ties together extraction, verification, lookup, and merging modules
to process a directory of videos or images.
"""

import os
import glob
import shutil
import time
import json
import argparse
import subprocess
import requests
import sys
from pathlib import Path

# Need to put src/ in sys.path so we can do `from pipeline.xxx import ...`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Pipeline Modules
from pipeline.config import EPHEMERAL_DIR, COLOR_NORMALIZE, COLOR_MAP, normalize_color
from pipeline.video import split_long_videos, get_video_duration_seconds, extract_frame_at_timestamp, strip_audio
from pipeline.extractor import (
    detect_location_from_video, run_alpr_pass, gemini_flash_video_pass, load_alpr_tokens
)
from pipeline.merger import union_merge, filter_hallucinations, deduplicate_plates, levenshtein_distance
from pipeline.verifier import (
    verify_state_via_gemini, extract_visual_metadata, escalate_to_gemini_pro, 
    gemini_flash_confirm_plate, gemini_flash_reeval, format_bias_reeval
)
from pipeline.lookup import (
    try_registration, try_neighboring_states, generate_substitution_candidates, 
    generate_plate_specific_hints, OCR_CONFUSION_MAP
)
from pipeline.format_analyzer import get_probable_states
from pipeline.ice import lookup_ice
from pipeline.output import write_results, write_edge_cases, write_stats, print_stats_summary
from pipeline.escalation import resolve_plate_escalation

# Source Modules
from plate_formats import is_valid_format, get_candidate_states


def _get_date_processed(target_dir: str, override: str = None) -> str:
    """Walk up the path until we find an 8-digit MMDDYYYY folder."""
    if override is not None:
        return override
    _search = str(os.path.abspath(target_dir))
    for _ in range(5):
        _seg = os.path.basename(_search)
        if len(_seg) == 8 and _seg.isdigit():
            return f"{_seg[0:2]}/{_seg[2:4]}/{_seg[4:8]}"
        _parent = os.path.dirname(_search)
        if _parent == _search:
            break
        _search = _parent
    return ""


def run_pipeline(target_dir: str, job_id: str = None, location_override: str = None, date_override: str = None) -> dict:
    _run_start_time = time.time()

    target_dir = os.path.abspath(target_dir)
    print(f"[{job_id}] Processing directory: {target_dir}")
    if location_override: print(f"  [Override] Location = '{location_override}'")
    if date_override: print(f"  [Override] Date = '{date_override}'")

    # ── Discover videos and images ─────────────────────────────────────────────
    videos = []
    for ext in ["*.MOV", "*.mp4", "*.avi", "*.mov", "*.MP4", "*.AVI"]:
        videos.extend(glob.glob(os.path.join(target_dir, ext)))
    videos = sorted(videos)

    image_files = []
    if not videos:
        _seen_stems = set()
        for ext in ["*.HEIC", "*.heic", "*.jpg", "*.JPG", "*.jpeg", "*.JPEG", "*.png", "*.PNG"]:
            for _p in sorted(glob.glob(os.path.join(target_dir, ext))):
                _stem = os.path.splitext(os.path.basename(_p))[0]
                if _stem not in _seen_stems:
                    _seen_stems.add(_stem)
                    image_files.append(_p)
        image_files = sorted(image_files)

    if not videos and not image_files:
        print(f"No video or image files found in {target_dir}")
        return {"status": "completed", "stats": {}, "results": []}
        
    image_mode = len(image_files) > 0 and len(videos) == 0
    if image_mode:
        print(f"  [Image Mode] Found {len(image_files)} image(s).")
    else:
        # Strip audio before upload to save bandwidth & processing time (privacy + efficiency)
        print("\n" + "="*60)
        print("PRE-PROCESSING — Stripping audio track from videos")
        print("="*60)
        silent_videos = []
        for v in videos:
            print(f"  [Audio] Processing {os.path.basename(v)}...")
            silent = strip_audio(v)
            if silent != v:
                print(f"    → Stripped version saved to cache.")
            silent_videos.append(silent)
        
        videos = split_long_videos(silent_videos, target_dir)

    # ── Cache Setup: Load existing caches from target_dir into EPHEMERAL_DIR ────────
    for cache_name in ["lookup_cache.json", "alpr_cache.json", "gemini_flash_cache.json", "alpr_image_cache.json"]:
        source_path = os.path.join(target_dir, cache_name)
        dest_path = os.path.join(EPHEMERAL_DIR, cache_name)
        if os.path.exists(source_path):
            shutil.copy2(source_path, dest_path)

    db_cache_file = os.path.join(EPHEMERAL_DIR, "lookup_cache.json")
    db_cache = json.load(open(db_cache_file)) if os.path.exists(db_cache_file) else {}

    # Stats counters
    stats = {
        "video_sizes_mb": [os.path.getsize(v) / 1_048_576 for v in videos] if not image_mode else [],
        "video_durations_sec": [get_video_duration_seconds(v) for v in videos] if not image_mode else [],
        "gemini_flash_image_calls": 0,
        "gemini_pro_calls": 0,
        "pro_corrections": 0,
        "reg_found": 0,
        "reg_not_found": 0,
        "match_y": 0,
        "match_n": 0,
        "edge_flags": {},
        "ice_y": 0,
        "ice_hs": 0,
        "ocr_sub_attempts": 0,
        "ocr_sub_hits": 0,
        "ocr_sub_fallbacks": 0,
        "throttled": 0,
        "alpr_failures": [],
        "format_bias_triggers": 0,
        "format_bias_gemini_calls": 0,
        "format_bias_state_corrections": 0,
        "format_bias_brute_force_queries": 0,
        "format_bias_brute_force_hits": 0
    }

    # ── Pass 0: Scene Analysis ────────────────────────────────────────────────
    print("\n" + "="*60)
    print("PASS 0 — Scene Analysis (Location & Date)")
    print("="*60)
    
    video_locations = {}
    if not image_mode and location_override is None:
        for _vid in videos:
            video_locations[os.path.basename(_vid)] = detect_location_from_video(_vid)
    elif location_override is not None:
        for _vid in videos:
            video_locations[os.path.basename(_vid)] = location_override
            
    DATE_PROCESSED = _get_date_processed(target_dir, date_override)

    # Note locations
    _distinct_locs = sorted(set(v for v in video_locations.values() if v))
    for _dl in _distinct_locs: print(f"  → Location: {_dl}")
    if not _distinct_locs: print("  → Location: (not detected for any video)")
    print(f"  → Date:     {DATE_PROCESSED or '(not parsed)'}")

    # ── Pass 1: Extraction ────────────────────────────────────────────────────
    all_plates = {}
    if image_mode:
        print("\n" + "="*60)
        print("PASS 1 — Image Mode: ALPR on individual images")
        print("="*60)
        jpeg_images = []
        for img in image_files:
            base_stem = os.path.splitext(img)[0]
            if img.upper().endswith(".HEIC"):
                jpg_path = base_stem + ".jpg"
                if not os.path.exists(jpg_path):
                    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "best", "-Z", "2048", img, "--out", jpg_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                jpeg_images.append(jpg_path)
            else:
                jpg_2k = base_stem + "_2k.jpg"
                if not os.path.exists(jpg_2k):
                    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "best", "-Z", "2048", img, "--out", jpg_2k], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                jpeg_images.append(jpg_2k)

        alpr_image_cache_file = os.path.join(EPHEMERAL_DIR, "alpr_image_cache.json")
        alpr_image_cache = json.load(open(alpr_image_cache_file)) if os.path.exists(alpr_image_cache_file) else {}
        _img_tokens = load_alpr_tokens()
        _img_token_idx = 0

        for jpg in jpeg_images:
            img_name = os.path.basename(jpg)
            if img_name in alpr_image_cache:
                results = alpr_image_cache[img_name]
            else:
                token = _img_tokens[_img_token_idx % len(_img_tokens)] if _img_tokens else None
                if not token:
                    results = []
                else:
                    try:
                        with open(jpg, "rb") as fp:
                            resp = requests.post(
                                "https://api.platerecognizer.com/v1/plate-reader/",
                                files={"upload": fp},
                                data={
                                    "regions": ["us-mn", "us-wi", "us-ia", "us-nd"],
                                    "mmc": "true",
                                    "config": json.dumps({"detection_rule": "strict", "zoom_in_vehicles": 4})
                                },
                                headers={"Authorization": f"Token {token}"},
                                timeout=30
                            )
                        if resp.status_code == 429:
                            _img_token_idx += 1
                            results = []
                        else:
                            results = resp.json().get("results", []) if resp.status_code in (200, 201) else []
                            alpr_image_cache[img_name] = results
                            with open(alpr_image_cache_file, "w") as f:
                                json.dump(alpr_image_cache, f, indent=2)
                        time.sleep(0.2)
                    except Exception as e:
                        print(f"  [ALPR Error] {e}")
                        results = []

            for res in results:
                plate = (res.get("plate") or "").upper().replace(" ", "").replace("-", "")
                if not plate or len(plate) < 4: continue
                score = float(res.get("score", 0.0))
                if score < 0.85: continue
                
                region_data = res.get("region", {})
                state = region_data.get("code", "UNKNOWN").upper()
                if state.startswith("US-"): state = state[3:]
                elif state == "US": state = "UNKNOWN"

                if plate not in all_plates or score > all_plates[plate]["score"]:
                    make, model, color = "", "", ""
                    if res.get("model_make") and res["model_make"]:
                        mm = res["model_make"][0]
                        if mm.get("score", 0) > 0.5: make, model = mm.get("make", ""), mm.get("model", "")
                    if res.get("color") and res["color"]:
                        cc = res["color"][0]
                        if cc.get("score", 0) > 0.5: color = cc.get("color", "")

                    all_plates[plate] = {
                        "plate": plate, "state": state if state != "UNKNOWN" else "",
                        "score": score, "plate_confidence": score,
                        "state_confidence": score if state != "UNKNOWN" else 0.0,
                        "timestamp_sec": 0.0, "best_frame": jpg, "video": img_name,
                        "video_path": jpg, "source": "ALPR",
                        "make": make, "model": model, "color": color
                    }
        print(f"\n[Image ALPR] \u2192 {len(all_plates)} unique plates.")
    else:
        print("\n" + "="*60)
        print("PASS 1a — PlateRecognizer ALPR Extraction")
        print("="*60)
        alpr_plates, alpr_fail = run_alpr_pass(videos)
        stats["alpr_failures"] = alpr_fail

        print("\n" + "="*60)
        print("PASS 1b — Gemini Flash Full-Video Extraction")
        print("="*60)
        gemini_plates = gemini_flash_video_pass(videos)

        print("\n" + "="*60)
        print("UNION — Merging Results")
        print("="*60)
        all_plates = union_merge(alpr_plates, gemini_plates)
        print(f"Merged unique plates: {len(all_plates)}")

    all_plates = filter_hallucinations(all_plates)
    all_plates = deduplicate_plates(all_plates)

    # ── Verify / Frames ────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("FRAME EXTRACTION & VERIFICATION")
    print("="*60)
    
    frames_dir = os.path.join(EPHEMERAL_DIR, "_best_frames")
    os.makedirs(frames_dir, exist_ok=True)
    
    csv_rows, edge_case_rows = [], []
    
    for plate, data in all_plates.items():
        vid_path = data.get('video_path')
        ts = data.get('timestamp_sec', 0.0)
        vid_name = Path(data.get('video', 'unknown')).stem
        
        # Ensure best_frame exists
        if vid_path and os.path.exists(vid_path):
            if not (data.get('best_frame') and os.path.exists(data['best_frame'])):
                out_ts = f"{ts:.1f}".replace(".", "_")
                fpath = extract_frame_at_timestamp(vid_path, ts, os.path.join(frames_dir, f"{vid_name}_ts{out_ts}.jpg"))
                data['best_frame'] = fpath or ""
        else:
            if 'best_frame' not in data: data['best_frame'] = ""
            
        best_frame = data['best_frame']
        state = data.get('state', 'UNKNOWN')

        # ── Pass 2: State verification ────────────────────────────────────
        state_confidence = data.get('state_confidence', 0.6)
        flash_high_confidence_state = (
            data.get('source') in ('GEMINI_FLASH', 'ALPR+GEMINI') and
            state_confidence >= 0.90 and
            state not in ('UNKNOWN', '', 'MO')
        )
        should_verify = not flash_high_confidence_state
        if should_verify and best_frame and os.path.exists(best_frame):
            print(f"  [State verify] {plate} state={state} (state_conf={state_confidence:.2f}), querying Gemini Flash...")
            stats["gemini_flash_image_calls"] += 1
            v_state = verify_state_via_gemini(best_frame, plate)
            if v_state and v_state != state:
                orig_key = f"{plate}_{state if state and len(state)==2 else 'MN'}"
                if db_cache.get(orig_key, {}).get("registration_found", False):
                    print(f"    \u2192 Flash suggests {v_state}, but {state} already has a registration hit \u2014 keeping {state}")
                else:
                    print(f"    \u2192 {state} corrected to {v_state}")
                    state = v_state

        # ── Pass 3: Visual metadata ───────────────────────────────────────
        make = data.get('make', '')
        model = data.get('model', '')
        color_code = data.get('color', '')

        has_alpr_mmc = make != '' and model != '' and color_code != ''
        if has_alpr_mmc:
            print(f"  [Visual] Using native ALPR Pro MMC for {plate} (Skipping Gemini)")
            color_code = normalize_color(color_code)
        elif best_frame and os.path.exists(best_frame):
            print(f"  [Visual] Extracting make/model/color for {plate}...")
            stats["gemini_flash_image_calls"] += 1
            vis = extract_visual_metadata(best_frame, plate)
            if not make: make = vis.get('make', '')
            if not model: model = vis.get('model', '')
            if not color_code:
                raw_color = vis.get('color', '')
                color_code = normalize_color(raw_color)
        else:
            color_code = normalize_color(color_code) if color_code else ''

        # Update data dict with resolved values
        data['make'] = make
        data['model'] = model
        data['color'] = color_code
        
        # ── Lookup ────────────────────────────────────────────────────────────
        clean_state = state if state and len(state) == 2 else "MN"
        p_conf = float(data.get('plate_confidence', 0.6))
        db_key = f"{plate}_{clean_state}"
        was_throttled = False
        
        if p_conf <= 0.90 and db_key not in db_cache:
            info = {"registration_found": False}
        else:
            info = try_registration(plate, clean_state, db_cache, db_cache_file)
            if info.get("rate_limited"):
                was_throttled = True
            
        reg_found = info.get("registration_found", False)
        info_desc = info.get("desc", "registration not found")
        vin = info.get("vin", "")
        title = info.get("title", "")
        
        obs_words = set(f"{color_code} {make} {model}".lower().split())
        
        match_status = ""
        if reg_found:
            reg_words = set(info_desc.lower().split())
            match_status = "Y" if (obs_words & reg_words or any(w in info_desc.lower() for w in obs_words if len(w)>3)) else "N"

        initial_plate = plate
        initial_state = clean_state

        # ── Escalation Paths ─────────────────────────────────────────────
        plate, clean_state, reg_found, info_desc, vin, title, match_status, stats, db_cache = resolve_plate_escalation(
            plate, clean_state, db_cache, db_cache_file, stats, obs_words, best_frame, 
            reg_found, info_desc, vin, title, match_status, initial_plate, initial_state
        )

        if reg_found: stats["reg_found"] += 1
        else: stats["reg_not_found"] += 1
        if match_status == "Y": stats["match_y"] += 1
        elif "N" in match_status: stats["match_n"] += 1

        flags = []
        if len(plate) > 7: flags.append("PLATE_TOO_LONG")
        if plate.isdigit() and len(plate) >= 6: flags.append("NUMERIC_PLATE")
        if "N" in match_status: flags.append("REG_MISMATCH")
        if plate != initial_plate or clean_state != initial_state: flags.append(f"PRO_CORRECTED({initial_plate}→{initial_state})")
        if not is_valid_format(plate, clean_state) and not reg_found: flags.append("UNKNOWN_FORMAT")
        if not reg_found:
            if was_throttled: 
                flags.append("LOOKUP_THROTTLED")
                stats["throttled"] += 1
            else: flags.append("NO_REGISTRATION")
        
        for f in [f.split("(")[0] for f in flags]:
            stats["edge_flags"][f] = stats["edge_flags"].get(f, 0) + 1

        vid_source_label = f"Source: {data.get('video','unknown')}"
        csv_rows.append([
            plate, clean_state, data.get('make',''), data.get('model',''), color_code,
            "", match_status, info_desc, vin, 
            title[:47] + "..." if len(title) > 50 else title,
            vid_source_label, video_locations.get(data.get('video',''), ""), DATE_PROCESSED,
            f"{p_conf:.2f}"
        ])
        if flags:
            edge_case_rows.append([
                plate, clean_state, data.get('make',''), data.get('model',''), color_code,
                match_status, info_desc, "|".join(flags),
                video_locations.get(data.get('video',''), ""), DATE_PROCESSED
            ])
            
    # ── Pass 6: ICE ───────────────────────────────────────────────────────────
    for row in csv_rows:
        plate_str = row[0]
        ice_key = f"ice_{plate_str}"
        if ice_key in db_cache:
            ice_val = db_cache[ice_key]
        else:
            ice_val = lookup_ice(plate_str)
            db_cache[ice_key] = ice_val
            with open(db_cache_file, "w") as f:
                json.dump(db_cache, f, indent=2)
            time.sleep(0.5)
        row[5] = ice_val
        if ice_val == "Y": stats["ice_y"] += 1
        elif ice_val == "HS": stats["ice_hs"] += 1
        else: stats["ice_n"] = stats.get("ice_n", 0) + 1

    # Deduplicate csv_rows by (final_plate, original_plate, video_name)
    seen, deduped = set(), []
    for r in csv_rows:
        dk = (r[0], r[13], r[10]) # Use plate confidence at r[13] as dummy original plate key due to runner simplification
        if dk not in seen:
            seen.add(dk)
            deduped.append(r)
    csv_rows = deduped

    # Outputs
    headers = [
        "Plate", "State", "Make", "Model", "Color", "ICE", "Match",
        "Registration", "VIN Associated to Plate (if available)",
        "Title Issues Associated to VIN (if available)", "Notes", "Location", "Date", "Plate Confidence"
    ]
    out_csv, out_md, out_ec, out_stats = write_results(csv_rows, headers, target_dir, os.path.basename(target_dir))
    write_edge_cases(edge_case_rows, out_ec, DATE_PROCESSED)

    # Write standard results.csv / results.md aliases for downstream tools
    for src, alias_name in [(out_csv, "results.csv"), (out_md, "results.md"), (out_ec, "results_edge_cases.txt"), (out_stats, "results_stats.json")]:
        alias_path = os.path.join(target_dir, alias_name)
        if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(alias_path):
            shutil.copy2(src, alias_path)

    # Compile Final Stats
    _run_elapsed = time.time() - _run_start_time
    stats_out = {
        "batch": os.path.basename(target_dir),
        "date_processed": DATE_PROCESSED,
        "location": ", ".join(sorted(set(v for v in video_locations.values() if v))),
        "run_elapsed_seconds": _run_elapsed,
        "total_videos": len(videos) if not image_mode else len(jpeg_images),
        "videos": [{"name": os.path.basename(videos[i]), "duration_seconds": stats["video_durations_sec"][i], "size_mb": stats["video_sizes_mb"][i]} for i in range(len(videos))] if not image_mode else [],
        "total_unique_plates": len(csv_rows),
        "cost_flash_video": (sum(stats["video_durations_sec"]) / 60.0) * 0.075 if not image_mode else 0.0,
        "cost_flash_image": stats["gemini_flash_image_calls"] * 0.000075,
        "cost_pro": stats["gemini_pro_calls"] * 0.00125,
    }
    stats_out.update(stats)
    stats_out["cost_total_gemini"] = stats_out["cost_flash_video"] + stats_out["cost_flash_image"] + stats_out["cost_pro"]
    stats_out["cost_per_plate"] = stats_out["cost_total_gemini"] / max(1, len(csv_rows))
    stats_out["registration_pct"] = (stats["reg_found"] / max(1, len(csv_rows))) * 100
    
    write_stats(stats_out, out_stats)
    print_stats_summary(stats_out)

    # ── Persistence: Save all caches from EPHEMERAL_DIR back to target_dir ──────────
    for cache_name in ["lookup_cache.json", "alpr_cache.json", "gemini_flash_cache.json", "alpr_image_cache.json"]:
        source_path = os.path.join(EPHEMERAL_DIR, cache_name)
        dest_path = os.path.join(target_dir, cache_name)
        if os.path.exists(source_path):
            shutil.copy2(source_path, dest_path)

    structured_results = []
    for row in csv_rows:
        try:
            conf = float(row[13])
        except:
            conf = 0.0
        structured_results.append({
            "plate": row[0],
            "state": row[1],
            "make": row[2],
            "model": row[3],
            "color": row[4],
            "vin": row[8],
            "match": row[6],
            "confidence": conf,
            "edge_flags": []
        })

    return {
        "status": "completed",
        "stats": stats_out,
        "results": structured_results
    }


if __name__ == "__main__":
    import argparse as _ap
    parser = _ap.ArgumentParser(description="Flick AI Orchestrator")
    parser.add_argument("target_dir", nargs="?", default=os.getcwd(), help="Directory containing video or image files")
    parser.add_argument("--location", default=None, help="Override location")
    parser.add_argument("--date", default=None, help="Override date string")
    args = parser.parse_args()
    run_pipeline(target_dir=args.target_dir, location_override=args.location, date_override=args.date)
