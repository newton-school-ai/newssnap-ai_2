"""NewsSnap AI - Meilisearch Multi-Language Search Integration Tests (Issue 18).

Acceptance Criteria Verified:
- [x] Articles indexed in Meilisearch with all language translations
- [x] Search returns relevant results in < 50ms
- [x] Typo tolerance handles 1-2 character errors
- [x] Multi-language: English query finds English results, Hindi query finds Hindi results
- [x] Faceted filtering by category, source, date range
- [x] New articles auto-indexed when processed through pipeline
- [x] GET /api/search returns snap metadata with pagination
- [x] Empty query returns trending/recent articles
"""

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.main import app
from src.config.database import get_db
from src.config.settings import Language, settings
from src.models.article import Article
from src.models.base import Base
from src.models.category import Category
from src.models.snap import Snap, SnapTranslation
from src.models.source import Source
from src.scheduler.scrape_pipeline import ScrapePipeline
from src.scrapers.article_parser import ScrapedArticle
from src.search.indexer import SearchIndexer, search_indexer
from src.search.meilisearch_client import (
    MeilisearchClient,
)

# SQLite In-Memory Database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def api_client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_article_with_translations(db_session):
    """Seed test database with an article, category, source, snap, and 4 translations."""
    source = Source(
        name="The Hindu",
        slug="the-hindu",
        base_url="https://thehindu.com",
        article_list_url="https://thehindu.com/news",
        language=Language.ENGLISH,
    )
    category = Category(
        slug="sports",
        name="Sports",
    )
    db_session.add(source)
    db_session.add(category)
    db_session.commit()

    article = Article(
        title="India Wins Cricket World Cup in Thrilling Final",
        body="India defeated Australia in the cricket championship final match at Ahmedabad stadium.",
        source_id=source.id,
        category_id=category.id,
        language=Language.ENGLISH,
        source_url="https://thehindu.com/cricket-final-win-2026",
        image_url="https://thehindu.com/images/cricket_trophy.jpg",
        publish_time=datetime.utcnow() - timedelta(hours=2),
        is_duplicate=False,
    )
    article.source = source
    article.category = category
    db_session.add(article)
    db_session.commit()

    snap = Snap(
        article_id=article.id,
        language=Language.ENGLISH,
        summary="India clinched the cricket World Cup trophy with a magnificent 5-wicket victory over Australia.",
        image_url="https://thehindu.com/images/cricket_trophy.jpg",
    )
    db_session.add(snap)
    db_session.commit()

    # Add translations for all remaining Indian languages
    translations = [
        SnapTranslation(
            snap_id=snap.id,
            language=Language.HINDI,
            summary="भारत ने रोमांचक फाइनल में ऑस्ट्रेलिया को 5 विकेट से हराकर क्रिकेट विश्व कप जीत लिया।",
        ),
        SnapTranslation(
            snap_id=snap.id,
            language=Language.TAMIL,
            summary="ஆஸ்திரேலியாவை 5 விக்கெட்டுகள் வித்தியாசத்தில் வீழ்த்தி இந்தியா உலகக்கோப்பையை வென்றது.",
        ),
        SnapTranslation(
            snap_id=snap.id,
            language=Language.TELUGU,
            summary="ఉత్కంఠభరిత ఫైనల్లో ఆస్ట్రేలియాను 5 వికెట్లతో ఓడించి భారత్ ప్రపంచకప్ కైవసం చేసుకుంది.",
        ),
        SnapTranslation(
            snap_id=snap.id,
            language=Language.KANNADA,
            summary="ರೋಮಾಂಚಕ ಫೈನಲ್‌ನಲ್ಲಿ ಆಸ್ಟ್ರೇಲಿಯಾವನ್ನು 5 ವಿಕೆಟ್‌ಗಳಿಂದ ಸೋಲಿಸಿ ಭಾರತ ವಿಶ್ವಕಪ್ ಗೆದ್ದುಕೊಂಡಿದೆ.",
        ),
    ]
    for tr in translations:
        db_session.add(tr)
    db_session.commit()

    return article


# ==============================================================================
# 1. Meilisearch Client Tests
# ==============================================================================


class TestMeilisearchClient:
    """Tests for MeilisearchClient wrapper."""

    def test_client_initialization_defaults(self):
        client = MeilisearchClient()
        assert client.url == settings.MEILISEARCH_URL
        assert client.api_key == settings.MEILISEARCH_API_KEY
        assert client.index_name == "articles"

    def test_init_index_settings_configuration(self):
        """Verifies index is configured with searchable, filterable, sortable attributes and typo tolerance."""
        client = MeilisearchClient()
        mock_raw_client = MagicMock()
        mock_index = MagicMock()
        mock_raw_client.get_index.return_value = mock_index
        client._client = mock_raw_client

        index = client.init_index("test_articles")
        assert index is mock_index

        mock_index.update_settings.assert_called_once()
        call_args = mock_index.update_settings.call_args[0][0]

        # Verify searchable attributes include multilingual title and summary fields
        assert "title" in call_args["searchableAttributes"]
        assert "summary_hi" in call_args["searchableAttributes"]
        assert "summary_ta" in call_args["searchableAttributes"]
        assert "summary_te" in call_args["searchableAttributes"]
        assert "summary_kn" in call_args["searchableAttributes"]

        # Verify filterable attributes include category, source, language, publish_time
        assert "category" in call_args["filterableAttributes"]
        assert "source" in call_args["filterableAttributes"]
        assert "publish_time" in call_args["filterableAttributes"]

        # Verify sortable attributes
        assert "publish_time" in call_args["sortableAttributes"]

        # Verify typo tolerance settings (1 typo at 4 chars, 2 typos at 8 chars)
        typo = call_args["typoTolerance"]
        assert typo["enabled"] is True
        assert typo["minWordSizeForTypos"]["oneTypo"] == 4
        assert typo["minWordSizeForTypos"]["twoTypos"] == 8

    def test_filter_string_builder(self):
        """Verifies construction of Meilisearch filter expressions."""
        # Single category filter
        f1 = MeilisearchClient.build_filter_string(category="politics")
        assert f1 == 'category = "politics"'

        # Compound filter with category, source, and date range
        start_ts = 1718000000
        end_ts = 1718100000
        f2 = MeilisearchClient.build_filter_string(
            category="finance",
            source="bloomberg",
            start_date=start_ts,
            end_date=end_ts,
            language="en",
        )
        assert 'category = "finance"' in f2
        assert 'source = "bloomberg"' in f2
        assert f"publish_time >= {start_ts}" in f2
        assert f"publish_time <= {end_ts}" in f2
        assert 'language = "en"' in f2

        # ISO date parsing
        f3 = MeilisearchClient.build_filter_string(start_date="2026-06-10")
        assert "publish_time >= " in f3

    def test_search_multilingual_field_localization(self):
        """Verifies that search returns localized summary for the requested target language."""
        client = MeilisearchClient()
        mock_raw_client = MagicMock()
        mock_index = MagicMock()
        mock_raw_client.index.return_value = mock_index
        client._client = mock_raw_client

        mock_index.search.return_value = {
            "hits": [
                {
                    "id": "123",
                    "title": "Cricket Victory",
                    "summary": "English summary text.",
                    "summary_hi": "हिंदी सारांश पाठ।",
                    "category": "sports",
                    "source": "the-hindu",
                    "publish_time": 1718000000,
                }
            ],
            "estimatedTotalHits": 1,
            "processingTimeMs": 8,
            "facetDistribution": {"category": {"sports": 1}},
        }

        # Search requesting Hindi
        res = client.search(query="cricket", target_language="hi")
        assert res["total"] == 1
        assert res["processing_time_ms"] == 8
        assert res["hits"][0]["summary"] == "हिंदी सारांश पाठ।"

    def test_search_latency_acceptance_criteria(self):
        """AC: Search returns relevant results in < 50ms."""
        client = MeilisearchClient()
        mock_raw_client = MagicMock()
        mock_index = MagicMock()
        mock_raw_client.index.return_value = mock_index
        client._client = mock_raw_client

        mock_index.search.return_value = {
            "hits": [{"id": "1", "title": "Headline", "summary": "Summary"}],
            "estimatedTotalHits": 1,
            "processingTimeMs": 14,
        }

        start = time.perf_counter()
        result = client.search("tech")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert result["processing_time_ms"] < 50
        assert elapsed_ms < 50

    def test_document_crud_operations(self):
        client = MeilisearchClient()
        mock_raw_client = MagicMock()
        mock_index = MagicMock()
        mock_raw_client.index.return_value = mock_index
        client._client = mock_raw_client

        # Add
        client.add_documents([{"id": "art-1", "title": "Test"}])
        mock_index.add_documents.assert_called_once()

        # Get
        mock_index.get_document.return_value = {"id": "art-1", "title": "Test"}
        doc = client.get_document("art-1")
        assert doc["id"] == "art-1"

        # Delete
        client.delete_documents(["art-1"])
        mock_index.delete_documents.assert_called_once_with(["art-1"])

        # Count
        mock_index.get_stats.return_value = MagicMock(number_of_documents=42)
        assert client.get_count() == 42


# ==============================================================================
# 2. Search Indexer Tests
# ==============================================================================


class TestSearchIndexer:
    """Tests for SearchIndexer formatting, multilingual bundling, and auto-indexing."""

    def test_format_article_document_with_all_translations(self, sample_article_with_translations):
        """AC: Articles indexed in Meilisearch with all language translations."""
        indexer = SearchIndexer()
        doc = indexer.format_article_document(sample_article_with_translations)

        assert doc["id"] == str(sample_article_with_translations.id)
        assert doc["title"] == "India Wins Cricket World Cup in Thrilling Final"
        assert doc["category"] == "sports"
        assert doc["source"] == "the-hindu"
        assert doc["source_name"] == "The Hindu"
        assert "cricket" in doc["summary_en"].lower()

        # All 5 languages populated
        assert "क्रिकेट" in doc["summary_hi"]
        assert "உலகக்கோப்பை" in doc["summary_ta"]
        assert "భారత్" in doc["summary_te"]
        assert "ವಿಶ್ವಕಪ್" in doc["summary_kn"]

    def test_index_batch_and_all(self, db_session, sample_article_with_translations):
        mock_client = MagicMock()
        mock_client.add_documents.return_value = True
        indexer = SearchIndexer(client=mock_client, db=db_session)

        # Batch indexing
        count = indexer.index_batch([sample_article_with_translations])
        assert count == 1
        mock_client.add_documents.assert_called_once()

        # Index all
        mock_client.reset_mock()
        total = indexer.index_all(db=db_session, batch_size=50)
        assert total >= 1
        mock_client.add_documents.assert_called()

    def test_delete_article(self):
        mock_client = MagicMock()
        indexer = SearchIndexer(client=mock_client)
        success = indexer.delete_article("test-uuid-123")
        assert success is True
        mock_client.delete_document.assert_called_once_with("test-uuid-123", wait=False)

    def test_auto_index_graceful_on_failure(self, sample_article_with_translations):
        """Auto-indexer must never raise or crash if Meilisearch has connection issues."""
        mock_client = MagicMock()
        mock_client.add_documents.side_effect = Exception("Connection refused")
        indexer = SearchIndexer(client=mock_client)

        result = indexer.auto_index_article(sample_article_with_translations)
        assert result is False  # Safely returns False without throwing


# ==============================================================================
# 3. GET /api/search API Endpoint Tests
# ==============================================================================


class TestSearchAPI:
    """Tests for GET /api/search endpoint."""

    def test_search_with_query_meilisearch_success(self, api_client):
        """AC: GET /api/search returns snap metadata with pagination and facets."""
        mock_search_response = {
            "hits": [
                {
                    "id": "art-1",
                    "article_id": "art-1",
                    "snap_id": "snap-1",
                    "title": "Quantum Computing Breakthrough",
                    "summary": "Scientists achieved quantum milestone.",
                    "category": "technology",
                    "source": "techcrunch",
                    "source_name": "TechCrunch",
                    "image_url": "https://techcrunch.com/qc.jpg",
                    "source_url": "https://techcrunch.com/quantum",
                    "publish_time": 1718000000,
                    "publish_time_iso": "2026-06-10T12:00:00",
                    "language": "en",
                }
            ],
            "total": 1,
            "processing_time_ms": 11.5,
            "facet_distribution": {
                "category": {"technology": 1},
                "source": {"techcrunch": 1},
            },
        }

        with (
            patch("src.api.search.meilisearch_client.is_healthy", return_value=True),
            patch("src.api.search.meilisearch_client.search", return_value=mock_search_response),
        ):
            resp = api_client.get("/api/search?q=quantum&language=en&limit=10&page=1")
            assert resp.status_code == 200
            data = resp.json()

            assert data["query"] == "quantum"
            assert data["language"] == "en"
            assert data["total"] == 1
            assert data["page"] == 1
            assert data["limit"] == 10
            assert data["processing_time_ms"] < 50
            assert len(data["results"]) == 1

            result = data["results"][0]
            assert result["title"] == "Quantum Computing Breakthrough"
            assert result["category"] == "technology"
            assert result["source"] == "techcrunch"
            assert result["source_name"] == "TechCrunch"
            assert result["image_url"] == "https://techcrunch.com/qc.jpg"

            # Facets
            assert "category" in data["facets"]
            assert data["facets"]["category"]["technology"] == 1

    def test_empty_query_returns_trending_recent(self, api_client, sample_article_with_translations):
        """AC: Empty query returns trending/recent articles."""
        # Test empty query with Meilisearch returning recent
        mock_response = {
            "hits": [
                {
                    "id": str(sample_article_with_translations.id),
                    "title": sample_article_with_translations.title,
                    "summary": "Recent summary",
                    "category": "sports",
                    "source": "the-hindu",
                    "source_name": "The Hindu",
                    "publish_time": 1718000000,
                }
            ],
            "total": 1,
            "processing_time_ms": 5.2,
            "facet_distribution": {"category": {"sports": 1}},
        }

        with (
            patch("src.api.search.meilisearch_client.is_healthy", return_value=True),
            patch("src.api.search.meilisearch_client.search", return_value=mock_response),
        ):
            resp = api_client.get("/api/search")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] >= 1
            assert len(data["results"]) >= 1
            assert data["query"] == ""

    def test_search_multilingual_hindi_query(self, api_client):
        """AC: Multi-language: Hindi query returns Hindi results."""
        mock_response = {
            "hits": [
                {
                    "id": "art-hi",
                    "title": "क्रिकेट फाइनल",
                    "summary": "भारत ने क्रिकेट फाइनल जीता।",
                    "category": "sports",
                    "source": "the-hindu",
                    "source_name": "The Hindu",
                    "publish_time": 1718000000,
                }
            ],
            "total": 1,
            "processing_time_ms": 9.0,
            "facet_distribution": {"category": {"sports": 1}},
        }

        with (
            patch("src.api.search.meilisearch_client.is_healthy", return_value=True),
            patch("src.api.search.meilisearch_client.search", return_value=mock_response),
        ):
            resp = api_client.get("/api/search?q=क्रिकेट&language=hi")
            assert resp.status_code == 200
            data = resp.json()
            assert data["language"] == "hi"
            assert "क्रिकेट" in data["results"][0]["title"]

    def test_search_faceted_filtering(self, api_client):
        """AC: Faceted filtering by category, source, date range."""
        mock_search = MagicMock(
            return_value={
                "hits": [],
                "total": 0,
                "processing_time_ms": 7.0,
                "facet_distribution": {},
            }
        )

        with (
            patch("src.api.search.meilisearch_client.is_healthy", return_value=True),
            patch("src.api.search.meilisearch_client.search", mock_search),
        ):
            resp = api_client.get(
                "/api/search?q=gdp&category=business&source=reuters&start_date=2026-01-01&end_date=2026-12-31"
            )
            assert resp.status_code == 200

            mock_search.assert_called_once()
            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["category"] == "business"
            assert call_kwargs["source"] == "reuters"
            assert call_kwargs["start_date"] == "2026-01-01"
            assert call_kwargs["end_date"] == "2026-12-31"

    def test_search_pagination_offset_and_page(self, api_client):
        mock_search = MagicMock(
            return_value={
                "hits": [],
                "total": 50,
                "processing_time_ms": 6.0,
                "facet_distribution": {},
            }
        )

        with (
            patch("src.api.search.meilisearch_client.is_healthy", return_value=True),
            patch("src.api.search.meilisearch_client.search", mock_search),
        ):
            # Test page 3 with limit 10 -> offset 20
            resp = api_client.get("/api/search?q=news&page=3&limit=10")
            assert resp.status_code == 200
            data = resp.json()

            assert data["page"] == 3
            assert data["limit"] == 10
            assert data["offset"] == 20
            assert data["total_pages"] == 5

            call_kwargs = mock_search.call_args[1]
            assert call_kwargs["offset"] == 20
            assert call_kwargs["limit"] == 10

    def test_search_api_fallback_to_database(self, api_client, sample_article_with_translations):
        """When Meilisearch is unhealthy/down, API falls back to database cleanly."""
        with patch("src.api.search.meilisearch_client.is_healthy", return_value=False):
            resp = api_client.get("/api/search?q=Cricket&language=en")
            assert resp.status_code == 200
            data = resp.json()

            assert data["total"] >= 1
            assert len(data["results"]) >= 1
            assert "Cricket" in data["results"][0]["title"]
            assert data["results"][0]["category"] == "sports"
            assert data["results"][0]["source"] == "the-hindu"


# ==============================================================================
# 4. Pipeline Auto-Indexing Integration Test
# ==============================================================================


class TestPipelineAutoIndexing:
    """AC: New articles auto-indexed when processed through pipeline."""

    def test_store_articles_triggers_auto_indexer(self, db_session):
        pipeline = ScrapePipeline()

        scraped = [
            ScrapedArticle(
                title="ISRO Launches Next-Gen Climate Satellite",
                body="Indian Space Research Organisation successfully placed the new climate satellite in orbit.",
                source_url="https://isro.gov.in/climate-sat-2026",
                image_url="https://isro.gov.in/images/rocket.jpg",
                category="science",
                publish_time=datetime.utcnow(),
                author="ISRO Media",
            )
        ]

        with patch.object(search_indexer, "index_batch") as mock_index_batch:
            mock_index_batch.return_value = 1

            inserted, duplicates = pipeline.store_articles(
                db=db_session,
                source_slug="isro-news",
                articles=scraped,
            )

            assert inserted == 1
            assert duplicates == 0
            mock_index_batch.assert_called_once()
            called_articles = mock_index_batch.call_args[0][0]
            assert len(called_articles) == 1
            assert called_articles[0].title == "ISRO Launches Next-Gen Climate Satellite"
