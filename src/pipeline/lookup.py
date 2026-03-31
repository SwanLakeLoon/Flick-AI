"""
Flick AI — Database Lookup Utilities (Pass 4)
==============================================
Runs plate registration queries via VinCheck.info + NHTSA.
Includes OCR confusion handling and neighboring-state expansion logic.
"""

import os
import json
import requests
import time

# ── OCR Confusion Handling ─────────────────────────────────────────────────────
def load_ocr_confusion_patterns() -> dict:
    """Parse ocr_confusion_patterns.md into {char: [substitutes]} mapping."""
    # src/pipeline/lookup.py → src/ocr_confusion_patterns.md
    _src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    patterns_file = os.path.join(_src_dir, "ocr_confusion_patterns.md")
    confusion_map: dict = {}
    if not os.path.exists(patterns_file):
        print(f"[Warning] ocr_confusion_patterns.md not found at {patterns_file}")
        return confusion_map
    with open(patterns_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "->" not in line:
                continue
            left, right = line.split("->", 1)
            right = right.split("#")[0].strip()
            char = left.strip().upper()
            subs = [s.strip().upper() for s in right.split(",") if s.strip()]
            if char and subs:
                confusion_map[char] = subs
    return confusion_map

OCR_CONFUSION_MAP = load_ocr_confusion_patterns()


def generate_substitution_candidates(plate: str, confusion_map: dict, max_candidates: int = 20) -> list:
    """Generate candidate plates by swapping one confusable character at a time (Lev-1 only)."""
    candidates = []
    seen = {plate}

    for pos in range(len(plate)):
        ch = plate[pos]
        if ch in confusion_map:
            for sub in confusion_map[ch]:
                new_plate = plate[:pos] + sub + plate[pos+1:]
                if new_plate not in seen:
                    seen.add(new_plate)
                    candidates.append(new_plate)
                    if len(candidates) >= max_candidates:
                        return candidates

    return candidates


def generate_plate_specific_hints(plate: str, confusion_map: dict) -> str:
    """Generate plate-specific OCR confusion hints for Flash reeval prompt."""
    lines = []
    for pos, ch in enumerate(plate):
        if ch in confusion_map:
            subs = ", ".join(confusion_map[ch])
            lines.append(f"  - Position {pos+1}: '{ch}' commonly misread as {subs}")
    if not lines:
        return "No specific confusable characters identified in this plate."
    return "\n".join(lines)


# ── Neighboring-State Expansion (2a / 2b) ─────────────────────────────────────
_NEIGHBOR_STATES: dict = {
    "MN": ["WI", "IA", "ND", "SD", "IL"],
    "WI": ["MN", "IL", "IA"],
    "IA": ["MN", "WI", "IL", "MO", "SD"],
    "ND": ["MN", "SD", "MT"],
    "SD": ["MN", "ND", "IA", "NE"],
    "IL": ["IN", "MO", "WI", "IA"],
}

def _promote(lst: list, value: str) -> None:
    if value in lst:
        lst.remove(value)
        lst.insert(0, value)


from .format_analyzer import get_probable_states

def infer_likely_states(plate: str, assigned_state: str = "MN") -> list:
    """Return a priority-ordered list of states based on formatting and geography."""
    # 1. Base geographic neighbors
    neighbors = list(_NEIGHBOR_STATES.get(assigned_state, ["WI", "IA", "ND", "SD", "IL"]))
    
    # 2. Extract formatting matches 
    probable_states = get_probable_states(plate)
    
    # Tier 1: Neighbors that ALSO match the alphanumeric format perfectly
    tier_1 = [s for s in neighbors if s in probable_states]
    
    # Tier 2: The remaining neighbors (in case of OCR hallucination breaking the format)
    tier_2 = [s for s in neighbors if s not in tier_1]
    
    # Tier 3: Other states nationally that perfectly match the format (capped at 3 to prevent explosion)
    tier_3 = [s for s in probable_states if s not in neighbors][:3]
    
    # Combine the tiers into a smart-fallback array
    final_list = tier_1 + tier_2 + tier_3
    
    return final_list if final_list else neighbors


def try_neighboring_states(
    plate: str,
    assigned_state: str,
    obs_words: set,
    db_cache: dict,
    db_cache_file: str,
) -> tuple:
    """Try plate in neighboring states after all local lookups fail."""
    neighbors = infer_likely_states(plate, assigned_state)
    print(f"  [State expansion] {plate} — trying neighbors {neighbors} of {assigned_state}...")
    for alt_state in neighbors:
        alt_info = try_registration(plate, alt_state, db_cache, db_cache_file)
        if alt_info.get("registration_found"):
            alt_desc  = alt_info.get("desc", "")
            alt_words = set(alt_desc.lower().split())
            alt_match = "Y" if (obs_words & alt_words or any(w in alt_desc.lower() for w in obs_words if len(w) > 3)) else "N"
            if alt_match == "Y":
                print(f"    → State expansion hit! {plate} found in {alt_state}: {alt_desc[:40]}")
                return alt_info, alt_state
            else:
                print(f"    → {plate} in {alt_state} registered ({alt_desc[:30]}) but vehicle mismatch — skipping.")
    
    print(f"    → State expansion: no match found for {plate} in any neighbor state.")
    return None, ""


def _clean_state(state: str) -> str:
    s = (state or "").strip().upper()
    return s if (len(s) == 2 and s.isalpha()) else ""


def lookup_platetovin(plate: str, state: str) -> dict:
    """Look up a US plate via the PlateToVin commercial API.
    
    Tries each API key in round-robin order. On auth/quota failures (401/403/429),
    rotates to the next key. On 404 (plate not in DB), stops immediately.
    """
    import pipeline.config as cfg

    if not cfg.PTV_KEYS:
        return {"registration_found": False, "desc": "PlateToVin keys not configured", "vin": "", "title": ""}

    clean_plate = plate.replace(" ", "").replace("-", "").upper()
    clean_state = state.upper() if state and len(state) == 2 else ""

    # Try each key once in round-robin before giving up
    for _ in range(len(cfg.PTV_KEYS)):
        key = cfg.PTV_KEYS[cfg.ptv_key_index % len(cfg.PTV_KEYS)]
        try:
            resp = requests.post(
                "https://platetovin.com/api/convert",
                headers={"Authorization": key, "Content-Type": "application/json", "Accept": "application/json"},
                json={"plate": clean_plate, "state": clean_state},
                timeout=10
            )
            # 404 = plate not found in their DB — stop, don't rotate
            if resp.status_code == 404:
                return {"registration_found": False, "desc": "registration not found", "vin": "", "title": ""}
            # Auth/quota/rate-limit/payment failures — rotate to next key
            if resp.status_code in (401, 402, 403, 429) or resp.status_code >= 500:
                print(f"    [PlateToVin] Key {cfg.ptv_key_index % len(cfg.PTV_KEYS)} rejected (HTTP {resp.status_code}), rotating...")
                cfg.ptv_key_index += 1
                continue
            # Any other non-200 — treat as transient, don't rotate
            if resp.status_code != 200:
                return {"registration_found": False, "desc": f"PlateToVin HTTP {resp.status_code}", "vin": "", "title": ""}
            data = resp.json()
            if not data.get("success"):
                # success:false on 200 — check if it's a key/auth error signal
                msg = data.get("error") or data.get("message") or ""
                if any(kw in msg.lower() for kw in ["invalid", "unauthorized", "quota", "limit", "auth"]):
                    print(f"    [PlateToVin] Key {cfg.ptv_key_index % len(cfg.PTV_KEYS)} auth error ({msg}), rotating...")
                    cfg.ptv_key_index += 1
                    continue
                # Any other success:false = plate not found
                return {"registration_found": False, "desc": "registration not found", "vin": "", "title": ""}
            v = data.get("vin") or {}
            if not v:
                return {"registration_found": False, "desc": "registration not found", "vin": "", "title": ""}
            desc = " ".join(x for x in [str(v.get("year", "")), v.get("make", ""), v.get("model", ""), v.get("trim", "")] if x).strip()
            return {"registration_found": True, "desc": desc, "vin": v.get("vin", ""), "title": ""}
        except Exception as e:
            # Network/timeout error — transient, don't rotate the key
            return {"registration_found": False, "desc": f"PlateToVin Error: {e}", "vin": "", "title": ""}

    return {"registration_found": False, "desc": "PlateToVin all keys exhausted", "vin": "", "title": ""}


def try_registration(plate: str, state: str, db_cache: dict, db_cache_file: str) -> dict:
    """Consolidated registration lookup via PlateToVin with caching."""
    clean_state = _clean_state(state)
    db_key = f"{plate}_{clean_state}"

    if db_key in db_cache:
        cached = db_cache[db_key]
        # Re-try transient failures (throttled/timeout) but serve real results from cache
        is_transient = (
            not cached.get("registration_found") and
            any(kw in cached.get("desc", "").lower() for kw in ["throttled", "timeout", "exhausted", "error"])
        )
        if not is_transient:
            print(f"  [Lookup] {plate} ({clean_state})... → Cache hit")
            return cached

    def _cache_and_return(info: dict) -> dict:
        db_cache[db_key] = info
        with open(db_cache_file, "w") as f:
            json.dump(db_cache, f, indent=2)
        return info

    print(f"  [Lookup] {plate} ({clean_state or 'Unknown'})...")

    # Also check PlateToVin-specific cache key
    ptv_key = f"ptv_{plate}_{clean_state}"
    _cached_ptv = db_cache.get(ptv_key)
    _is_transient = (
        _cached_ptv is not None and
        not _cached_ptv.get("registration_found") and
        any(kw in _cached_ptv.get("desc", "").lower() for kw in ["throttled", "timeout", "exhausted", "error"])
    )
    if ptv_key in db_cache and not _is_transient:
        ptv_info = db_cache[ptv_key]
        print(f"    → [PlateToVin] Cache hit")
    else:
        print(f"    [PlateToVin] Looking up {plate} ({clean_state})...")
        ptv_info = lookup_platetovin(plate, clean_state)
        # Don't cache transient failures
        if not any(kw in ptv_info.get("desc", "").lower() for kw in ["exhausted", "error"]):
            db_cache[ptv_key] = ptv_info
            with open(db_cache_file, "w") as f:
                json.dump(db_cache, f, indent=2)

    if ptv_info.get("registration_found"):
        print(f"    → [PlateToVin] Found: {ptv_info.get('desc', '')}")
        return _cache_and_return(ptv_info)
    else:
        desc = ptv_info.get("desc", "registration not found")
        print(f"    → [PlateToVin] {desc}")
        return _cache_and_return({"registration_found": False, "desc": desc, "vin": "", "title": ""})


