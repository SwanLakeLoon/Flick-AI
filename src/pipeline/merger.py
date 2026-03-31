"""
Flick AI — Merger & Deduplication
===================================
Union merge for ALPR/Gemini, hallucination filtering, and fuzzy deduplication.
"""

def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def union_merge(alpr_plates: dict, gemini_plates: dict) -> dict:
    """
    Merge the two dictionaries. If a plate exists in both:
      - Add source="ALPR+GEMINI"
      - Keep the higher confidence scores
      - Prefer ALPR native MMC if present, otherwise Gemini MMC.
      - Default to the ALPR best frame.
    """
    merged = {}
    
    for plate, adata in alpr_plates.items():
        if plate in gemini_plates:
            gdata = gemini_plates[plate]
            merged_data = dict(adata)
            merged_data['source'] = 'ALPR+GEMINI'
            
            # Use max plate score
            if gdata['plate_confidence'] > adata['plate_confidence']:
                merged_data['plate_confidence'] = gdata['plate_confidence']
                merged_data['score'] = gdata['plate_confidence']
                
            # Usually keep Gemini's state if ALPR missed it, and state conf
            if gdata['state'] and gdata['state'] != 'UNKNOWN':
                if not merged_data['state'] or merged_data['state'] == 'UNKNOWN' or gdata['state_confidence'] > adata['state_confidence']:
                    merged_data['state'] = gdata['state']
                    merged_data['state_confidence'] = gdata['state_confidence']
                    
            # Gemini typically has MMC when ALPR Pro doesn't
            if not merged_data['make']: merged_data['make'] = gdata.get('make') or ''
            if not merged_data['model']: merged_data['model'] = gdata.get('model') or ''
            if not merged_data['color']: merged_data['color'] = gdata.get('color') or ''
            
            merged[plate] = merged_data
        else:
            merged[plate] = dict(adata)
            
    # Add Gemini-only plates
    for plate, gdata in gemini_plates.items():
        if plate not in merged:
            merged[plate] = dict(gdata)
            
    return merged


def check_hallucination_pattern(plate: str) -> tuple[bool, str]:
    """Returns (is_hallucination, reason). Strictly checks for egregious patterns."""
    p = plate.upper().strip()
    
    digits = ''.join(filter(str.isdigit, p))
    
    # 1. Flag >= 5 sequential digits (up or down)
    if len(digits) >= 5:
        nums = [int(d) for d in digits]
        is_ascending = all(nums[i+1] == nums[i] + 1 for i in range(len(nums) - 1))
        is_descending = all(nums[i+1] == nums[i] - 1 for i in range(len(nums) - 1))
        
        if is_ascending or is_descending:
             return True, f"sequence_of_5+_digits({digits})"
            
    # 2. Flag >= 5 identical digits (e.g. '00000', '99999')
    if len(digits) >= 5 and len(set(digits)) == 1:
        return True, f"repeated_5+_digits({digits})"
        
    # 3. Known dummy/demo words
    dummy_patterns = {'TEST', 'SAMPLE', 'DEALER', 'XXXX'}
    if any(d in p for d in dummy_patterns):
        return True, "known_dummy_word"
        
    return False, ""


def filter_hallucinations(plates: dict) -> dict:
    """Filter out plates that trigger hallucination warnings."""
    filtered_plates = {}
    for plate, data in plates.items():
        is_hall, reason = check_hallucination_pattern(plate)
        if is_hall:
            print(f"  [Hallucination filter] Dropped '{plate}' — {reason}")
        else:
            filtered_plates[plate] = data
    return filtered_plates


def deduplicate_plates(plates: dict) -> dict:
    """
    Deduplicate near-matches from the same video.
    Groups plates by video, sorts by confidence descending, and accepts a plate if
    it doesn't closely match (Levenshtein <= 2 or sharing first 4 chars) an already
    accepted higher-confidence plate.
    """
    video_groups = {}
    for p, data in plates.items():
        v = data.get('video', 'unknown')
        if v not in video_groups: video_groups[v] = []
        video_groups[v].append((p, data))
        
    deduped_plates = {}
    for v, plates_in_vid in video_groups.items():
        plates_in_vid.sort(key=lambda x: x[1].get('score', 0.0), reverse=True)
        accepted = []
        for p, data in plates_in_vid:
            is_dup = False
            for ap, adata in accepted:
                if levenshtein_distance(p, ap) <= 2:
                    is_dup = True
                    break
                if len(p) >= 5 and len(ap) >= 5 and p[:4] == ap[:4]:
                    is_dup = True
                    break
            
            if not is_dup:
                accepted.append((p, data))
                deduped_plates[p] = data
            else:
                print(f"  [Dedup] Dropped variant '{p}' (confidence {data.get('score',0.0):.2f}) in favor of a higher-confidence match")
                
    return deduped_plates
