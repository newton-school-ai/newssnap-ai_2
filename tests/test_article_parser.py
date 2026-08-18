"""Tests for Article Parser and Content Normalizer (Issue 7).

Acceptance Criteria covered:
  AC1 - Parser extracts clean body text with no HTML tags, ads, or navigation
  AC2 - Lead image extracted from og:image meta tag with fallback to first large image
  AC3 - Category assigned from URL patterns and content keywords (all 19 categories)
  AC4 - Language detection verifies article matches expected source language
  AC5 - Author and publish_time extracted when available
  AC6 - Articles with body < 100 words are flagged as incomplete
  AC7 - Parser works on articles from all configured sources
"""

from datetime import datetime, timezone
from textwrap import dedent

import pytest
from src.scrapers.article_parser import ArticleParser, ScrapedArticle
from src.utils.image_utils import extract_first_large_image, extract_og_image, is_valid_image_url, pick_best_image
from src.utils.text_utils import clean_html, extract_text, is_incomplete, normalize_whitespace, word_count

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parser() -> ArticleParser:
    return ArticleParser()


FULL_ARTICLE_HTML = dedent("""
    <!DOCTYPE html>
    <html>
    <head>
      <title>RBI holds repo rate at 6.5% amid global uncertainty | Business Standard</title>
      <meta property="og:title" content="RBI holds repo rate at 6.5% amid global uncertainty"/>
      <meta property="og:image" content="https://img.example.com/rbi-news.jpg"/>
      <meta property="article:published_time" content="2024-06-10T10:30:00+05:30"/>
      <meta name="author" content="Priya Sharma"/>
      <meta name="keywords" content="RBI, repo rate, monetary policy, inflation"/>
    </head>
    <body>
      <nav>Home | Business | Finance</nav>
      <header>Business Standard Header</header>
      <article>
        <h1>RBI holds repo rate at 6.5% amid global uncertainty</h1>
        <div class="author-bio">By Priya Sharma</div>
        <p>The Reserve Bank of India's Monetary Policy Committee (MPC) voted unanimously on Thursday
           to keep the repo rate unchanged at 6.5 per cent for the seventh consecutive time.
           The decision comes amid persistent global uncertainties and elevated food inflation at home.</p>
        <p>RBI Governor Shaktikanta Das, while addressing the post-policy press conference, said
           the central bank remains focused on the withdrawal of accommodation to ensure that
           inflation progressively aligns with the target of 4 per cent while supporting growth.</p>
        <p>The GDP growth forecast for the current fiscal year was retained at 7.2 per cent,
           while the inflation forecast was revised slightly upward to 4.5 per cent from 4.2 per cent
           due to higher vegetable prices. The stock market responded positively to the announcement,
           with Sensex rising by 400 points and the Nifty crossing the 23,000 mark intra-day.</p>
        <p>Economists and market analysts widely expected the status quo decision. "The RBI is
           navigating a difficult global environment while trying to keep domestic growth on track.
           The rate-hold decision makes complete sense," said Dr. Radhika Rao of DBS Bank.</p>
        <p>Fixed deposit investors and home loan borrowers will get some respite as lending rates
           are unlikely to rise in the near term. Housing finance companies saw their shares rise
           on expectations of stable EMIs continuing into the next quarter.</p>
      </article>
      <aside class="ad">Buy gold now!</aside>
      <footer>Copyright 2024 Business Standard</footer>
      <script>alert('ad')</script>
    </body>
    </html>
""").strip()

SHORT_ARTICLE_HTML = dedent("""
    <html>
    <head>
      <meta property="og:image" content="https://img.example.com/short.jpg"/>
    </head>
    <body>
      <article>
        <p>This is a very short article with only a few words. Not enough content.</p>
      </article>
    </body>
    </html>
""").strip()

HINDI_ARTICLE_HTML = dedent("""
    <html>
    <head>
      <title>भारत में क्रिकेट का जोश</title>
      <meta property="og:image" content="https://img.example.com/cricket.jpg"/>
    </head>
    <body>
      <article>
        <p>भारतीय क्रिकेट टीम ने आज ऑस्ट्रेलिया के खिलाफ शानदार जीत दर्ज की।
           यह मैच मुंबई के वानखेड़े स्टेडियम में खेला गया। भारत ने पहले बल्लेबाजी करते हुए
           300 रन बनाए और फिर गेंदबाजी में ऑस्ट्रेलिया को 250 रन पर ऑलआउट कर दिया।
           रोहित शर्मा ने शतक लगाया और विराट कोहली ने 80 रन की उपयोगी पारी खेली।</p>
      </article>
    </body>
    </html>
""").strip()


# ---------------------------------------------------------------------------
# AC1 - Clean body text (no HTML tags, ads, or navigation)
# ---------------------------------------------------------------------------


class TestBodyExtraction:
    def test_no_html_tags_in_body(self, parser):
        """AC1: Extracted body must not contain any HTML tags."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi-rate")
        assert "<" not in article.body, "Body should not contain HTML tags"
        assert ">" not in article.body, "Body should not contain HTML tags"

    def test_no_nav_or_footer_in_body(self, parser):
        """AC1: Navigation and footer text must be stripped."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi-rate")
        # Nav content
        assert "Home | Business | Finance" not in article.body
        # Footer content
        assert "Copyright 2024 Business Standard" not in article.body

    def test_no_ad_content_in_body(self, parser):
        """AC1: Ad elements (aside.ad) must be stripped from body."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi-rate")
        assert "Buy gold now!" not in article.body

    def test_body_contains_main_content(self, parser):
        """AC1: Core article paragraphs should be present in the body."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi-rate")
        assert "Reserve Bank of India" in article.body
        assert "repo rate" in article.body

    def test_clean_html_removes_script_tags(self):
        """text_utils.clean_html should remove <script> elements."""
        html = "<div><p>Real content</p><script>evil()</script></div>"
        cleaned = clean_html(html)
        assert "evil()" not in cleaned

    def test_extract_text_returns_plain_text(self):
        """text_utils.extract_text should strip all tags."""
        html = "<article><p>Hello <b>World</b></p></article>"
        text = extract_text(html)
        assert "<" not in text
        assert "Hello" in text
        assert "World" in text

    def test_normalize_whitespace_collapses_spaces(self):
        raw = "   Hello   \n\n  World  "
        assert normalize_whitespace(raw) == "Hello World"


# ---------------------------------------------------------------------------
# AC2 - Lead image extraction (og:image → first large img → fallback)
# ---------------------------------------------------------------------------


class TestImageExtraction:
    def test_og_image_extracted(self, parser):
        """AC2: og:image should be the first choice."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi-rate")
        assert article.image_url == "https://img.example.com/rbi-news.jpg"

    def test_og_image_utility_function(self):
        """AC2: extract_og_image helper returns og:image URL."""
        html = '<html><head><meta property="og:image" content="https://cdn.test/img.jpg"/></head></html>'
        assert extract_og_image(html) == "https://cdn.test/img.jpg"

    def test_fallback_to_first_large_image(self):
        """AC2: When no og:image, first large <img> in body is used."""
        html = dedent("""
            <html><body>
            <article>
              <img src="https://cdn.test/article-photo.jpg" width="800" height="450"/>
              <p>Article text</p>
            </article>
            </body></html>
        """)
        url = extract_first_large_image(html, base_url="https://cdn.test")
        assert url == "https://cdn.test/article-photo.jpg"

    def test_small_image_skipped(self):
        """AC2: Images smaller than 200x200 should be skipped."""
        html = dedent("""
            <html><body>
            <img src="https://cdn.test/icon.png" width="16" height="16"/>
            <img src="https://cdn.test/big.jpg" width="600" height="400"/>
            </body></html>
        """)
        url = extract_first_large_image(html)
        assert url == "https://cdn.test/big.jpg"

    def test_fallback_url_used_when_no_image_in_html(self, parser):
        """AC2: fallback_image_url should be returned when HTML has no image."""
        html = "<html><body><article><p>No image here at all, just text content.</p></article></body></html>"
        result = pick_best_image(html, fallback_url="https://fallback.test/img.jpg")
        assert result == "https://fallback.test/img.jpg"

    def test_is_valid_image_url_rejects_logos(self):
        """AC2: Logo/icon URLs should fail validation."""
        assert not is_valid_image_url("https://example.com/images/logo.png")
        assert not is_valid_image_url("https://example.com/1x1.gif")
        assert is_valid_image_url("https://example.com/article-hero.jpg")


# ---------------------------------------------------------------------------
# AC3 - Category detection (URL patterns + content keywords, 19 categories)
# ---------------------------------------------------------------------------


class TestCategoryDetection:
    @pytest.mark.parametrize(
        "url,expected_category",
        [
            ("https://ndtv.com/india-news/pm-modi-meets-president", "national"),
            ("https://example.com/sports/cricket/india-vs-australia", "sports"),
            ("https://example.com/finance/rbi-rate-unchanged", "finance"),
            ("https://example.com/technology/ai-revolution", "technology"),
            ("https://example.com/health/dengue-outbreak", "health"),
            ("https://example.com/entertainment/bollywood-awards", "entertainment"),
            ("https://example.com/education/neet-results", "education"),
            ("https://example.com/crime/delhi-robbery-case", "crime"),
            ("https://example.com/environment/climate-summit", "environment"),
            ("https://example.com/jobs/sarkari-naukri-2024", "jobs"),
            ("https://example.com/defence/army-exercise", "defence"),
            ("https://example.com/opinion/editorial-budget", "opinion"),
        ],
    )
    def test_url_based_category_detection(self, parser, url, expected_category):
        """AC3: URL path segment correctly maps to the expected category."""
        html = f"<html><body><article><p>{'placeholder text ' * 20}</p></article></body></html>"
        article = parser.parse(html, url=url)
        assert article.category == expected_category, f"Expected {expected_category} for URL {url}"

    def test_body_keyword_fallback_category(self, parser):
        """AC3: When URL gives no category, body keywords determine it."""
        url = "https://example.com/story/1234"
        body_html = dedent("""
            <html><body><article>
            <p>The Reserve Bank of India kept the repo rate unchanged at 6.5 per cent.
               The Sensex fell 200 points in early trade. The Nifty slipped below 22,800.
               Mutual fund managers said the rate decision was expected by the market.
               The RBI governor commented on monetary policy tightening globally.</p>
            </article></body></html>
        """)
        article = parser.parse(body_html, url=url)
        assert article.category == "finance"

    def test_fallback_category_used_when_undetectable(self, parser):
        """AC3: fallback_category is applied when detection returns no match."""
        html = "<html><body><article><p>xyzzy foobar qux baz</p></article></body></html>"
        article = parser.parse(html, url="https://example.com/no-match", fallback_category="national")
        assert article.category == "national"


# ---------------------------------------------------------------------------
# AC4 - Language detection
# ---------------------------------------------------------------------------


class TestLanguageDetection:
    def test_english_article_detected(self, parser):
        """AC4: English article correctly detected (or trusted from expected)."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi", expected_language="en")
        assert article.language == "en"

    def test_hindi_article_detected_by_script(self, parser):
        """AC4: Hindi article detected by Devanagari Unicode script range."""
        article = parser.parse(
            HINDI_ARTICLE_HTML, url="https://aajtak.com/cricket/hindi-article", expected_language="hi"
        )
        assert article.language == "hi"

    def test_language_mismatch_logged(self, parser, caplog):
        """AC4: A warning is logged when detected language differs from expected."""
        import logging

        with caplog.at_level(logging.WARNING, logger="src.scrapers.article_parser"):
            parser.parse(HINDI_ARTICLE_HTML, url="https://example.com/story", expected_language="en")
        assert any("Language mismatch" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# AC5 - Metadata: author and publish_time
# ---------------------------------------------------------------------------


class TestMetadataExtraction:
    def test_author_extracted(self, parser):
        """AC5: Author name should be extracted from <meta name='author'>."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi")
        assert article.author == "Priya Sharma"

    def test_publish_time_extracted(self, parser):
        """AC5: publish_time should be parsed from article:published_time meta tag."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi")
        assert article.publish_time is not None
        assert article.publish_time.year == 2024
        assert article.publish_time.month == 6
        assert article.publish_time.day == 10

    def test_fallback_publish_time_used(self, parser):
        """AC5: When HTML has no date, fallback_publish_time should be used."""
        html = "<html><body><article><p>Some article text here.</p></article></body></html>"
        fallback = datetime(2024, 1, 15, tzinfo=timezone.utc)
        article = parser.parse(html, url="https://example.com/story", fallback_publish_time=fallback)
        assert article.publish_time.year == 2024
        assert article.publish_time.month == 1
        assert article.publish_time.day == 15

    def test_tags_extracted(self, parser):
        """AC5: Keywords meta tag should populate the tags list."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi")
        assert "RBI" in article.tags
        assert "repo rate" in article.tags


# ---------------------------------------------------------------------------
# AC6 - Incomplete article flagging (< 100 words)
# ---------------------------------------------------------------------------


class TestIncompleteFlag:
    def test_short_article_flagged(self, parser):
        """AC6: Article with fewer than 100 words should have is_incomplete=True."""
        article = parser.parse(SHORT_ARTICLE_HTML, url="https://example.com/story")
        assert article.is_incomplete is True

    def test_full_article_not_flagged(self, parser):
        """AC6: Full-length article should have is_incomplete=False."""
        article = parser.parse(FULL_ARTICLE_HTML, url="https://example.com/finance/rbi")
        assert article.is_incomplete is False

    def test_word_count_utility(self):
        assert word_count("one two three") == 3
        assert word_count("") == 0

    def test_is_incomplete_utility(self):
        short_body = " ".join(["word"] * 50)
        long_body = " ".join(["word"] * 150)
        assert is_incomplete(short_body) is True
        assert is_incomplete(long_body) is False


# ---------------------------------------------------------------------------
# AC7 - Parser works on all configured sources (sample source URLs)
# ---------------------------------------------------------------------------


class TestMultipleSourceSupport:
    @pytest.mark.parametrize(
        "source_url",
        [
            "https://www.thehindu.com/news/national/article123.html",
            "https://www.ndtv.com/india-news/article456.html",
            "https://www.hindustantimes.com/india-news/article789.html",
            "https://timesofindia.indiatimes.com/india/article012.html",
            "https://www.aajtak.in/india/article345.html",
        ],
    )
    def test_parser_produces_scraped_article(self, parser, source_url):
        """AC7: Parser should return a valid ScrapedArticle for any source URL."""
        html = dedent(f"""
            <html>
            <head>
              <meta property="og:title" content="Test Article from {source_url}"/>
              <meta property="og:image" content="https://cdn.test/image.jpg"/>
              <meta property="article:published_time" content="2024-06-10T10:00:00Z"/>
              <meta name="author" content="Test Author"/>
            </head>
            <body>
              <article>
                <p>{"This is test article content with sufficient words to pass the word count check. " * 10}</p>
              </article>
            </body>
            </html>
        """)
        article = parser.parse(html, url=source_url, expected_language="en")
        assert isinstance(article, ScrapedArticle)
        assert article.title != ""
        assert article.body != ""
        assert article.image_url == "https://cdn.test/image.jpg"
        assert article.author == "Test Author"
        assert article.publish_time is not None
        assert article.is_incomplete is False
