"""NewsSnap AI - Trending, Category, Breaking News, and Explore API Tests (Issue 20).

Acceptance Criteria Covered:
- [x] Trending API returns articles ranked by interaction velocity (last 1 hour)
- [x] Category API lists all categories with article counts
- [x] Top articles per category returns best articles from last 24 hours
- [x] Breaking news: articles < 30 min old with velocity > configurable threshold
- [x] Explore endpoint combines: breaking (if any) + trending + top per category
- [x] Velocity computed in Redis, refreshed every 5 minutes
- [x] All endpoints support language filtering
- [x] Response time < 100ms (Redis-cached)
"""

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.main import app
from src.config.database import get_db
from src.config.settings import Language
from src.models.article import Article
from src.models.base import Base
from src.models.category import Category
from src.models.interaction import Comment, Interaction, InteractionType
from src.models.snap import Snap
from src.models.source import Source
from src.models.user import User
from src.recommendation.trending import (
    compute_article_velocities,
)
from src.utils.auth_utils import create_token
from src.utils.cache import clear_cache, set_redis_client

TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    clear_cache()
    set_redis_client(None)  # Reset any mock
    yield
    clear_cache()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db):
    user = User(
        email="explorer@example.com",
        name="Explorer User",
        is_active=True,
        is_onboarded=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def auth_headers(test_user):
    token = create_token({"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seed_data(db, test_user):
    """Seed sources, categories, and varied articles with interaction profiles."""
    source_en = Source(
        name="Tech Chronicle",
        slug="tech-chronicle",
        base_url="https://techchronicle.com",
        article_list_url="https://techchronicle.com/rss",
        language=Language.ENGLISH,
    )
    source_hi = Source(
        name="Dainik Samachar",
        slug="dainik-samachar",
        base_url="https://dainiksamachar.in",
        article_list_url="https://dainiksamachar.in/rss",
        language=Language.HINDI,
    )
    db.add_all([source_en, source_hi])

    cat_tech = Category(id=1, slug="technology", name="Technology", is_active=True)
    cat_sports = Category(id=2, slug="sports", name="Sports", is_active=True)
    cat_business = Category(id=3, slug="business", name="Business", is_active=True)
    cat_inactive = Category(id=4, slug="archived", name="Archived", is_active=False)
    db.add_all([cat_tech, cat_sports, cat_business, cat_inactive])
    db.commit()

    now = datetime.utcnow()

    # Article 1: High velocity, recent breaking (10 mins old, 15 interactions)
    art1 = Article(
        title="OpenAI Unveils Breakthrough AI Model",
        body="A massive leap in artificial general intelligence reasoning capabilities was released today.",
        source_id=source_en.id,
        category_id=cat_tech.id,
        language=Language.ENGLISH,
        source_url="https://techchronicle.com/openai-breakthrough",
        publish_time=now - timedelta(minutes=10),
        quality_score=0.95,
        is_duplicate=False,
    )
    # Article 2: Medium velocity, published 40 mins ago (10 interactions)
    art2 = Article(
        title="India Wins Thrilling T20 Cricket Match",
        body="In a nail-biting final over, India secured victory against Australia.",
        source_id=source_en.id,
        category_id=cat_sports.id,
        language=Language.ENGLISH,
        source_url="https://techchronicle.com/india-t20-win",
        publish_time=now - timedelta(minutes=40),
        quality_score=0.88,
        is_duplicate=False,
    )
    # Article 3: Hindi article with high velocity (20 mins old, 8 interactions)
    art3 = Article(
        title="शेयर बाजार में भारी उछाल, सेंसेक्स रिकॉर्ड स्तर पर",
        body="भारतीय शेयर बाजार में आज जबरदस्त तेजी देखी गई। सेंसेक्स नए शिखर पर पहुंचा।",
        source_id=source_hi.id,
        category_id=cat_business.id,
        language=Language.HINDI,
        source_url="https://dainiksamachar.in/sensex-record",
        publish_time=now - timedelta(minutes=20),
        quality_score=0.92,
        is_duplicate=False,
    )
    # Article 4: Low velocity, published 12 hours ago (1 interaction)
    art4 = Article(
        title="Tech Sector Q3 Revenue Report Highlights",
        body="Analysis of enterprise software revenues and cloud computing growth.",
        source_id=source_en.id,
        category_id=cat_tech.id,
        language=Language.ENGLISH,
        source_url="https://techchronicle.com/q3-report",
        publish_time=now - timedelta(hours=12),
        quality_score=0.75,
        is_duplicate=False,
    )
    # Article 5: Old article (> 24 hours old, published 30 hours ago)
    art5 = Article(
        title="Historic Football Championship Recap",
        body="Looking back at the historic football championship matches.",
        source_id=source_en.id,
        category_id=cat_sports.id,
        language=Language.ENGLISH,
        source_url="https://techchronicle.com/historic-championship",
        publish_time=now - timedelta(hours=30),
        quality_score=0.80,
        is_duplicate=False,
    )
    # Article 6: Duplicate article (should be excluded)
    art6 = Article(
        title="Duplicate AI Model Announcement",
        body="Duplicate content of OpenAI model announcement.",
        source_id=source_en.id,
        category_id=cat_tech.id,
        language=Language.ENGLISH,
        source_url="https://techchronicle.com/duplicate-openai",
        publish_time=now - timedelta(minutes=5),
        quality_score=0.50,
        is_duplicate=True,
    )

    db.add_all([art1, art2, art3, art4, art5, art6])
    db.commit()

    # Add snaps
    snap1 = Snap(
        article_id=art1.id,
        language=Language.ENGLISH,
        summary="OpenAI announces next-gen reasoning model with unprecedented performance.",
        image_url="https://techchronicle.com/img/openai.jpg",
    )
    snap2 = Snap(
        article_id=art2.id,
        language=Language.ENGLISH,
        summary="India clinches thrilling last-ball win in high-scoring T20 match.",
        image_url="https://techchronicle.com/img/cricket.jpg",
    )
    snap3 = Snap(
        article_id=art3.id,
        language=Language.HINDI,
        summary="सेंसेक्स और निफ्टी नए रिकॉर्ड स्तर पर बंद हुए।",
        image_url="https://dainiksamachar.in/img/market.jpg",
    )
    db.add_all([snap1, snap2, snap3])
    db.commit()

    # Seed interactions within the last 1 hour
    # Article 1 interactions: 5 shares, 5 likes, 5 comments -> very high velocity
    for _ in range(5):
        db.add(
            Interaction(
                user_id=test_user.id,
                article_id=art1.id,
                type=InteractionType.SHARE.value,
                created_at=now - timedelta(minutes=5),
            )
        )
        db.add(
            Interaction(
                user_id=test_user.id,
                article_id=art1.id,
                type=InteractionType.LIKE.value,
                created_at=now - timedelta(minutes=6),
            )
        )
        db.add(
            Comment(
                user_id=test_user.id,
                article_id=art1.id,
                content="Incredible advance!",
                created_at=now - timedelta(minutes=7),
            )
        )

    # Article 2 interactions: 2 likes, 2 reads -> medium velocity
    for _ in range(2):
        db.add(
            Interaction(
                user_id=test_user.id,
                article_id=art2.id,
                type=InteractionType.LIKE.value,
                created_at=now - timedelta(minutes=15),
            )
        )
        db.add(
            Interaction(
                user_id=test_user.id,
                article_id=art2.id,
                type=InteractionType.READ.value,
                created_at=now - timedelta(minutes=20),
            )
        )

    # Article 3 (Hindi) interactions: 3 shares, 3 likes -> high velocity in Hindi
    for _ in range(3):
        db.add(
            Interaction(
                user_id=test_user.id,
                article_id=art3.id,
                type=InteractionType.SHARE.value,
                created_at=now - timedelta(minutes=10),
            )
        )
        db.add(
            Interaction(
                user_id=test_user.id,
                article_id=art3.id,
                type=InteractionType.LIKE.value,
                created_at=now - timedelta(minutes=12),
            )
        )

    # Article 4 interactions: 1 read
    db.add(
        Interaction(
            user_id=test_user.id,
            article_id=art4.id,
            type=InteractionType.READ.value,
            created_at=now - timedelta(minutes=25),
        )
    )

    # Article 5 interactions: 5 likes but happened 20 hours ago (outside 1h trending window)
    for _ in range(5):
        db.add(
            Interaction(
                user_id=test_user.id,
                article_id=art5.id,
                type=InteractionType.LIKE.value,
                created_at=now - timedelta(hours=20),
            )
        )

    db.commit()

    return {
        "art1": art1,
        "art2": art2,
        "art3": art3,
        "art4": art4,
        "art5": art5,
        "art6": art6,
        "cat_tech": cat_tech,
        "cat_sports": cat_sports,
        "cat_business": cat_business,
    }


# ==============================================================================
# 1. Trending API Tests (AC: Ranked by velocity in last 1 hour)
# ==============================================================================


class TestTrendingAPI:
    """AC: Trending API returns articles ranked by interaction velocity (last 1 hour)."""

    def test_trending_ranked_by_velocity(self, client, seed_data):
        res = client.get("/api/trending?language=en&limit=10")
        assert res.status_code == 200
        data = res.json()

        assert "trending" in data
        assert len(data["trending"]) >= 2

        # Article 1 (lots of shares/comments in last 10m) should be ranked higher than Article 2
        first_art = data["trending"][0]
        second_art = data["trending"][1]

        assert first_art["title"] == seed_data["art1"].title
        assert second_art["title"] == seed_data["art2"].title
        assert first_art["velocity"] >= second_art["velocity"]
        assert first_art["velocity"] > 0.0

    def test_trending_excludes_duplicates(self, client, seed_data):
        res = client.get("/api/trending?language=en&limit=20")
        assert res.status_code == 200
        titles = [a["title"] for a in res.json()["trending"]]
        assert seed_data["art6"].title not in titles

    def test_trending_language_filtering(self, client, seed_data):
        # Query Hindi trending
        res_hi = client.get("/api/trending?language=hi&limit=10")
        assert res_hi.status_code == 200
        data_hi = res_hi.json()
        assert len(data_hi["trending"]) == 1
        assert data_hi["trending"][0]["title"] == seed_data["art3"].title
        assert data_hi["trending"][0]["language"] == "hi"

        # Query English trending
        res_en = client.get("/api/trending?language=en&limit=10")
        assert res_en.status_code == 200
        for item in res_en.json()["trending"]:
            assert item["language"] == "en"

    def test_trending_category_filtering(self, client, seed_data):
        res = client.get("/api/trending?language=en&category=sports&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert len(data["trending"]) >= 1
        for item in data["trending"]:
            assert item["category"] == "sports"

    def test_trending_pagination(self, client, seed_data):
        res_limit_1 = client.get("/api/trending?language=en&limit=1&offset=0")
        assert res_limit_1.status_code == 200
        data1 = res_limit_1.json()
        assert len(data1["trending"]) == 1

        res_offset_1 = client.get("/api/trending?language=en&limit=1&offset=1")
        assert res_offset_1.status_code == 200
        data2 = res_offset_1.json()
        assert len(data2["trending"]) == 1
        assert data1["trending"][0]["id"] != data2["trending"][0]["id"]


# ==============================================================================
# 2. Category API Tests (AC: List with article counts & Top in 24 hours)
# ==============================================================================


class TestCategoryAPI:
    """AC: Category API lists all categories with article counts & top articles per category."""

    def test_list_categories_with_article_counts(self, client, seed_data):
        res = client.get("/api/categories")
        assert res.status_code == 200
        data = res.json()

        assert "categories" in data
        categories = data["categories"]
        assert len(categories) >= 3

        cat_counts = {c["slug"]: c["article_count"] for c in categories}
        # Technology has art1 and art4 (art6 is duplicate so excluded) -> count 2
        assert cat_counts.get("technology") == 2
        # Sports has art2 and art5 -> count 2
        assert cat_counts.get("sports") == 2
        # Business has art3 -> count 1
        assert cat_counts.get("business") == 1

    def test_list_categories_language_filtering(self, client, seed_data):
        res = client.get("/api/categories?language=hi")
        assert res.status_code == 200
        categories = res.json()["categories"]
        cat_counts = {c["slug"]: c["article_count"] for c in categories}
        assert cat_counts.get("business") == 1
        assert cat_counts.get("technology") == 0
        assert cat_counts.get("sports") == 0

    def test_get_category_details(self, client, seed_data):
        res = client.get("/api/categories/technology")
        assert res.status_code == 200
        data = res.json()
        assert data["slug"] == "technology"
        assert data["name"] == "Technology"
        assert data["article_count"] == 2

    def test_get_nonexistent_category_returns_404(self, client):
        res = client.get("/api/categories/nonexistent-category")
        assert res.status_code == 404

    def test_top_articles_per_category_last_24_hours(self, client, seed_data):
        # Category sports: art2 published 40 mins ago, art5 published 30 hours ago
        res = client.get("/api/categories/sports/top?language=en&limit=10")
        assert res.status_code == 200
        data = res.json()

        assert "articles" in data
        articles = data["articles"]
        # Only art2 is <= 24 hours old; art5 is > 24 hours old so must be excluded
        titles = [a["title"] for a in articles]
        assert seed_data["art2"].title in titles
        assert seed_data["art5"].title not in titles

    def test_top_articles_nonexistent_category_returns_404(self, client):
        res = client.get("/api/categories/invalid-slug/top?language=en")
        assert res.status_code == 404


# ==============================================================================
# 3. Breaking News API Tests (AC: < 30 min old with velocity > threshold)
# ==============================================================================


class TestBreakingNewsAPI:
    """AC: Breaking news: articles < 30 min old with velocity > configurable threshold."""

    def test_detect_breaking_news(self, client, seed_data):
        # art1: published 10 mins ago (< 30 min) and high velocity -> BREAKING
        # art2: published 40 mins ago (> 30 min) -> NOT BREAKING
        # art3: published 20 mins ago in Hindi -> BREAKING for Hindi
        # art4: published 12 hours ago -> NOT BREAKING
        res_en = client.get("/api/breaking?language=en&threshold=0.5")
        assert res_en.status_code == 200
        data = res_en.json()

        assert "breaking" in data
        breaking_titles = [a["title"] for a in data["breaking"]]

        assert seed_data["art1"].title in breaking_titles
        assert seed_data["art2"].title not in breaking_titles
        assert seed_data["art4"].title not in breaking_titles
        assert data["breaking"][0]["is_breaking"] is True

    def test_breaking_news_threshold_configuration(self, client, seed_data):
        # A very high threshold should return no breaking news
        res_high = client.get("/api/breaking?language=en&threshold=999.0")
        assert res_high.status_code == 200
        assert len(res_high.json()["breaking"]) == 0

        # A very low threshold should return art1
        res_low = client.get("/api/breaking?language=en&threshold=0.01")
        assert res_low.status_code == 200
        assert len(res_low.json()["breaking"]) >= 1

    def test_breaking_news_language_filter(self, client, seed_data):
        res_hi = client.get("/api/breaking?language=hi&threshold=0.1")
        assert res_hi.status_code == 200
        data_hi = res_hi.json()
        assert len(data_hi["breaking"]) == 1
        assert data_hi["breaking"][0]["title"] == seed_data["art3"].title


# ==============================================================================
# 4. Explore Endpoint Tests (AC: Combines breaking + trending + top per category)
# ==============================================================================


class TestExploreAPI:
    """AC: Explore endpoint combines: breaking (if any) + trending + top per category."""

    def test_explore_endpoint_combined_structure(self, client, seed_data):
        res = client.get("/api/explore?language=en")
        assert res.status_code == 200
        data = res.json()

        assert "breaking" in data
        assert "trending" in data
        assert "categories" in data
        assert "language" in data
        assert "timestamp" in data

        # Check breaking news
        assert len(data["breaking"]) >= 1
        assert data["breaking"][0]["title"] == seed_data["art1"].title

        # Check trending
        assert len(data["trending"]) >= 1
        assert data["trending"][0]["title"] == seed_data["art1"].title

        # Check categories section has category blocks with articles
        assert isinstance(data["categories"], list)
        tech_section = next((c for c in data["categories"] if c["slug"] == "technology"), None)
        assert tech_section is not None
        assert "articles" in tech_section
        assert len(tech_section["articles"]) >= 1

    def test_explore_authenticated_user(self, client, seed_data, auth_headers, test_user):
        res = client.get("/api/explore?language=en", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data.get("user_id") == str(test_user.id)


# ==============================================================================
# 5. Redis Caching & Velocity Computation Tests (AC: Redis-cached, < 100ms)
# ==============================================================================


class TestRedisCachingAndPerformance:
    """AC: Velocity computed in Redis, refreshed every 5 minutes, response time < 100ms."""

    def test_cached_response_performance_sub_100ms(self, client, seed_data):
        # First call warms the cache
        client.get("/api/trending?language=en&limit=10")

        # Second call hits cache; measure response time
        start_time = time.perf_counter()
        res = client.get("/api/trending?language=en&limit=10")
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert res.status_code == 200
        assert elapsed_ms < 100.0, f"Expected < 100ms response time, got {elapsed_ms:.2f}ms"

    def test_category_cached_response_sub_100ms(self, client, seed_data):
        client.get("/api/categories")
        start_time = time.perf_counter()
        res = client.get("/api/categories")
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert res.status_code == 200
        assert elapsed_ms < 100.0

    def test_explore_cached_response_sub_100ms(self, client, seed_data):
        client.get("/api/explore?language=en")
        start_time = time.perf_counter()
        res = client.get("/api/explore?language=en")
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert res.status_code == 200
        assert elapsed_ms < 100.0

    def test_trending_refresh_endpoint(self, client, seed_data):
        res = client.post("/api/trending/refresh")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "refreshed"
        assert "summary" in data

    def test_mock_redis_interaction(self, db, seed_data):
        """Verify Redis zadd and zrevrange interactions when Redis is active."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None
        set_redis_client(mock_redis)

        try:
            # Recompute velocities with mock Redis
            compute_article_velocities(db, window_hours=1.0, language="en")
            # Verify mock_redis.zadd was called with velocity scores
            assert mock_redis.zadd.called
            call_args = mock_redis.zadd.call_args
            assert "trending:velocity:en" in call_args[0][0]
        finally:
            set_redis_client(None)

    def test_trending_scheduler_5_minute_refresh_job(self):
        """AC: Velocity computed in Redis, refreshed every 5 minutes (scheduler job)."""
        from src.scheduler.jobs import TRENDING_JOB_ID, create_scheduler

        scheduler = create_scheduler(async_mode=True)
        job = scheduler.get_job(TRENDING_JOB_ID)
        assert job is not None, "Trending refresh job should be registered in scheduler"
        assert job.trigger.interval.total_seconds() == 300, "Interval should be 300s (5 minutes)"
