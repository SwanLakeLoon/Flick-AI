"""
Flick AI — Prompt Loader
=========================
Loads prompt templates from the prompts/ directory and the
state-identifier knowledge base.
"""

import os


# ── Prompt directory ───────────────────────────────────────────────────────────
_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")


def load_prompt(filename: str, **kwargs) -> str:
    """Load a prompt template from prompts/ and interpolate kwargs."""
    path = os.path.join(_PROMPTS_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file not found: {path}")
    with open(path) as f:
        template = f.read()
    # Simple replace to avoid .format() choking on JSON curly braces in prompts
    for k, v in kwargs.items():
        template = template.replace(f"{{{k}}}", str(v))
    return template


# ── State Identifier Knowledge Base ────────────────────────────────────────────
_STATE_KNOWLEDGE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "state-identifier-prompt.txt"
)

if os.path.exists(_STATE_KNOWLEDGE_FILE):
    with open(_STATE_KNOWLEDGE_FILE) as _f:
        STATE_KNOWLEDGE = _f.read().strip()
else:
    STATE_KNOWLEDGE = (
        "Identify the issuing US state. **Crucially, look at the top 10% to 15% of the license plate**, as this is where the state name is almost always explicitly printed. "
        "If you can read the state name, use that as your primary identifier. "
        "Use plate color, design, symbols, slogans, and logos as secondary clues. "
        "MN = blue, white, blue horizontal bands; WI = blue/white with badger; "
        "IA = blue sky/red barn; SD = Mount Rushmore; IL = Lincoln silhouette."
    )
