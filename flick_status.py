#!/usr/bin/env python3
"""
Flick AI — Pipeline Status Checker
==================================
Checks the ephemeral cache directory to estimate how far along
the currently running (or most recent) pipeline is.
"""

import os
import json
import time

CACHE_DIR = ".alpr_cache"

def load_cache(filename):
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def count_frames_dir():
    frames_dir = os.path.join(CACHE_DIR, "_best_frames")
    if os.path.exists(frames_dir):
        return len([f for f in os.listdir(frames_dir) if f.endswith(".jpg")])
    return 0

def main():
    if not os.path.exists(CACHE_DIR):
        print("No active pipeline cache found (.alpr_cache directory does not exist).")
        return

    print("\n============================================================")
    print("FLICK AI PIPELINE — LIVE STATUS MAP")
    print("============================================================\n")

    # ALPR Pass
    alpr_cache = load_cache("alpr_cache.json")
    alpr_chunks = len(alpr_cache.keys())
    alpr_plates = sum(len(plates) for plates in alpr_cache.values())
    if alpr_chunks > 0:
        print(f"✅ Pass 1a (ALPR): Processed {alpr_chunks} images/chunks, found ~{alpr_plates} raw plate reads.")
    else:
        print("⏳ Pass 1a (ALPR): Not started or zero chunks processed.")

    # Gemini Flash Pass
    gemini_cache = load_cache("gemini_flash_cache.json")
    gemini_vids = len(gemini_cache.keys())
    gemini_plates = sum(len(plates) for plates in gemini_cache.values())
    if gemini_vids > 0:
        print(f"✅ Pass 1b (Flash): Processed {gemini_vids} videos, found ~{gemini_plates} plates.")
    else:
        print("⏳ Pass 1b (Flash): Not started or zero videos processed.")

    # Verification / Best Frames
    frames_count = count_frames_dir()
    if frames_count > 0:
        print(f"🔄 Pass 2 (Verification): {frames_count} best-frames extracted for visual confirmation.")
    else:
        print("⏳ Pass 2 (Verification): Frame extraction not yet started.")

    # Registration Lookups
    lookup_cache = load_cache("lookup_cache.json")
    lookups = len(lookup_cache.keys())
    if lookups > 0:
        hits = sum(1 for v in lookup_cache.values() if isinstance(v, dict) and v.get("registration_found"))
        print(f"🔄 Pass 3 (Registration): {lookups} API lookups completed ({hits} hits).")
    else:
        print("⏳ Pass 3 (Registration): Lookups not yet started.")

    # Last modified
    try:
        mod_times = [os.path.getmtime(os.path.join(CACHE_DIR, f)) for f in os.listdir(CACHE_DIR) if os.path.isfile(os.path.join(CACHE_DIR, f))]
        if mod_times:
            last_mod = max(mod_times)
            seconds_ago = time.time() - last_mod
            print(f"\nLast pipeline activity: {seconds_ago:.1f} seconds ago.")
            if seconds_ago > 300:
                print("⚠️ Pipeline seems idle or stalled (no cache updates in 5+ minutes).")
            else:
                print("⚡️ Pipeline is actively running!")
    except Exception as e:
        pass

    print("\nNote: This is a cache-based estimate. Final unified plate counts will differ after deduplication.")
    print("============================================================\n")

if __name__ == "__main__":
    main()
