"""NewsSnap AI - Language Utilities (Issue 13).

Provides helper utilities for Indian language script validation, language detection,
proper noun preservation, and back-translation quality evaluation.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Set, Tuple

logger = logging.getLogger(__name__)

# Supported Indian languages
SUPPORTED_LANGUAGES: Set[str] = {"en", "hi", "ta", "te", "kn"}

# Unicode ranges for the supported language scripts
SCRIPT_RANGES: Dict[str, Tuple[int, int]] = {
    "hi": (0x0900, 0x097F),  # Devanagari (Hindi, Marathi, etc.)
    "ta": (0x0B80, 0x0BFF),  # Tamil
    "te": (0x0C00, 0x0C7F),  # Telugu
    "kn": (0x0C80, 0x0CFF),  # Kannada
    "en": (0x0020, 0x007E),  # Basic Latin / ASCII
}

SCRIPT_NAMES: Dict[str, str] = {
    "hi": "Devanagari",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "en": "Latin",
}


def get_script_name(lang: str) -> str:
    """Return the name of the script used by the language."""
    return SCRIPT_NAMES.get(lang.lower(), "Unknown")


def validate_script(text: str, expected_lang: str, min_ratio: float = 0.3) -> bool:
    """Validate that text predominantly uses the script of expected_lang.

    Args:
        text: Input string to validate.
        expected_lang: Language code ('en', 'hi', 'ta', 'te', 'kn').
        min_ratio: Minimum ratio of script-specific characters among non-whitespace/punctuation.

    Returns:
        True if the text contains a sufficient ratio of characters in expected script.
    """
    if not text or not text.strip():
        return False

    expected_lang = expected_lang.lower()
    if expected_lang not in SCRIPT_RANGES:
        return False

    if expected_lang == "en":
        # Check Latin / ASCII
        ascii_chars = sum(1 for c in text if c.isascii() and c.isalnum())
        total_alnum = sum(1 for c in text if c.isalnum())
        return (ascii_chars / max(total_alnum, 1)) >= min_ratio

    start, end = SCRIPT_RANGES[expected_lang]
    script_chars = sum(1 for c in text if start <= ord(c) <= end)
    total_alnum = sum(1 for c in text if c.isalnum())

    if total_alnum == 0:
        return False

    ratio = script_chars / total_alnum
    return ratio >= min_ratio


def detect_language(text: str) -> str:
    """Detect language of input text among supported Indian languages.

    Returns language code ('en', 'hi', 'ta', 'te', 'kn').
    """
    if not text or not text.strip():
        return "en"

    # Quick script range frequency check
    counts = {lang: 0 for lang in SCRIPT_RANGES}
    for char in text:
        cp = ord(char)
        for lang, (start, end) in SCRIPT_RANGES.items():
            if lang != "en" and start <= cp <= end:
                counts[lang] += 1
            elif lang == "en" and char.isascii() and char.isalpha():
                counts["en"] += 1

    best_lang = max(counts, key=counts.get)
    if counts[best_lang] > 0:
        return best_lang

    try:
        from langdetect import detect

        detected = detect(text[:500])
        return detected if detected in SUPPORTED_LANGUAGES else "en"
    except Exception:
        return "en"


def extract_proper_nouns_and_numbers(text: str) -> Tuple[Set[str], Set[str]]:
    """Extract numbers and capitalized words (potential proper nouns) from English text.

    Returns:
        (numbers, proper_nouns)
    """
    numbers = set(re.findall(r"\b\d+(?:[\.,]\d+)?%?\b", text))
    # Capitalized tokens not at start of sentence, or capitalized acronyms
    words = re.findall(r"\b[A-Z][A-Za-z0-9\.]*\b", text)
    proper_nouns = set(words)
    return numbers, proper_nouns


def calculate_semantic_overlap(text1: str, text2: str) -> float:
    """Calculate token overlap / similarity ratio between two texts in the same language.

    Used for back-translation quality evaluation.
    Returns float score between 0.0 and 1.0.
    """
    if not text1 or not text2:
        return 0.0

    # Tokenize words into lower-case sets
    tokens1 = set(re.findall(r"\w+", text1.lower()))
    tokens2 = set(re.findall(r"\w+", text2.lower()))

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)

    # Jaccard index with length penalty
    jaccard = len(intersection) / len(union)

    # Dice coefficient (more lenient for text comparison)
    dice = 2 * len(intersection) / (len(tokens1) + len(tokens2))

    return round(max(jaccard, dice), 4)
