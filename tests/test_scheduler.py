"""Tests for Scrape Scheduler and Health Monitoring (Issue 8).

Acceptance Criteria covered:
  AC1 - Scheduler triggers scrape pipeline every 10 minutes
  AC2 - Sources are spread across the interval (not all scraped simultaneously)
  AC3 - Scraped articles are stored in database with all required fields
  AC4 - Source marked unhealthy after 5 consecutive scrape failures
  AC5 - Unhealthy sources are retried after 30-minute cooldown
  AC6 - GET /api/admin/scrape-health returns per-source health metrics
  AC7 - Pipeline logs: articles scraped, duplicates found, errors per cycle
  AC8 - Scheduler survives individual source failures (does not crash entire cycle)
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.main import app
from src.config.database import get_db
from src.config.settings import Language
from src.models.article import Article
from src.models.category import Category
from src.models.source import Source
from src.scheduler.jobs import (
    create_scheduler,
    is_scheduler_running,
    start_scheduler,
    stop_scheduler,
)
from src.scheduler.scrape_pipeline import ScrapePipeline
from src.scrapers.article_parser import ScrapedArticle

# ---------------------------------------------------------------------------
# Database & TestClient Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shared_engine():
    """Create a shared in-memory SQLite engine with StaticPool."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Category.__table__.create(engine)
    Source.__table__.create(engine)
    Article.__table__.create(engine)
    return engine


@pytest.fixture
def db_session(shared_engine):
    """Create an isolated database session for testing."""
    session_factory = sessionmaker(bind=shared_engine)
    session = session_factory()

    category = session.query(Category).filter(Category.slug == "national").first()
    if not category:
        category = Category(id=1, slug="national", name="National", is_active=True)
        session.add(category)
        session.commit()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_client(shared_engine):
    """FastAPI TestClient with overridden get_db dependency."""
    session_factory = sessionmaker(bind=shared_engine)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def pipeline():
    """Fresh ScrapePipeline instance."""
    return ScrapePipeline()


# ---------------------------------------------------------------------------
# AC1 - Scheduler triggers scrape pipeline every 10 minutes
# ---------------------------------------------------------------------------


class TestSchedulerConfiguration:
    def test_scheduler_interval_is_10_minutes(self):
        """AC1: Scheduler is configured with a 10-minute interval trigger."""
        scheduler = create_scheduler(interval_minutes=10, async_mode=True)
        job = scheduler.get_job("periodic_news_scrape_job")
        assert job is not None, "Scrape job should be registered"
        assert job.trigger.interval.total_seconds() == 600, "Interval should be 600s (10 mins)"

    def test_scheduler_lifecycle(self):
        """AC1: Scheduler starts and stops cleanly."""
        stop_scheduler()
        assert not is_scheduler_running()

        scheduler = start_scheduler(interval_minutes=10, async_mode=False)
        assert is_scheduler_running()
        assert scheduler.running

        stop_scheduler()
        assert not is_scheduler_running()


# ---------------------------------------------------------------------------
# AC2 - Sources are spread across the interval (rotation / staggering)
# ---------------------------------------------------------------------------


class TestSourceStaggering:
    @pytest.mark.asyncio
    async def test_sources_are_staggered_with_sleep(self, pipeline):
        """AC2: Sources are spread across the interval (not scraped simultaneously)."""
        mock_scraper = MagicMock()
        mock_scraper.scrape_source = AsyncMock(return_value=[])

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await pipeline.run_scrape_cycle(
                sources=["source_a", "source_b", "source_c"],
                stagger_seconds=5.0,
                custom_scraper=mock_scraper,
            )

            # For 3 sources with stagger_seconds=5.0, sleep should be called twice (before b and c)
            assert mock_sleep.call_count == 2
            mock_sleep.assert_called_with(5.0)


# ---------------------------------------------------------------------------
# AC3 - Articles stored in database with all required fields
# ---------------------------------------------------------------------------


class TestDatabaseStorage:
    def test_scraped_articles_stored_with_all_fields(self, pipeline, db_session):
        """AC3: Scraped articles are persisted to database with all fields."""
        unique_slug = f"src_{uuid.uuid4().hex[:6]}"
        unique_url = f"https://example.com/news/{uuid.uuid4().hex}"

        mock_article = ScrapedArticle(
            title="RBI keeps repo rate unchanged at 6.5%",
            body="The Reserve Bank of India decided to maintain the policy rate unchanged at 6.5 percent.",
            source_url=unique_url,
            publish_time=datetime(2026, 8, 15, 10, 30, 0),
            category="finance",
            image_url="https://example.com/rbi.jpg",
            author="Ananya Sen",
            language="en",
        )

        inserted, duplicates = pipeline.store_articles(
            db=db_session,
            source_slug=unique_slug,
            articles=[mock_article],
        )

        assert inserted == 1
        assert duplicates == 0

        # Query database to verify fields
        stored = db_session.query(Article).filter(Article.source_url == unique_url).first()
        assert stored is not None
        assert stored.title == "RBI keeps repo rate unchanged at 6.5%"
        assert stored.body.startswith("The Reserve Bank of India")
        assert stored.image_url == "https://example.com/rbi.jpg"
        assert stored.author == "Ananya Sen"
        assert stored.publish_time == datetime(2026, 8, 15, 10, 30, 0)
        assert stored.source_id is not None
        assert stored.category_id is not None
        assert stored.language == Language.ENGLISH
        assert stored.is_duplicate is False

    def test_duplicate_articles_are_not_inserted_twice(self, pipeline, db_session):
        """AC3: Duplicate URLs are caught and not duplicated in DB."""
        unique_slug = f"src_{uuid.uuid4().hex[:6]}"
        unique_url = f"https://example.com/duplicate-test-{uuid.uuid4().hex}"

        mock_article = ScrapedArticle(
            title="Duplicate Test Article",
            body="Article body text for duplicate testing.",
            source_url=unique_url,
            publish_time=datetime(2026, 8, 15, 12, 0, 0),
            category="national",
        )

        # First insert
        inserted_1, dup_1 = pipeline.store_articles(db_session, unique_slug, [mock_article])
        assert inserted_1 == 1
        assert dup_1 == 0

        # Second insert with same URL
        inserted_2, dup_2 = pipeline.store_articles(db_session, unique_slug, [mock_article])
        assert inserted_2 == 0
        assert dup_2 == 1


# ---------------------------------------------------------------------------
# AC4 - Source marked unhealthy after 5 consecutive failures
# ---------------------------------------------------------------------------


class TestUnhealthyThreshold:
    def test_healthy_under_5_failures(self, pipeline):
        """AC4: Source remains healthy with fewer than 5 consecutive failures."""
        slug = "test_flaky_source"

        for _ in range(4):
            pipeline.record_failure(slug, error_msg="Temporary network glitch")

        health = pipeline.source_health[slug]
        assert health["consecutive_failures"] == 4
        assert health["is_healthy"] is True
        assert health["status"] == "degraded"

    def test_unhealthy_at_5_consecutive_failures(self, pipeline):
        """AC4: Source is marked unhealthy on exactly the 5th consecutive failure."""
        slug = "test_failing_source"

        for _ in range(5):
            pipeline.record_failure(slug, error_msg="Connection timed out")

        health = pipeline.source_health[slug]
        assert health["consecutive_failures"] == 5
        assert health["is_healthy"] is False
        assert health["status"] == "unhealthy"
        assert health["unhealthy_since"] is not None
        assert health["cooldown_until"] is not None

    def test_success_resets_consecutive_failures(self, pipeline):
        """AC4: A success resets consecutive failure count to 0."""
        slug = "test_recovery_source"

        for _ in range(3):
            pipeline.record_failure(slug, error_msg="Error")
        assert pipeline.source_health[slug]["consecutive_failures"] == 3

        pipeline.record_success(slug, articles_count=5)
        assert pipeline.source_health[slug]["consecutive_failures"] == 0
        assert pipeline.source_health[slug]["is_healthy"] is True


# ---------------------------------------------------------------------------
# AC5 - Unhealthy sources retried after 30-minute cooldown
# ---------------------------------------------------------------------------


class TestCooldownRetry:
    def test_source_skipped_during_cooldown(self, pipeline):
        """AC5: Source in cooldown is reported as in cooldown."""
        slug = "test_cooldown_source"
        now = datetime.now(timezone.utc)

        # Trigger 5 failures to enter cooldown
        for _ in range(5):
            pipeline.record_failure(slug, error_msg="Failure", now=now)

        # 10 minutes later -> still in cooldown
        time_10m_later = now + timedelta(minutes=10)
        assert pipeline.is_in_cooldown(slug, current_time=time_10m_later) is True

    def test_source_retried_after_cooldown_expires(self, pipeline):
        """AC5: After 30 minutes pass, cooldown expires and retry is allowed."""
        slug = "test_cooldown_expired_source"
        now = datetime.now(timezone.utc)

        # Enter cooldown
        for _ in range(5):
            pipeline.record_failure(slug, error_msg="Failure", now=now)

        # 31 minutes later -> cooldown expired
        time_31m_later = now + timedelta(minutes=31)
        assert pipeline.is_in_cooldown(slug, current_time=time_31m_later) is False

    @pytest.mark.asyncio
    async def test_scrape_skips_source_in_active_cooldown(self, pipeline):
        """AC5: scrape_source returns skipped_cooldown status when active."""
        slug = "test_cooldown_skip"
        for _ in range(5):
            pipeline.record_failure(slug, error_msg="Failure")

        res = await pipeline.scrape_source(slug)
        assert res["status"] == "skipped_cooldown"
        assert res["articles_scraped"] == 0


# ---------------------------------------------------------------------------
# AC6 - GET /api/admin/scrape-health returns per-source health metrics
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_scrape_health_api_returns_metrics(self, test_client):
        """AC6: GET /api/admin/scrape-health returns per-source and pipeline metrics."""
        response = test_client.get("/api/admin/scrape-health")
        assert response.status_code == 200

        data = response.json()
        assert "sources" in data
        assert "pipeline" in data
        assert isinstance(data["sources"], list)
        assert "total_articles_scraped" in data["pipeline"]
        assert "overall_error_rate" in data["pipeline"]

        # Check source structure
        if len(data["sources"]) > 0:
            first_source = data["sources"][0]
            assert "slug" in first_source
            assert "is_healthy" in first_source
            assert "success_count" in first_source
            assert "error_count" in first_source
            assert "status" in first_source


# ---------------------------------------------------------------------------
# AC7 - Pipeline logs: articles scraped, duplicates found, errors per cycle
# ---------------------------------------------------------------------------


class TestPipelineLoggingAndMetrics:
    @pytest.mark.asyncio
    async def test_cycle_logs_summary(self, pipeline, db_session, caplog):
        """AC7: Pipeline logs summary of articles scraped, duplicates, errors."""
        import logging

        mock_scraper = MagicMock()
        mock_scraper.scrape_source = AsyncMock(
            return_value=[
                ScrapedArticle(
                    title="Article 1",
                    body="Body of article 1 with enough content to be valid.",
                    source_url=f"https://example.com/log1-{uuid.uuid4().hex}",
                    publish_time=datetime.now(),
                    category="national",
                )
            ]
        )

        with caplog.at_level(logging.INFO, logger="src.scheduler.scrape_pipeline"):
            result = await pipeline.run_scrape_cycle(
                db=db_session,
                sources=["test_source_log"],
                custom_scraper=mock_scraper,
            )

        assert "Scrape cycle completed" in caplog.text
        assert "articles_scraped=" in caplog.text
        assert "duplicates_found=" in caplog.text
        assert "errors=" in caplog.text
        assert result["cycle_summary"]["articles_scraped"] == 1


# ---------------------------------------------------------------------------
# AC8 - Scheduler survives individual source failures (resilience)
# ---------------------------------------------------------------------------


class TestSchedulerResilience:
    @pytest.mark.asyncio
    async def test_cycle_completes_despite_source_failure(self, pipeline, db_session):
        """AC8: Individual source failure does not crash the entire scrape cycle."""

        async def mock_scrape_fn(slug):
            if slug == "failing_source":
                raise ConnectionError("DNS resolution failed for failing_source")
            return [
                ScrapedArticle(
                    title=f"Article from {slug}",
                    body="Article body content.",
                    source_url=f"https://example.com/{slug}-{uuid.uuid4().hex}",
                    publish_time=datetime.now(),
                    category="national",
                )
            ]

        mock_scraper = MagicMock()
        mock_scraper.scrape_source = mock_scrape_fn

        # Run cycle with 3 sources (1 failing, 2 succeeding)
        result = await pipeline.run_scrape_cycle(
            db=db_session,
            sources=["failing_source", "good_source_1", "good_source_2"],
            custom_scraper=mock_scraper,
        )

        summary = result["cycle_summary"]
        assert summary["sources_attempted"] == 3
        assert summary["errors"] == 1
        assert summary["articles_scraped"] == 2
        assert len(result["results"]) == 3

        # Verify failing source was recorded as error
        assert result["results"][0]["status"] == "error"
        assert result["results"][1]["status"] == "success"
        assert result["results"][2]["status"] == "success"


# ---------------------------------------------------------------------------
# Additional Admin Endpoints Testing
# ---------------------------------------------------------------------------


class TestAdminRecentArticlesEndpoint:
    def test_get_recent_articles_api(self, test_client, db_session, pipeline):
        """Verify GET /api/admin/recent-articles returns stored articles."""
        url = f"https://example.com/recent-{uuid.uuid4().hex}"
        art = ScrapedArticle(
            title="Recent Breaking News",
            body="Full content of breaking news article.",
            source_url=url,
            publish_time=datetime.now(timezone.utc),
            category="national",
        )
        pipeline.store_articles(db_session, "recent_test_src", [art])

        response = test_client.get("/api/admin/recent-articles?limit=5")
        assert response.status_code == 200
        articles = response.json()
        assert isinstance(articles, list)
        assert any(a["source_url"] == url for a in articles)
