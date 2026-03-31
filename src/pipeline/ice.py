"""
Flick AI — ICE Lookup
=====================
Pass 6: Queries defrostmn.net for ICE (Immigration and Customs Enforcement) hits.
"""

import json
import urllib.request
import urllib.parse


DEFROST_API_BASE = "https://defrostmn.net/plates/lookup"
DEFROST_PASSWORD = "bCBEYZbpA3"


def lookup_ice(plate: str) -> str:
    """Query defrostmn.net for a single plate and return 'Y', 'HS', or 'N'.

    Y  — exact match with status 'Confirmed ICE'
    HS — exact match with status 'Highly suspected ICE'
    N  — no exact match
    """
    clean = plate.replace(" ", "").replace("-", "").upper()
    params = urllib.parse.urlencode({"q": clean, "password": DEFROST_PASSWORD})
    url = f"{DEFROST_API_BASE}?{params}"
    headers = {
        "Accept": "application/json",
        "Origin": "https://defrostmn.net",
        "Referer": "https://defrostmn.net/plate-check/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        matches = data.get("matches", [])
        exact = [m for m in matches if m.get("similarity_score", 0) == 1]
        if not exact:
            return "N"
        status = (exact[0].get("status") or "").strip()
        if status == "Confirmed ICE":
            return "Y"
        elif status == "Highly suspected ICE":
            return "HS"
        else:
            return "N"
    except Exception as e:
        print(f"  [ICE lookup error] {plate}: {e}")
        return "N"
