"""Text normalization for AI guardrail processing.

Normalizes text before running guardrail validators to handle:
- Unicode normalization (NFKC)
- Emoji removal/replacement
- Encoding fixes
- Whitespace normalization
"""

import re
import unicodedata


# Emoji unicode ranges covering major emoji blocks
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Misc Symbols & Pictographs
    "\U0001F680-\U0001F6FF"  # Transport & Map
    "\U0001F1E0-\U0001F1FF"  # Flags (iOS)
    "\U00002702-\U000027B0"  # Dingbats
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols & Pictographs
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols & Pictographs Extended-A
    "\U00002600-\U000026FF"  # Misc Symbols
    "\U0000FE00-\U0000FE0F"  # Variation Selectors
    "\U0000200D"             # Zero Width Joiner
    "\U00002B50"             # Star
    "\U00002B55"             # Circle
    "\U000023F0-\U000023FA"  # Misc technical symbols
    "\U0000231A-\U0000231B"  # Watch/Hourglass
    "]+",
    flags=re.UNICODE,
)

# Whitespace normalization (multiple spaces, tabs, etc.)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize text for guardrail processing.

    Steps:
    1. Unicode NFKC normalization (canonical decomposition + compatibility composition)
    2. Emoji removal (replaced with single space)
    3. Whitespace normalization (collapse multiple spaces/tabs/newlines)
    4. Strip leading/trailing whitespace

    Args:
        text: Raw input text.

    Returns:
        Normalized text ready for guardrail validator matching.
    """
    if not text:
        return text

    # 1. Unicode NFKC normalization — handles fullwidth chars, ligatures, etc.
    text = unicodedata.normalize("NFKC", text)

    # 2. Remove emoji (replace with space to avoid word joining)
    text = _EMOJI_PATTERN.sub(" ", text)

    # 3. Normalize whitespace (collapse runs of whitespace to single space)
    text = _WHITESPACE_RE.sub(" ", text)

    # 4. Strip
    text = text.strip()

    return text


def remove_diacritics(text: str) -> str:
    """Remove diacritical marks from text for fuzzy matching.

    Useful for matching slurs/banned words that use accented characters
    to evade detection (e.g., "slür" -> "slur").
    """
    # Decompose to NFD (separates base chars from combining marks)
    decomposed = unicodedata.normalize("NFD", text)
    # Remove combining marks (category "Mn" = Mark, Nonspacing)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
