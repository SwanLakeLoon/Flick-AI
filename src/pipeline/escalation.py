import os
import json
from pipeline.lookup import try_registration, generate_plate_specific_hints, try_neighboring_states, generate_substitution_candidates, OCR_CONFUSION_MAP
from pipeline.verifier import format_bias_reeval, gemini_flash_confirm_plate, gemini_flash_reeval
from plate_formats import is_valid_format, get_candidate_states
from pipeline.format_analyzer import get_probable_states

def resolve_plate_escalation(
    plate: str, 
    clean_state: str, 
    db_cache: dict, 
    db_cache_file: str, 
    stats: dict, 
    obs_words: set, 
    best_frame: str, 
    reg_found: bool, 
    info_desc: str, 
    vin: str, 
    title: str, 
    match_status: str,
    initial_plate: str,
    initial_state: str
):
    """
    Handles the 7-phase escalation path for resolving a plate against the DMV oracle.
    Short-circuits (early exit and flag as found_y=True) as soon as a 'Y' match is found.
    Returns:
        (plate, clean_state, reg_found, info_desc, vin, title, match_status, stats, db_cache)
    """
    # Short-circuit only on a confirmed Y match; everything else falls through.
    if reg_found and match_status == "Y":
        print(f"  [Short-circuit] {plate} ({clean_state}) \u2014 registration match, skipping escalation.")
        return plate, clean_state, reg_found, info_desc, vin, title, match_status, stats, db_cache

    # Preserve any mismatch result as a fallback (reg found but wrong vehicle)
    mismatch_fallback = None
    if reg_found and match_status == "N":
        mismatch_fallback = {"plate": plate, "state": clean_state, "desc": info_desc, "vin": vin, "title": title}

    found_y = False

    # Phase A.5: Dynamic Format Biasing ────────────────────────────
    if not found_y and not is_valid_format(plate, clean_state):
        fmt_candidates = get_candidate_states(plate, exclude_state=clean_state)
        if fmt_candidates:
            stats["format_bias_triggers"] += 1
            print(f"  [Format Bias] {plate} format invalid for {clean_state}. Candidates: {fmt_candidates}")

            # Strategy 1: Gemini second-look with candidate hints
            if best_frame and os.path.exists(best_frame):
                stats["gemini_flash_image_calls"] += 1
                stats["format_bias_gemini_calls"] += 1
                fb_state, fb_plate = format_bias_reeval(
                    best_frame, plate, clean_state, fmt_candidates
                )
                if fb_state and fb_plate:
                    print(f"    \u2192 Gemini suggests {fb_state} / {fb_plate}")
                    fb_info = try_registration(fb_plate, fb_state, db_cache, db_cache_file)
                    if fb_info.get("registration_found"):
                        fb_desc = fb_info.get("desc", "")
                        fb_words = set(fb_desc.lower().split())
                        fb_match = "Y" if (obs_words & fb_words or any(w in fb_desc.lower() for w in obs_words if len(w) > 3)) else "N"
                        if fb_match == "Y":
                            print(f"    \u2192 Format bias hit! {plate}({clean_state}) → {fb_plate}({fb_state})")
                            clean_state, plate = fb_state, fb_plate
                            reg_found, info_desc, vin, title, match_status = True, fb_desc, fb_info.get("vin", ""), fb_info.get("title", ""), "Y"
                            stats["format_bias_state_corrections"] += 1
                            found_y = True
                        elif mismatch_fallback is None:
                            mismatch_fallback = {"plate": fb_plate, "state": fb_state, "desc": fb_desc, "vin": fb_info.get("vin", ""), "title": fb_info.get("title", "")}

            # Strategy 2: State brute-force with original plate (capped)
            _GLOBAL_FORMAT_BIAS_BUDGET = 100
            if not found_y and stats["format_bias_brute_force_queries"] < _GLOBAL_FORMAT_BIAS_BUDGET:
                remaining_budget = _GLOBAL_FORMAT_BIAS_BUDGET - stats["format_bias_brute_force_queries"]
                bf_cap = min(len(fmt_candidates), 20, remaining_budget)
                print(f"  [Format Bias] Brute-forcing {bf_cap} candidate states for {plate}... (budget: {remaining_budget} remaining)")
                for alt_state in fmt_candidates[:bf_cap]:
                    stats["format_bias_brute_force_queries"] += 1
                    alt_info = try_registration(plate, alt_state, db_cache, db_cache_file)
                    if alt_info.get("registration_found"):
                        alt_desc = alt_info.get("desc", "")
                        alt_words = set(alt_desc.lower().split())
                        alt_match = "Y" if (obs_words & alt_words or any(w in alt_desc.lower() for w in obs_words if len(w) > 3)) else "N"
                        if alt_match == "Y":
                            print(f"    \u2192 Brute-force hit! {plate} found in {alt_state}: {alt_desc[:40]}")
                            clean_state, reg_found, info_desc = alt_state, True, alt_desc
                            vin, title, match_status = alt_info.get("vin", ""), alt_info.get("title", ""), "Y"
                            stats["format_bias_state_corrections"] += 1
                            stats["format_bias_brute_force_hits"] += 1
                            found_y = True
                            break
                        elif mismatch_fallback is None:
                            mismatch_fallback = {"plate": plate, "state": alt_state, "desc": alt_desc, "vin": alt_info.get("vin", ""), "title": alt_info.get("title", "")}
            elif not found_y and stats["format_bias_brute_force_queries"] >= _GLOBAL_FORMAT_BIAS_BUDGET:
                print(f"  [Format Bias] Global budget exhausted ({_GLOBAL_FORMAT_BIAS_BUDGET} queries). Skipping brute-force for {plate}.")
        else:
            print(f"  [Format Bias] {plate} format invalid for {clean_state}, but no strict candidate states found (likely vanity). Skipping.")

    # Phase B: Flash confirm (only useful if we had a mismatch to re-read)
    if not found_y and reg_found and match_status == "N":
        if best_frame and os.path.exists(best_frame):
            stats["gemini_flash_image_calls"] += 1
            conf = gemini_flash_confirm_plate(best_frame, plate)
            if conf != plate:
                r_info = try_registration(conf, clean_state, db_cache, db_cache_file)
                if r_info.get("registration_found"):
                    r_desc = r_info.get("desc","")
                    r_words = set(r_desc.lower().split())
                    r_match = "Y" if (obs_words & r_words or any(w in r_desc.lower() for w in obs_words if len(w)>3)) else "N"
                    if r_match == "Y":
                        plate, reg_found, info_desc, vin, title, match_status = conf, True, r_desc, r_info.get("vin",""), r_info.get("title",""), "Y"
                        found_y = True
                    elif mismatch_fallback is None:
                        mismatch_fallback = {"plate": conf, "state": clean_state, "desc": r_desc, "vin": r_info.get("vin",""), "title": r_info.get("title","")}

    # Phase C: Flash re-eval with OCR hints 
    if not found_y:
        if best_frame and os.path.exists(best_frame):
            stats["gemini_flash_image_calls"] += 1
            hints = generate_plate_specific_hints(plate, OCR_CONFUSION_MAP)
            fs, fp = gemini_flash_reeval(best_frame, plate, clean_state, hints)
            if fs and fp and (fs != clean_state or fp != plate):
                f_info = try_registration(fp, fs, db_cache, db_cache_file)
                if f_info.get("registration_found"):
                    f_desc = f_info.get("desc","")
                    f_words = set(f_desc.lower().split())
                    f_match = "Y" if (obs_words & f_words or any(w in f_desc.lower() for w in obs_words if len(w)>3)) else "N"
                    if f_match == "Y":
                        clean_state, plate, reg_found = fs, fp, True
                        info_desc, vin, title, match_status = f_desc, f_info.get("vin",""), f_info.get("title",""), "Y"
                        found_y = True
                    elif mismatch_fallback is None:
                        mismatch_fallback = {"plate": fp, "state": fs, "desc": f_desc, "vin": f_info.get("vin",""), "title": f_info.get("title","")}

    # Phase D: State expansion with caching 
    if not found_y:
        plate_is_vanity = (len(plate) > 7 or plate.isalpha()) and not get_probable_states(plate)
        if not plate_is_vanity:
            _neighbor_state_cache_key = f"neighbor_state_{plate}_{clean_state}"
            if _neighbor_state_cache_key not in db_cache:
                exp_info, exp_state = try_neighboring_states(plate, clean_state, obs_words, db_cache, db_cache_file)
                if exp_info:
                    print(f"    \u2192 Neighbor expansion accepted: {plate} in {exp_state}")
                    clean_state, reg_found, info_desc, vin, title, match_status = exp_state, True, exp_info.get("desc",""), exp_info.get("vin",""), exp_info.get("title",""), "Y"
                    found_y = True
                db_cache[_neighbor_state_cache_key] = {"attempted": True, "hit": exp_info is not None, "result_state": exp_state if exp_info else ""}
                with open(db_cache_file, "w") as f:
                    json.dump(db_cache, f, indent=2)
            else:
                cached_exp = db_cache[_neighbor_state_cache_key]
                if cached_exp.get("hit") and cached_exp.get("result_state"):
                    exp_state = cached_exp["result_state"]
                    exp_info = try_registration(plate, exp_state, db_cache, db_cache_file)
                    if exp_info.get("registration_found"):
                        print(f"    \u2192 Neighbor expansion cache hit! {plate} in {exp_state}")
                        clean_state, reg_found, info_desc, vin, title, match_status = exp_state, True, exp_info.get("desc",""), exp_info.get("vin",""), exp_info.get("title",""), "Y"
                        found_y = True
        else:
            print(f"  [State expansion] Skipping {plate} \u2014 vanity/invalid format.")

    # Phase E: OCR character substitution brute force
    # Item A: each candidate is also cross-tried against the top-2 format-probable states
    # to catch cases where ALPR assigned the wrong state (e.g. MTY448→MTY440 IA not MN)
    if not found_y:
        sub_cache_key = f"ocr_sub_{plate}_{clean_state}"
        if sub_cache_key not in db_cache:
            cands = generate_substitution_candidates(plate, OCR_CONFUSION_MAP)
            if cands:
                print(f"  [OCR sub] Trying {len(cands)} substitution candidates for {plate} ({clean_state})...")
            ocr_sub_hit = False
            for cand in cands:
                # First try in the primary assigned state
                stats["ocr_sub_attempts"] += 1
                sub_info = try_registration(cand, clean_state, db_cache, db_cache_file)
                if sub_info.get("registration_found"):
                    s_desc = sub_info.get("desc","")
                    s_words = set(s_desc.lower().split())
                    s_match = "Y" if (obs_words & s_words or any(w in s_desc.lower() for w in obs_words if len(w)>3)) else "N"
                    if s_match == "Y":
                        print(f"    \u2192 OCR sub hit! {plate} \u2192 {cand} ({clean_state}): {s_desc[:40]}")
                        plate, reg_found, info_desc, vin, title, match_status = cand, True, s_desc, sub_info.get("vin",""), sub_info.get("title",""), "Y"
                        stats["ocr_sub_hits"] += 1
                        ocr_sub_hit = True
                        found_y = True
                        break
                    elif mismatch_fallback is None:
                        mismatch_fallback = {"plate": cand, "state": clean_state, "desc": s_desc, "vin": sub_info.get("vin",""), "title": sub_info.get("title","")}

                # Item A: cross-try against top-2 format-probable states
                if not found_y:
                    alt_states = [s for s in get_probable_states(cand) if s != clean_state][:2]
                    for alt_state in alt_states:
                        stats["ocr_sub_attempts"] += 1
                        alt_info = try_registration(cand, alt_state, db_cache, db_cache_file)
                        if alt_info.get("registration_found"):
                            a_desc = alt_info.get("desc","")
                            a_words = set(a_desc.lower().split())
                            a_match = "Y" if (obs_words & a_words or any(w in a_desc.lower() for w in obs_words if len(w)>3)) else "N"
                            if a_match == "Y":
                                print(f"    \u2192 OCR sub cross-state hit! {plate} \u2192 {cand} ({alt_state}): {a_desc[:40]}")
                                plate, clean_state, reg_found = cand, alt_state, True
                                info_desc, vin, title, match_status = a_desc, alt_info.get("vin",""), alt_info.get("title",""), "Y"
                                stats["ocr_sub_hits"] += 1
                                ocr_sub_hit = True
                                found_y = True
                                break
                            elif mismatch_fallback is None:
                                mismatch_fallback = {"plate": cand, "state": alt_state, "desc": a_desc, "vin": alt_info.get("vin",""), "title": alt_info.get("title","")}
                if found_y:
                    break

            db_cache[sub_cache_key] = {"attempted": True, "hit": ocr_sub_hit, "result_plate": plate if ocr_sub_hit else "", "match_status": match_status if ocr_sub_hit else ""}
            with open(db_cache_file, "w") as f:
                json.dump(db_cache, f, indent=2)
        else:
            cached_sub = db_cache[sub_cache_key]
            if cached_sub.get("hit") and cached_sub.get("result_plate"):
                plate = cached_sub["result_plate"]
                sub_info = try_registration(plate, clean_state, db_cache, db_cache_file)
                if sub_info.get("registration_found"):
                    info_desc = sub_info.get("desc","")
                    vin = sub_info.get("vin","")
                    title = sub_info.get("title","")
                    reg_found = True
                    match_status = cached_sub.get("match_status", "Y")
                    found_y = True

    # Fallback: if nothing found a Y match, use the best mismatch result
    if not found_y and mismatch_fallback:
        plate = mismatch_fallback["plate"]
        clean_state = mismatch_fallback.get("state", clean_state)
        info_desc = mismatch_fallback["desc"]
        vin = mismatch_fallback["vin"]
        title = mismatch_fallback["title"]
        reg_found = True
        match_status = "N"
        stats["ocr_sub_fallbacks"] += 1

    return plate, clean_state, reg_found, info_desc, vin, title, match_status, stats, db_cache
