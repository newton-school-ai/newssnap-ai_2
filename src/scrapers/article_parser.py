"""NewsSnap AI - Article Parser and Content Normalizer (Issue 7).

Extracts clean, structured article data from raw HTML regardless of source format:
- Clean body text (no HTML tags, ads, or navigation)
- Lead image (og:image → first large img → fallback)
- Category detection from URL patterns and content keywords (all 19 categories)
- Language detection against the expected source language
- Metadata: author, publish_time, title
- Flags articles with < 100 words as incomplete
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.utils.image_utils import pick_best_image
from src.utils.text_utils import extract_text, is_incomplete, normalize_whitespace, word_count

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category detection maps (URL path keywords → category)
# ---------------------------------------------------------------------------

_URL_CATEGORY_MAP: dict[str, str] = {
    # Core
    "national": "national",
    "india": "national",
    "bharat": "national",
    "desh": "national",
    "international": "international",
    "world": "international",
    "global": "international",
    "politics": "politics",
    "election": "politics",
    "parliament": "politics",
    "rajniti": "politics",
    "business": "business",
    "economy": "business",
    "startup": "business",
    "corporate": "business",
    "market": "finance",
    "finance": "finance",
    "stocks": "finance",
    "sensex": "finance",
    "crypto": "finance",
    "sports": "sports",
    "cricket": "sports",
    "football": "sports",
    "ipl": "sports",
    "khel": "sports",
    # Tech & science
    "technology": "technology",
    "tech": "technology",
    "gadgets": "technology",
    "ai": "technology",
    "science": "science",
    "space": "science",
    "isro": "science",
    "automobile": "automobile",
    "auto": "automobile",
    "cars": "automobile",
    "bikes": "automobile",
    # Society
    "education": "education",
    "exam": "education",
    "results": "education",
    "health": "health",
    "fitness": "health",
    "disease": "health",
    "entertainment": "entertainment",
    "bollywood": "entertainment",
    "ott": "entertainment",
    "movies": "entertainment",
    "lifestyle": "lifestyle",
    "food": "lifestyle",
    "travel": "lifestyle",
    "fashion": "lifestyle",
    # India specific
    "crime": "crime",
    "court": "crime",
    "scam": "crime",
    "environment": "environment",
    "climate": "environment",
    "pollution": "environment",
    "wildlife": "environment",
    "jobs": "jobs",
    "sarkari": "jobs",
    "recruitment": "jobs",
    "naukri": "jobs",
    "defence": "defence",
    "military": "defence",
    "army": "defence",
    "realestate": "real_estate",
    "property": "real_estate",
    "housing": "real_estate",
    "opinion": "opinion",
    "editorial": "opinion",
    "analysis": "opinion",
    "column": "opinion",
}

# Keywords that appear in article body → category (used as fallback after URL matching)
_KEYWORD_CATEGORY_MAP: dict[str, list[str]] = {
    "national": ["India", "government", "Modi", "BJP", "Congress", "Lok Sabha", "Rajya Sabha", "state government"],
    "international": ["United Nations", "NATO", "US President", "China", "Russia", "Europe", "foreign affairs"],
    "politics": ["election", "vote", "party", "parliament", "chief minister", "prime minister", "political"],
    "business": ["startup", "IPO", "merger", "acquisition", "revenue", "profit", "CEO", "quarter earnings"],
    "finance": ["Sensex", "Nifty", "RBI", "repo rate", "mutual fund", "stock market", "cryptocurrency", "rupee"],
    "sports": ["cricket", "IPL", "football", "Olympics", "match", "wicket", "goal", "medal", "tournament"],
    "technology": ["AI", "artificial intelligence", "smartphone", "app", "software", "Google", "Apple", "Meta"],
    "science": ["ISRO", "NASA", "space mission", "research", "discovery", "satellite", "experiment"],
    "automobile": ["car", "bike", "EV", "electric vehicle", "launch", "mileage", "horsepower"],
    "education": ["CBSE", "NEET", "JEE", "university", "exam", "result", "scholarship", "NEP"],
    "health": ["hospital", "disease", "vaccine", "medicine", "doctor", "health ministry", "WHO", "cancer"],
    "entertainment": ["Bollywood", "actor", "actress", "film", "movie", "OTT", "Netflix", "web series"],
    "lifestyle": ["recipe", "fashion", "travel", "wellness", "restaurant", "diet", "beauty"],
    "crime": ["arrested", "FIR", "court", "verdict", "murder", "scam", "cybercrime", "police"],
    "environment": ["climate change", "pollution", "forest", "wildlife", "disaster", "flood", "earthquake"],
    "jobs": ["sarkari naukri", "recruitment", "vacancy", "government job", "placement", "hiring"],
    "defence": ["army", "navy", "air force", "soldier", "border", "defence ministry", "weapon"],
    "real_estate": ["property", "housing", "RERA", "apartment", "flat", "real estate", "home loan"],
    "opinion": ["editorial", "opinion", "analysis", "column", "perspective", "commentary"],
}

# Supported language codes and their common Unicode script ranges
_LANGUAGE_SCRIPT_MAP: dict[str, re.Pattern] = {
    "hi": re.compile(r"[\u0900-\u097F]"),  # Devanagari (Hindi)
    "ta": re.compile(r"[\u0B80-\u0BFF]"),  # Tamil
    "te": re.compile(r"[\u0C00-\u0C7F]"),  # Telugu
    "kn": re.compile(r"[\u0C80-\u0CFF]"),  # Kannada
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ScrapedArticle:
    """Represents an article extracted from a scraper before database insertion."""

    title: str
    body: str
    source_url: str
    publish_time: datetime
    category: str
    image_url: Optional[str] = None
    author: Optional[str] = None
    language: Optional[str] = None
    is_incomplete: bool = False
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ArticleParser
# ---------------------------------------------------------------------------


class ArticleParser:
    """
    Parses and normalizes raw HTML articles into :class:`ScrapedArticle` objects.

    Usage::

        parser = ArticleParser()
        article = parser.parse(html=raw_html, url="https://example.com/article",
                               expected_language="en")
    """

    def parse(
        self,
        html: str,
        url: str,
        expected_language: Optional[str] = "en",
        fallback_image_url: Optional[str] = None,
        fallback_publish_time: Optional[datetime] = None,
        fallback_category: Optional[str] = None,
    ) -> ScrapedArticle:
        """
        Parse a raw HTML page into a :class:`ScrapedArticle`.

        Args:
            html: Raw HTML content of the article page.
            url: Canonical URL of the article (used for category detection and image resolution).
            expected_language: Language code expected for this source (e.g. "en", "hi").
            fallback_image_url: Image URL already discovered by a prior step (e.g. RSS enclosure).
            fallback_publish_time: Publish time if the HTML doesn't contain one.
            fallback_category: Category to use if detection fails.

        Returns:
            A :class:`ScrapedArticle` with all extracted fields populated.
        """
        soup = BeautifulSoup(html, "html.parser")

        title = self._extract_title(soup)
        body = self._extract_body(html)
        image_url = pick_best_image(html, base_url=url, fallback_url=fallback_image_url)
        author = self._extract_author(soup)
        publish_time = self._extract_publish_time(soup) or fallback_publish_time or datetime.now(timezone.utc)
        language = self._detect_language(body, expected_language)
        category = self._detect_category(url, body) or fallback_category or "national"
        incomplete = is_incomplete(body)
        tags = self._extract_tags(soup)

        if incomplete:
            logger.warning(f"Article flagged as incomplete ({word_count(body)} words): {url}")

        return ScrapedArticle(
            title=title,
            body=body,
            source_url=url,
            publish_time=publish_time.replace(tzinfo=None),
            category=category,
            image_url=image_url,
            author=author,
            language=language,
            is_incomplete=incomplete,
            tags=tags,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract the article title: og:title > <title> > first <h1>."""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return normalize_whitespace(og_title["content"])

        if soup.title and soup.title.string:
            return normalize_whitespace(soup.title.string)

        h1 = soup.find("h1")
        if h1:
            return normalize_whitespace(h1.get_text())

        return ""

    def _extract_body(self, html: str) -> str:
        """Extract clean plain-text body from article HTML."""
        soup = BeautifulSoup(html, "html.parser")

        # Prefer <article> element if present
        article_tag = soup.find("article")
        if article_tag:
            return extract_text(str(article_tag))

        # Try common article container classes/ids
        for selector in ("div.article-body", "div.story-content", "div.content-body", "div.post-content"):
            tag_name, _, class_name = selector.partition(".")
            container = soup.find(tag_name, class_=class_name)
            if container:
                return extract_text(str(container))

        # Fall back to full page extraction with noise removed
        return extract_text(html)

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract author name from meta tags or byline elements."""
        # JSON-LD author
        for tag in soup.find_all("meta", attrs={"name": re.compile(r"author", re.I)}):
            if tag.get("content"):
                return normalize_whitespace(tag["content"])

        # og:article:author
        og_author = soup.find("meta", property="article:author")
        if og_author and og_author.get("content"):
            return normalize_whitespace(og_author["content"])

        # Common byline elements
        for selector in (".author", ".byline", "[itemprop='author']", ".reporter"):
            tag = soup.select_one(selector)
            if tag:
                text = normalize_whitespace(tag.get_text())
                if text:
                    return text

        return None

    def _extract_publish_time(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract article publish date from meta/time tags."""
        # Try standard meta properties
        for prop in ("article:published_time", "og:published_time", "datePublished"):
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                dt = self._parse_datetime(tag["content"])
                if dt:
                    return dt

        # <time> element with datetime attribute
        time_tag = soup.find("time", attrs={"datetime": True})
        if time_tag:
            dt = self._parse_datetime(time_tag["datetime"])
            if dt:
                return dt

        return None

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        """Try several common date formats and return a UTC datetime."""
        value = value.strip()
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return None

    def _detect_language(self, body: str, expected: Optional[str]) -> Optional[str]:
        """
        Verify or detect article language.

        - For Hindi/Tamil/Telugu/Kannada: check Unicode script presence.
        - For English: use langdetect if available, otherwise trust expected.
        - Logs a warning when the detected language differs from expected.
        """
        if not body:
            return expected

        # Script-based detection for Indian languages
        for lang_code, pattern in _LANGUAGE_SCRIPT_MAP.items():
            if pattern.search(body):
                detected = lang_code
                if expected and detected != expected:
                    logger.warning(f"Language mismatch: expected={expected}, detected={detected}")
                return detected

        # For Latin-script languages try langdetect
        try:
            from langdetect import detect  # type: ignore[import]

            detected = detect(body[:2000])
            if expected and detected != expected:
                logger.warning(f"Language mismatch: expected={expected}, detected={detected}")
            return detected
        except Exception:
            pass

        return expected

    def _detect_category(self, url: str, body: str) -> Optional[str]:
        """
        Detect article category in two passes:
          1. URL path segments (fast, high-precision)
          2. Body keyword matching (fallback)
        """
        # Pass 1: URL path
        path = urlparse(url).path.lower()
        # Normalise separators
        segments = re.split(r"[/\-_]", path)
        for segment in segments:
            if segment in _URL_CATEGORY_MAP:
                return _URL_CATEGORY_MAP[segment]

        # Pass 2: keyword matching in body
        body_lower = body.lower()
        best_category: Optional[str] = None
        best_count = 0
        for category, keywords in _KEYWORD_CATEGORY_MAP.items():
            count = sum(1 for kw in keywords if kw.lower() in body_lower)
            if count > best_count:
                best_count = count
                best_category = category

        return best_category if best_count >= 2 else None

    def _extract_tags(self, soup: BeautifulSoup) -> list[str]:
        """Extract article tags/keywords from meta tags and tag elements."""
        tags: list[str] = []

        # keywords meta tag
        kw_tag = soup.find("meta", attrs={"name": re.compile(r"keywords", re.I)})
        if kw_tag and kw_tag.get("content"):
            for kw in kw_tag["content"].split(","):
                kw = kw.strip()
                if kw:
                    tags.append(kw)

        # article:tag meta
        for tag in soup.find_all("meta", property="article:tag"):
            if tag.get("content"):
                tags.append(tag["content"].strip())

        return list(dict.fromkeys(tags))  # deduplicate while preserving order
