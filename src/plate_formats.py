import re

# Format patterns per state — covers standard passenger, truck, vanity, and common specialty series.
# Each state has a list of regex patterns.  A plate is "valid" if it matches ANY pattern in the list.
# A generous catch-all is included for vanity/personalized plates (most states allow 2-7 alphanumeric
# characters with at least one letter).
PLATE_FORMATS = {
  # ── A ─────────────────────────────────────────────────────────────────────
  "AL": [r"^\d[A-Z0-9]{6}$", r"^[A-Z0-9]{1,7}$"],       # Very loose county-based formats
  "AK": [r"^[A-Z]{3}\d{3}$",                             # Standard ABC123
         r"^[A-Z0-9]{1,7}$"],                             # Vanity
  "AZ": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z][A-Z0-9]{5,6}$",                        # Various specialty
         r"^[A-Z0-9]{1,7}$"],                             # Vanity
  "AR": [r"^\d{3}[A-Z]{3}$",                             # 123ABC
         r"^[A-Z0-9]{1,7}$"],

  # ── C ─────────────────────────────────────────────────────────────────────
  "CA": [r"^\d[A-Z]{3}\d{3}$",                           # 1ABC234
         r"^[A-Z0-9]{2,7}$"],                             # Vanity (very common in CA)
  "CO": [r"^[A-Z]{3}[A-Z0-9]{3,4}$",                    # ABC123, ABCD12
         r"^[A-Z0-9]{1,7}$"],
  "CT": [r"^[A-Z]{2}\d{5}$",                             # AB12345
         r"^\d{2}[A-Z]{4}$",                             # 12ABCD
         r"^\d[A-Z]{2}\d{4}$",                           # 1AB2345
         r"^[A-Z0-9]{1,7}$"],

  # ── D ─────────────────────────────────────────────────────────────────────
  "DE": [r"^\d{1,6}$",                                   # Pure numeric up to 6 digits
         r"^[A-Z0-9]{1,7}$"],
  "DC": [r"^[A-Z]{2}\d{4}$",                             # AB1234
         r"^[A-Z0-9]{1,7}$"],

  # ── F ─────────────────────────────────────────────────────────────────────
  "FL": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z]{4}\d{2}$",                             # ABCD12
         r"^[A-Z]{3}[A-Z0-9]{3}$",                      # ABC1D2
         r"^[A-Z0-9]{1,7}$"],

  # ── G ─────────────────────────────────────────────────────────────────────
  "GA": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],

  # ── H ─────────────────────────────────────────────────────────────────────
  "HI": [r"^[A-Z]{3}\d{3}$",                             # ABC123
         r"^[A-Z0-9]{1,7}$"],

  # ── I ─────────────────────────────────────────────────────────────────────
  "ID": [r"^\d[A-Z]\d{4}$",                              # 1A1234  (county prefix)
         r"^[A-Z]\d{5}$",                                # A12345
         r"^[A-Z]{2}\d{4}$",                             # AB1234
         r"^[A-Z0-9]{1,7}$"],
  "IL": [r"^[A-Z]{2}\d{5}$",                             # AB12345
         r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z]\d{5,6}$",                              # P509722, A595268 (government/specialty)
         r"^\d{5,7}$",                                   # All-numeric plates (5-7 digits only)
         r"^\d{4,6}[A-Z]$",                              # B-Truck plates (e.g. 71615G)
         r"^[A-Z0-9]{1,7}$"],
  "IN": [r"^\d{3}[A-Z]{3}$",                             # 123ABC
         r"^[A-Z]{3}\d{3}$",                             # ABC123
         r"^[A-Z0-9]{1,7}$"],
  "IA": [r"^[A-Z]{3}\d{3}$",                             # ABC123  (standard county-based)
         r"^[A-Z]{3}\d{4}$",                             # ABC1234 (newer series)
         r"^\d{3}[A-Z]{2}\d$",                           # 123AB4  (older format)
         r"^\d{3}[A-Z]{3}$",                             # 123ABC  (county truck / older)
         r"^\d[A-Z]{2}\d{3}$",                           # 1AB234  (mixed)
         r"^[A-Z0-9]{2,7}$"],                            # Vanity up to 7 chars

  # ── K ─────────────────────────────────────────────────────────────────────
  "KS": [r"^\d{3}[A-Z]{3}$",                             # 123ABC
         r"^[A-Z0-9]{1,7}$"],
  "KY": [r"^\d{3}[A-Z]{3}$",                             # 123ABC
         r"^[A-Z0-9]{1,7}$"],

  # ── L ─────────────────────────────────────────────────────────────────────
  "LA": [r"^[A-Z]{3}\d{3}$",                             # ABC123
         r"^[A-Z0-9]{1,7}$"],

  # ── M ─────────────────────────────────────────────────────────────────────
  "ME": [r"^\d{4}[A-Z]{2}$",                             # 1234AB
         r"^[A-Z0-9]{1,7}$"],
  "MD": [r"^\d[A-Z]{2}\d{4}$",                           # 1AB1234
         r"^[A-Z0-9]{1,7}$"],
  "MA": [r"^\d[A-Z]{2}\d{3}$",                           # 1AB234
         r"^\d{3}[A-Z]{2}\d$",                           # 123AB4
         r"^[A-Z0-9]{1,7}$"],
  "MI": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],
  "MN": [r"^[A-Z]{3}\d{3}$",                             # ABC123  (standard passenger since June 2008)
         r"^[A-Z]{3}\d{4}$",                             # ABC1234 (7-char passenger)
         r"^[Y][A-Z0-9]{5}$",                            # Y-prefix mail-out plates (Dec 2025+)
         r"^\d{3,4}[A-Z]{3}$",                           # 123ABC / 1234ABC — apportioned truck (PRP) / digit-leading
         r"^\d[A-Z]{2}\d{3}$",                           # 1AB234  (older series / digit-leading passenger)
         r"^\d{2}[A-Z]\d{3}$",                           # 12A345  (digit-leading)
         r"^\d[A-Z]\d[A-Z]\d{2}$",                      # 1A2B34  (mixed alphanumeric)
         r"^[A-Z]{2}\d{4}$",                             # AB1234  (2-letter prefix)
         r"^[A-Z]{4}\d{3}$",                             # ABCD123 (7-char specialty)
         r"^[A-Z0-9]{2,7}$"],                            # Vanity/personalized (up to 7 chars, must have ≥1 letter)
  "MS": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],
  "MO": [r"^[A-Z0-9]{2}\d[A-Z]\d[A-Z]$",                # Complex mix
         r"^[A-Z]{2}\d\d[A-Z]$",                        # AB12C
         r"^[A-Z0-9]{6}$",                              # Generic 6-char
         r"^[A-Z0-9]{1,7}$"],
  "MT": [r"^\d{1,2}[A-Z]{1,3}\d{1,4}$",                 # County+prefix+serial
         r"^[A-Z0-9]{1,7}$"],

  # ── N ─────────────────────────────────────────────────────────────────────
  "NE": [r"^\d{1,2}[A-Z0-9]{3,5}$",                     # County prefixes (min 3 suffix chars)
         r"^[A-Z0-9]{1,7}$"],
  "NV": [r"^\d[A-Z]{2}\d{3}$",                           # 1AB234
         r"^\d{3}[A-Z]{2}\d$",                           # 123AB4
         r"^[A-Z0-9]{1,7}$"],
  "NH": [r"^\d{3,7}$",                                   # Pure numeric (3-7 digits)
         r"^\d{4}[A-Z]{2}$",                             # 1234AB
         r"^[A-Z0-9]{1,7}$"],
  "NJ": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z]{3}\d{2}[A-Z]$",                       # ABC12D
         r"^[A-Z0-9]{1,7}$"],
  "NM": [r"^[A-Z]{3}\d{3}$",                             # ABC123
         r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],
  "NY": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,8}$"],                            # Vanity (NY allows up to 8)
  "NC": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],
  "ND": [r"^\d{3}[A-Z]{3}$",                             # 123ABC
         r"^[A-Z0-9]{1,7}$"],

  # ── O ─────────────────────────────────────────────────────────────────────
  "OH": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],
  "OK": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],
  "OR": [r"^\d{3}[A-Z]{3}$",                             # 123ABC
         r"^[A-Z0-9]{1,7}$"],

  # ── P ─────────────────────────────────────────────────────────────────────
  "PA": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],

  # ── R ─────────────────────────────────────────────────────────────────────
  "RI": [r"^\d{3,6}$",                                   # Pure numeric (3-6 digits)
         r"^[A-Z]{2}\d{2,4}$",                          # AB1234
         r"^[A-Z0-9]{1,6}$"],

  # ── S ─────────────────────────────────────────────────────────────────────
  "SC": [r"^[A-Z]{3}\d{3}$",                             # ABC123
         r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],
  "SD": [r"^\d[A-Z]\d{4}$",                              # County-based 1A1234
         r"^\d{2}[A-Z]\d{3}$",                           # 12A345
         r"^[A-Z0-9]{1,7}$"],

  # ── T ─────────────────────────────────────────────────────────────────────
  "TN": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^\d[A-Z]{2}\d{4}$",                           # 1AB2345
         r"^[A-Z0-9]{1,7}$"],
  "TX": [r"^[A-Z]{3}\d{4}$",                             # ABC1234 (newer)
         r"^\d{3}[A-Z]{3}$",                             # 123ABC  (older)
         r"^[A-Z0-9]{1,7}$"],

  # ── U ─────────────────────────────────────────────────────────────────────
  "UT": [r"^[A-Z]\d{2}\d[A-Z]{2}$",                     # A123BC
         r"^[A-Z0-9]{6}$",                              # Generic 6-char
         r"^[A-Z0-9]{1,7}$"],

  # ── V ─────────────────────────────────────────────────────────────────────
  "VT": [r"^[A-Z]{3}\d{3}$",                             # ABC123
         r"^[A-Z0-9]{1,7}$"],
  "VA": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],

  # ── W ─────────────────────────────────────────────────────────────────────
  "WA": [r"^[A-Z]{3}\d{4}$",                             # ABC1234
         r"^[A-Z0-9]{1,7}$"],
  "WV": [r"^\d[A-Z]{2}\d{4}$",                           # 1AB2345
         r"^[A-Z0-9]{1,7}$"],
  "WI": [r"^[A-Z]{3}\d{4}$",                             # ABC1234 (standard passenger 7-char since 2017)
         r"^[A-Z]{3}\d{3}$",                             # ABC123  (6-char passenger/light truck)
         r"^\d{3}[A-Z]{3}$",                             # 123ABC  (older/light truck)
         r"^[A-Z]{2}\d{4}$",                             # AB1234  (light truck series)
         r"^\d{5,6}[A-Z]{1,3}$",                        # 46648AFT (fleet/temp — 5-6 digits + 1-3 letters)
         r"^\d{5,6}[A-Z]$",                              # 12345A  (farm/special)
         r"^[A-Z0-9]{2,7}$"],                            # Vanity up to 7 chars
  "WY": [r"^\d{1,2}\d{3,5}$",                            # County prefix + serial (min 3 serial digits)
         r"^\d{1,2}[A-Z0-9]{3,4}$",                     # County prefix + alphanumeric (min 3 suffix)
         r"^[A-Z0-9]{1,7}$"],
}


# ── Minimum output length ─────────────────────────────────────────────────────
# No US state issues standard passenger plates shorter than 5 chars.
# Plates shorter than this at the output stage are almost always OCR fragments.
MIN_PLATE_OUTPUT_LENGTH = 5

# ── Vanity/generic catch-all patterns to EXCLUDE from strict matching ─────────
# These patterns match virtually any alphanumeric string and provide no
# discriminating signal for state identification.
_VANITY_PATTERNS = {
    r"^[A-Z0-9]{1,7}$",
    r"^[A-Z0-9]{1,8}$",
    r"^[A-Z0-9]{2,7}$",
    r"^[A-Z0-9]{1,6}$",
    r"^[A-Z0-9]{6}$",       # Generic 6-char (UT, MO)
    r"^[A-Z][A-Z0-9]{5,6}$",  # Semi-generic (AZ) — matches any 6-7 char starting with letter
    r"^[A-Z]{3}[A-Z0-9]{3,4}$",  # Semi-generic (CO) — matches any 6-7 char with 3-letter prefix
    r"^[A-Z]{3}[A-Z0-9]{3}$",  # Semi-generic (FL) — matches any 6-char with 3-letter prefix
}

# ── State population rank (approximate registered vehicles, descending) ───────
# Used to sort candidate states so higher-probability states are tried first.
_STATE_POPULATION_RANK = [
    "CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI",
    "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
    "MN", "CO", "SC", "AL", "LA", "KY", "OR", "OK", "CT", "IA",
    "UT", "NV", "AR", "MS", "KS", "NM", "NE", "ID", "WV", "HI",
    "NH", "ME", "MT", "RI", "DE", "SD", "ND", "AK", "DC", "VT", "WY",
]


def is_valid_format(plate: str, state: str) -> bool:
    """
    Return True if `plate` matches any known format for `state`.
    Returns True for unknown states (don't penalise unrecognised codes).
    """
    if not plate or len(plate) < 2:
        return False

    clean_state = state.upper().strip()
    clean_plate = plate.upper().strip()

    patterns = PLATE_FORMATS.get(clean_state)
    if not patterns:
        return True   # Unknown state code — give benefit of the doubt

    return any(re.match(p, clean_plate) for p in patterns)


def get_candidate_states(plate: str, exclude_state: str = "") -> list:
    """
    Test `plate` against every state's STRICT (non-vanity) format patterns.
    Returns a list of state codes where the plate matches a standard-issue
    format, sorted by vehicle registration volume (most populous first).

    Excludes the `exclude_state` from the results (since we already tried it).
    Returns an empty list for plates shorter than 4 chars (likely noise)
    or plates that only match vanity catch-alls.
    """
    if not plate or len(plate) < 4:
        return []

    clean_plate = plate.upper().strip()
    exclude = exclude_state.upper().strip()
    candidates = []

    for state_code, patterns in PLATE_FORMATS.items():
        if state_code == exclude:
            continue
        # Only test strict patterns (skip vanity catch-alls)
        strict_patterns = [p for p in patterns if p not in _VANITY_PATTERNS]
        if any(re.match(p, clean_plate) for p in strict_patterns):
            candidates.append(state_code)

    # Sort by population rank so high-probability states are tried first
    rank_map = {s: i for i, s in enumerate(_STATE_POPULATION_RANK)}
    candidates.sort(key=lambda s: rank_map.get(s, 999))

    return candidates


def is_strict_format(plate: str, state: str) -> bool:
    """
    Return True if `plate` matches a STRICT (non-vanity) format for `state`.
    If state is unknown or empty, falls back to checking all states.
    Does NOT fall back globally when a known state fails — that was allowing
    garbage plates to pass by matching some other state's loose patterns.
    """
    if not plate or len(plate) < 4:
        return False
        
    clean_plate = plate.upper().strip()
    clean_state = (state or "").upper().strip()
    
    if clean_state and clean_state in PLATE_FORMATS:
        # Known state: only check THIS state's strict patterns
        strict_patterns = [p for p in PLATE_FORMATS[clean_state] if p not in _VANITY_PATTERNS]
        return any(re.match(p, clean_plate) for p in strict_patterns)
            
    # Unknown/empty state only: test against all strict formats globally
    for patterns in PLATE_FORMATS.values():
        strict_patterns = [p for p in patterns if p not in _VANITY_PATTERNS]
        if any(re.match(p, clean_plate) for p in strict_patterns):
            return True
            
    return False
