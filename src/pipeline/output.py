"""
Flick AI — Output Generators
==============================
Handles formatting of CSV/MD reports, edge cases, and printing statistics.
"""

import os
import csv
import json


def write_results(csv_rows: list, headers: list, target_dir: str, date_label: str) -> tuple[str, str, str, str]:
    """Writes the main Results, Markdown, Edge Cases, and Stats JSON to disk."""
    _abs = os.path.abspath(target_dir)
    _date_seg = ""
    _batch_seg = ""
    _walk = _abs
    for _ in range(5):
        _seg = str(os.path.basename(_walk))
        if len(_seg) == 8 and _seg.isdigit():
            _date_seg = _seg
            break
        if not _batch_seg and _walk != _abs:
            _batch_seg = _seg.replace("_", "").replace("-", "")
        elif not _batch_seg:
            _batch_seg = _seg.replace("_", "").replace("-", "")
        _parent = os.path.dirname(_walk)
        if _parent == _walk:
            break
        _walk = _parent
        
    _stem = _date_seg if _date_seg else date_label
    if _batch_seg and not _batch_seg.isdigit():
        _stem = f"{_stem}_{_batch_seg}"
        
    out_csv = os.path.join(target_dir, f"{_stem}_results.csv")
    out_md  = os.path.join(target_dir, f"{_stem}_results.md")
    out_edge_cases = os.path.join(target_dir, f"{_stem}_edge_cases.txt")
    out_stats = os.path.join(target_dir, f"{_stem}_stats.json")

    with open(out_csv, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(csv_rows)

    with open(out_md, "w") as f:
        f.write(f"# License Plate Extraction Results ({date_label})\n\n")
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
        for r in csv_rows:
            f.write("| " + " | ".join(str(x) for x in r) + " |\n")

    print(f"\n✓ Done! {len(csv_rows)} plates written to {out_csv}")
    
    return out_csv, out_md, out_edge_cases, out_stats


def write_edge_cases(edge_case_rows: list, out_path: str, date_processed: str):
    """Write edge-case flags (e.g. format issues, Pro-corrected) to a text summary."""
    if not edge_case_rows:
        return
        
    seen_ec: set = set()
    deduped_ec = []
    for row in edge_case_rows:
        if row[0] not in seen_ec:
            seen_ec.add(row[0])
            deduped_ec.append(row)
            
    with open(out_path, "w") as f:
        f.write(f"Edge Cases — {date_processed}  ({len(deduped_ec)} plates flagged)\n")
        f.write("=" * 70 + "\n\n")
        for row in deduped_ec:
            plate, state, make, model, color, match, reg, flags = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
            vehicle = " ".join(x for x in [make, model, color] if x) or "unknown vehicle"
            f.write(f"[{plate}]  {state}  —  {flags}\n")
            f.write(f"  Vehicle:  {vehicle}\n")
            f.write(f"  Match:    {match or 'n/a'}\n")
            f.write(f"  Reg:      {reg or 'not found'}\n")
            f.write("\n")
    print(f"✓ {len(deduped_ec)} edge cases written to {out_path}")


def write_stats(stats_json: dict, out_path: str):
    """Save pipeline runtime numbers and Gemini inference costs to JSON."""
    with open(out_path, "w") as f:
        json.dump(stats_json, f, indent=2)
    print(f"✓ Stats written to {out_path}")


def print_stats_summary(stats_json: dict):
    """Print the final stats report to stdout."""
    print("\n" + "="*60)
    print("BATCH RUN STATISTICS")
    print("="*60)
    
    run_elapsed = stats_json.get("run_elapsed_seconds", 0)
    print(f"  Run time          : {int(run_elapsed // 60)}m {int(run_elapsed % 60)}s")
    print(f"  Locations         : {stats_json.get('location', '(not detected)')}")
    print(f"  Date              : {stats_json.get('date_processed', '(not parsed)')}")
    print()
    print("  ── Input ──────────────────────────────────")
    print(f"  Videos processed  : {stats_json.get('total_videos', 0)}")
    
    videos = stats_json.get("videos", [])
    for i, v in enumerate(videos):
        _name = v.get("name", "")
        _dur = v.get("duration_seconds", 0)
        _sz = v.get("size_mb", 0)
        print(f"    [{i+1}] {_name:50s}  {_dur:6.1f}s  {_sz:6.1f} MB")
        
    print("  ── Plates ─────────────────────────────────")
    print(f"  Total unique      : {stats_json.get('total_unique_plates', 0)}")
    print()
    print("  ── Registration ───────────────────────────")
    _reg_pct = stats_json.get("registration_pct", 0)
    print(f"  Found             : {stats_json.get('reg_found', 0)} ({_reg_pct:.0f}%)")
    print(f"  Not found         : {stats_json.get('reg_not_found', 0)}")
    if stats_json.get("registration_throttled"):
        print(f"  Throttled (retry) : {stats_json.get('registration_throttled')}  ← lookup incomplete")
    print(f"  Match=Y           : {stats_json.get('match_y', 0)}")
    print(f"  Match=N           : {stats_json.get('match_n', 0)}")
    print(f"  Pro escalations   : {stats_json.get('gemini_pro_calls', 0)}  (corrections: {stats_json.get('pro_corrections', 0)})")
    
    _sub_att = stats_json.get("ocr_sub_attempts", 0)
    _sub_hits = stats_json.get("ocr_sub_hits", 0)
    _sub_fb = stats_json.get("ocr_sub_fallbacks", 0)
    print(f"  OCR substitution  : {_sub_att} attempts, {_sub_hits} hits, {_sub_fb} fallbacks")
    print()
    print("  ── ICE ─────────────────────────────────────")
    print(f"  Confirmed ICE (Y) : {stats_json.get('ice_y', 0)}")
    print(f"  Highly Susp. (HS) : {stats_json.get('ice_hs', 0)}")
    print(f"  Not found (N)     : {stats_json.get('ice_n', 0)}")
    print()
    print("  ── Cost Estimator ──────────────────────────")
    print(f"  Gemini Flash video: ${stats_json.get('cost_flash_video', 0):.4f}")
    print(f"  Gemini Flash image: ${stats_json.get('cost_flash_image', 0):.4f}")
    print(f"  Gemini Pro image  : ${stats_json.get('cost_pro', 0):.4f}")
    print(f"  ─────────────────────────────────────────")
    print(f"  TOTAL (Gemini)    : ${stats_json.get('cost_total_gemini', 0):.4f}")
    print(f"  Cost / plate      : ${stats_json.get('cost_per_plate', 0):.4f}")
    
    alpr_failures = stats_json.get("alpr_failures", [])
    if alpr_failures:
        print("\n  ── ALPR Token Failures ────────────────────")
        for msg in alpr_failures:
            print(f"  * {msg}")
        print("  Please check quota at platerecognizer.com")
        
    print("="*60)
