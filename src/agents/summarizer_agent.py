"""NewsSnap AI - LLM Summarizer Agent (Issue 11).

Compresses 500-2000 word news articles into crisp 60-80 word summaries using Groq LLM:
- Category-aware prompts (finance = data-heavy, sports = score-focused, politics = quote-focused)
- Quality validation: 60-80 words, key facts preserved, no clickbait language
- Retry logic: up to 2 retries with tighter prompts if quality check fails
- Source attribution in metadata (not injected into the summary text)
- Batch summarization for efficiency
- English and Hindi language detection and support
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Clickbait patterns to detect and reject
# ---------------------------------------------------------------------------
CLICKBAIT_PATTERNS = [
    r"\byou won't believe\b",
    r"\bshocking\b",
    r"\bblew.*mind\b",
    r"\bwhat happened next\b",
    r"\bthis is why\b",
    r"\bsecret\b",
    r"\b\d+ reasons\b",
    r"\bmust[\s-]?see\b",
    r"\bviral\b",
    r"\bbreaking!!!+\b",
    r"\bOMG\b",
    r"\bwow\b",
    r"\bunbelievable\b",
]

# ---------------------------------------------------------------------------
# Category-specific prompt modifiers
# ---------------------------------------------------------------------------
CATEGORY_PROMPT_STYLES: Dict[str, str] = {
    "finance": (
        "Focus on key financial figures, market movements, numbers, percentages, and their economic implications."
    ),
    "business": ("Focus on company names, deal values, strategic implications, and market impact."),
    "sports": ("Focus on scores, players, teams, match results, and tournament standings."),
    "politics": ("Include key quotes, decision-makers, policy changes, and their immediate political implications."),
    "technology": ("Focus on the product or innovation, company behind it, and its practical impact on users."),
    "health": ("Focus on health findings, affected populations, expert advice, and actionable insights."),
    "science": ("Focus on the discovery, research institution, scientific significance, and broader implications."),
    "crime": ("Focus on the incident, key parties involved, location, and legal proceedings."),
    "international": ("Focus on countries involved, key decision-makers, geopolitical implications."),
    "national": ("Focus on Indian context, government bodies, affected citizens, and policy outcomes."),
}
DEFAULT_STYLE = "Be factual, specific, and objective. Preserve key who/what/when/where/why facts."


@dataclass
class SummaryResult:
    """Result of a summarization operation."""

    summary: str
    word_count: int
    language: str
    category: str
    retries: int
    quality_passed: bool
    source_attribution: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SummarizerAgent:
    """LLM-based news article summarizer using Groq API.

    Uses category-aware prompts and quality validation with retry logic
    to produce crisp 60-80 word factual summaries.
    """

    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        model: Optional[str] = None,
        min_words: int = 60,
        max_words: int = 80,
        max_retries: int = 2,
    ):
        # Lazy import settings to allow test overrides
        from src.config.settings import settings

        self.api_key = groq_api_key or settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL
        self.min_words = min_words
        self.max_words = max_words
        self.max_retries = max_retries
        self._client = None

    @property
    def client(self):
        """Lazy-initialize Groq client."""
        if self._client is None:
            from groq import Groq

            if self.api_key and self.api_key != "your_groq_api_key_here":
                self._client = Groq(api_key=self.api_key)
            else:
                # Use mock client for testing without real API key
                self._client = self._create_mock_client()
        return self._client

    def _create_mock_client(self):
        """Create a mock Groq client for testing."""
        mock = MagicMock()
        return mock

    # ------------------------------------------------------------------
    # Language Detection
    # ------------------------------------------------------------------

    def detect_language(self, text: str) -> str:
        """Detect language of article text. Returns 'en' or 'hi'."""
        try:
            from langdetect import detect

            lang = detect(text[:500])
            return lang if lang in ("en", "hi") else "en"
        except Exception:
            return "en"

    # ------------------------------------------------------------------
    # Prompt Construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        body: str,
        category: str,
        language: str,
        retry_num: int = 0,
    ) -> str:
        """Build category-aware summarization prompt."""
        style = CATEGORY_PROMPT_STYLES.get(category.lower(), DEFAULT_STYLE)

        lang_instruction = ""
        if language == "hi":
            lang_instruction = "The article is in Hindi. Provide the summary in English. "

        strictness = ""
        if retry_num > 0:
            strictness = (
                f"IMPORTANT: Previous attempt failed quality check. "
                f"You MUST write exactly {self.min_words}-{self.max_words} words. "
                f"Count each word carefully. "
            )

        prompt = (
            f"{strictness}"
            f"{lang_instruction}"
            f"Summarize the following news article in exactly {self.min_words}-{self.max_words} words. "
            f"{style} "
            f"Do NOT use clickbait language. Be factual, specific, and engaging. "
            f"Do NOT include source names in the summary. "
            f"Output ONLY the summary paragraph, nothing else.\n\n"
            f"Article:\n{body[:3000]}"
        )
        return prompt

    # ------------------------------------------------------------------
    # Quality Validation
    # ------------------------------------------------------------------

    def _count_words(self, text: str) -> int:
        """Count words in text."""
        return len(text.split())

    def _has_clickbait(self, text: str) -> bool:
        """Return True if text contains clickbait language."""
        lower = text.lower()
        for pattern in CLICKBAIT_PATTERNS:
            if re.search(pattern, lower):
                return True
        return False

    def _check_key_facts(self, summary: str, body: str) -> int:
        """
        Estimate how many of the 5 W's are present in the summary.
        Returns count (0-5). At least 3 required to pass.
        """
        who_words = re.findall(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b", summary)
        has_who = len(who_words) >= 1

        action_verbs = re.search(
            r"\b(announced|launched|won|defeated|approved|rejected|signed|said|declared|released|introduced)\b",
            summary,
            re.I,
        )
        has_what = bool(action_verbs)

        time_words = re.search(
            r"\b(today|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december|\d{4}|week|month|year)\b",
            summary,
            re.I,
        )
        has_when = bool(time_words)

        location_words = re.search(
            r"\b(india|delhi|mumbai|bengaluru|chennai|kolkata|hyderabad|punjab|gujarat|kerala|pakistan|china|usa|london|new york|parliament|supreme court|lok sabha)\b",
            summary,
            re.I,
        )
        has_where = bool(location_words)

        # Why/impact - check for causal or impact words
        impact_words = re.search(
            r"\b(because|due to|as a result|following|after|amid|in response|to boost|to reduce|to tackle)\b",
            summary,
            re.I,
        )
        has_why = bool(impact_words)

        total = sum([has_who, has_what, has_when, has_where, has_why])
        return total

    def validate_quality(self, summary: str, body: str) -> tuple[bool, str]:
        """
        Validate summary quality. Returns (passed: bool, reason: str).
        Checks: word count range, no clickbait, and key facts present (≥ 3 of 5).
        """
        word_count = self._count_words(summary)

        if word_count < self.min_words:
            return False, f"Too short: {word_count} words (min {self.min_words})"

        if word_count > self.max_words:
            return False, f"Too long: {word_count} words (max {self.max_words})"

        if self._has_clickbait(summary):
            return False, "Contains clickbait language"

        facts_count = self._check_key_facts(summary, body)
        if facts_count < 3:
            return False, f"Too few key facts: {facts_count}/5 (need at least 3)"

        return True, "OK"

    # ------------------------------------------------------------------
    # Core Summarization
    # ------------------------------------------------------------------

    def _call_groq(self, prompt: str) -> str:
        """Call Groq API and return raw summary text."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional news summarizer for an Indian news app. Write crisp, factual summaries.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()

    def summarize(
        self,
        body: str,
        category: str = "national",
        source: Optional[str] = None,
        title: Optional[str] = None,
    ) -> SummaryResult:
        """
        Summarize an article body into a 60-80 word paragraph.

        Args:
            body: Article full text.
            category: Category slug (e.g. 'politics', 'sports', 'finance').
            source: Source name for metadata attribution (not injected into summary).
            title: Optional article title for context.

        Returns:
            SummaryResult with summary text, word count, quality status, and metadata.
        """
        if not body or not body.strip():
            return SummaryResult(
                summary="",
                word_count=0,
                language="en",
                category=category,
                retries=0,
                quality_passed=False,
                source_attribution=source,
                metadata={"error": "Empty article body"},
            )

        language = self.detect_language(body)
        context = f"{title}.\n\n{body}" if title else body

        summary = ""
        quality_passed = False
        quality_reason = ""
        retries = 0

        for attempt in range(self.max_retries + 1):
            try:
                prompt = self._build_prompt(context, category, language, retry_num=attempt)
                summary = self._call_groq(prompt)
                quality_passed, quality_reason = self.validate_quality(summary, body)

                if quality_passed:
                    break

                retries = attempt + 1
                logger.warning(f"Quality check failed (attempt {attempt + 1}): {quality_reason}. Retrying...")

            except Exception as e:
                logger.error(f"Groq API error on attempt {attempt + 1}: {e}")
                retries = attempt + 1
                if attempt == self.max_retries:
                    summary = summary or ""
                    quality_passed = False
                    quality_reason = str(e)

        return SummaryResult(
            summary=summary,
            word_count=self._count_words(summary),
            language=language,
            category=category,
            retries=retries,
            quality_passed=quality_passed,
            source_attribution=source,
            metadata={
                "quality_reason": quality_reason,
                "model": self.model,
                "title": title,
            },
        )

    def batch_summarize(
        self,
        articles: List[Dict[str, Any]],
    ) -> List[SummaryResult]:
        """
        Summarize a batch of articles.

        Args:
            articles: List of dicts with keys: 'body', 'category', optionally 'source', 'title'.

        Returns:
            List of SummaryResult objects in the same order.
        """
        results = []
        for art in articles:
            result = self.summarize(
                body=art.get("body", ""),
                category=art.get("category", "national"),
                source=art.get("source"),
                title=art.get("title"),
            )
            results.append(result)
        return results
