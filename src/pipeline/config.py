"""
Flick AI — Pipeline Configuration
==================================
Central configuration: API keys, Gemini client, ephemeral storage,
color maps, and shared constants.
"""

import os
import re

# ── Persistent Cache Directory ─────────────────────────────────────────────────
# All caches, frames, and splits live here. Persists across runs so the pipeline
# can resume after crashes or network hangs.
EPHEMERAL_DIR = os.path.join(os.getcwd(), ".alpr_cache")
os.makedirs(EPHEMERAL_DIR, exist_ok=True)



# ── .env Loader ────────────────────────────────────────────────────────────────
def _load_config_key(key_name: str) -> str:
    """Read a KEY=value entry from .env (gitignored secrets file)."""
    cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    if os.path.exists(cfg):
        with open(cfg) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key_name}="):
                    return line[len(key_name) + 1:].strip()
    return ""


# ── API Keys ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or _load_config_key("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set.\n"
        "Either export it:  export GEMINI_API_KEY=<your-key>\n"
        "Or add it to .env:  GEMINI_API_KEY=<your-key>"
    )

# ── PlateToVin API Keys (round-robin rotation) ────────────────────────────────
_ptv_raw = os.environ.get("PLATETOVIN_API_KEYS") or _load_config_key("PLATETOVIN_API_KEYS")
PTV_KEYS: list[str] = [k.strip() for k in _ptv_raw.split(",") if k.strip()] if _ptv_raw else []
ptv_key_index = 0  # mutable counter for round-robin rotation
if not PTV_KEYS:
    print("[WARNING] No PlateToVin API keys found. Registration lookups will be limited.")



# ── Gemini Client ──────────────────────────────────────────────────────────────
from google import genai
from google.genai import types as genai_types

client = genai.Client(api_key=GEMINI_API_KEY)


# ── Color Maps ─────────────────────────────────────────────────────────────────
COLOR_NORMALIZE = {
    "dark blue": "BL", "dark navy": "BL", "navy": "BL",
    "dark gray": "GR", "dark grey": "GR", "charcoal": "GR", "graphite": "GR",
    "light gray": "SL", "light grey": "SL",
    "dark green": "GN", "olive": "GN",
    "dark red": "R", "maroon": "R", "burgundy": "R",
    "cream": "TN", "beige": "TN", "champagne": "TN",
    "pearl": "WH", "bright white": "WH",
}

COLOR_MAP = {
    "black": "BK", "tan": "TN", "white": "WH", "silver": "SL",
    "grey": "GR",  "gray": "GR",  "gold": "GD", "blue": "BL",
    "green": "GN", "red": "R",   "orange": "OR", "purple": "PU",
}


def normalize_color(raw: str) -> str:
    """Normalize any Gemini color string to the allowed 2-char codes."""
    if not raw:
        return ""
    raw = raw.lower().strip()
    if raw in COLOR_NORMALIZE:
        return COLOR_NORMALIZE[raw]
    if raw in COLOR_MAP:
        return COLOR_MAP[raw]
    for modifier in ("dark ", "light ", "bright ", "deep "):
        if raw.startswith(modifier):
            stripped = raw[len(modifier):]
            if stripped in COLOR_MAP:
                return COLOR_MAP[stripped]
    return raw.upper()[:2]


# ── Constants ──────────────────────────────────────────────────────────────────
MN_LOGO_DIGIT_RE = re.compile(r'^([A-Z]{2,4})0([0-9]{3})$')
MIN_PLATE_LENGTH = 4
MAX_SEGMENT_SECONDS = 120  # 2 minutes

STATE_CODES = {
    "minnesota": "MN", "georgia": "GA", "colorado": "CO", "wisconsin": "WI",
    "california": "CA", "maryland": "MD", "south dakota": "SD", "utah": "UT",
    "vermont": "VT", "connecticut": "CT", "new mexico": "NM", "illinois": "IL",
    "missouri": "MO", "texas": "TX", "new york": "NY", "florida": "FL",
    "ohio": "OH", "michigan": "MI", "iowa": "IA", "north dakota": "ND",
    "nebraska": "NE", "kansas": "KS", "indiana": "IN",
}


# ── Default Hotel Location ────────────────────────────────────────────────────
_DEFAULT_HOTEL_LOCATION = ""
