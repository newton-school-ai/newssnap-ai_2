"""NewsSnap AI - Text Processing Utilities."""

import re

from bs4 import BeautifulSoup

# Tags commonly used for ads, navigation, sidebars, footers — removed during cleaning
_NOISE_TAGS = [
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "button",
    "iframe",
    "noscript",
    "figure",  # captions-only figures can be noisy; body text is kept
]

# CSS class/id substrings that signal ad or navigation content
_NOISE_CLASS_PATTERNS = re.compile(
    r"(ad|ads|advert|advertisement|promo|sidebar|widget|related|newsletter"
    r"|social|share|comment|footer|header|nav|menu|banner|popup|modal|cookie"
    r"|breadcrumb|pagination|tag-list|author-bio|recommended|trending)",
    re.IGNORECASE,
)


def _is_noisy_element(tag) -> bool:
    """Return True if the tag's class or id looks like an ad/navigation block."""
    for attr in ("class", "id"):
        value = tag.get(attr, "")
        if isinstance(value, list):
            value = " ".join(value)
        if _NOISE_CLASS_PATTERNS.search(value):
            return True
    return False


def clean_html(html_str: str) -> str:
    """
    Remove script/style/nav/ad elements from an HTML string.
    Returns cleaned HTML (still has tags but noisy elements stripped).
    """
    if not html_str:
        return ""
    soup = BeautifulSoup(html_str, "html.parser")

    # Remove structural noise tags
    for element in soup(_NOISE_TAGS):
        element.decompose()

    # Remove elements whose class/id looks like ads or navigation
    for element in soup.find_all(True):
        if _is_noisy_element(element):
            element.decompose()

    return str(soup)


def extract_text(html_str: str) -> str:
    """
    Extract plain text from an HTML string, stripping all tags.
    Noise elements (ads, nav, scripts) are removed first.
    """
    if not html_str:
        return ""
    cleaned = clean_html(html_str)
    soup = BeautifulSoup(cleaned, "html.parser")
    text = soup.get_text(separator=" ")
    return normalize_whitespace(text)


def normalize_whitespace(text: str) -> str:
    """Replace multiple whitespace characters/newlines with a single space and trim."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def word_count(text: str) -> int:
    """Return the number of words in a plain-text string."""
    if not text:
        return 0
    return len(text.split())


def is_incomplete(body: str, min_words: int = 100) -> bool:
    """Return True when the article body is below the minimum word threshold."""
    return word_count(body) < min_words
