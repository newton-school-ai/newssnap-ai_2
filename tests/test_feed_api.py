"""Tests for personalized feed API, cursor pagination, filtering, and caching (Issue 17)."""

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.main import app
from src.config.database import get_db
from src.config.settings import Language, ScrapeType, UserRole
from src.models.article import Article
from src.models.base import Base
from src.models.category import Category
from src.models.interaction import Comment, Interaction
from src.models.snap import Snap, SnapTranslation
from src.models.source import Source
from src.models.user import User, UserPreference
from src.utils.auth_utils import create_token
from src.utils.cache import invalidate_feed_cache, set_custom_redis_client


class InMemoryRedis:
    """Lightweight in-memory mock for Redis cache testing."""

    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
        self.expiries: Dict[str, float] = {}

    def get(self, key: str) -> Optional[str]:
        now = time.time()
        if key in self.expiries and now > self.expiries[key]:
            del self.store[key]
            del self.expiries[key]
            return None
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self.store[key] = value
        self.expiries[key] = time.time() + ttl
        return True

    def scan_iter(self, match: str = "*", count: int = 100):
        prefix = match.rstrip("*")
        for key in list(self.store.keys()):
            if key.startswith(prefix):
                yield key

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                self.expiries.pop(k, None)
                count += 1
        return count

    def flushall(self) -> None:
        self.store.clear()
        self.expiries.clear()


# Setup in-memory SQLite database
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)

fake_redis = InMemoryRedis()
set_custom_redis_client(fake_redis)

client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_teardown_db():
    """Reset DB and cache before each test."""
    app.dependency_overrides[get_db] = override_get_db
    fake_redis.flushall()
    session = TestingSessionLocal()
    # Clean tables in reverse dependency order
    session.query(Interaction).delete()
    session.query(Comment).delete()
    session.query(SnapTranslation).delete()
    session.query(Snap).delete()
    session.query(Article).delete()
    session.query(Category).delete()
    session.query(Source).delete()
    session.query(UserPreference).delete()
    session.query(User).delete()
    session.commit()
    session.close()
    yield
    app.dependency_overrides.pop(get_db, None)


def _seed_sample_data(session):
    """Seed helper with sources, categories, and articles with snaps."""
    now = datetime.now(timezone.utc)

    # Categories
    cat_tech = Category(id=1, slug="technology", name="Technology", is_active=True)
    cat_sports = Category(id=2, slug="sports", name="Sports", is_active=True)
    cat_pol = Category(id=3, slug="politics", name="Politics", is_active=True)
    session.add_all([cat_tech, cat_sports, cat_pol])
    session.flush()

    # Source
    src = Source(
        id=uuid.uuid4(),
        slug="hindu",
        name="The Hindu",
        base_url="https://thehindu.com",
        article_list_url="https://thehindu.com/news",
        language=Language.ENGLISH,
        scrape_type=ScrapeType.STATIC,
        is_active=True,
    )
    session.add(src)
    session.flush()

    articles_data = [
        ("Tech News 1", "Tech summary 1", cat_tech.id, now - timedelta(hours=1), 0.9),
        ("Sports News 1", "Sports summary 1", cat_sports.id, now - timedelta(hours=2), 0.85),
        ("Politics News 1", "Politics summary 1", cat_pol.id, now - timedelta(hours=5), 0.7),
        ("Tech News 2", "Tech summary 2", cat_tech.id, now - timedelta(hours=10), 0.8),
        ("Sports News 2", "Sports summary 2", cat_sports.id, now - timedelta(days=2), 0.75),
    ]

    created_snaps = []
    for title, summary, cat_id, pub_time, q_score in articles_data:
        art = Article(
            id=uuid.uuid4(),
            title=title,
            body=f"{title} full content details here...",
            source_id=src.id,
            category_id=cat_id,
            language=Language.ENGLISH,
            source_url=f"https://thehindu.com/news/{uuid.uuid4().hex[:8]}",
            image_url="https://cdn.newssnap.ai/img/test.jpg",
            publish_time=pub_time,
            quality_score=q_score,
            is_duplicate=False,
        )
        session.add(art)
        session.flush()

        snap = Snap(
            id=uuid.uuid4(),
            article_id=art.id,
            language=Language.ENGLISH,
            summary=summary,
            image_url=art.image_url,
        )
        session.add(snap)
        created_snaps.append(snap)

    session.commit()
    return created_snaps


# 1. Acceptance Criteria: Language filter is required (returns 400 without it)
def test_feed_language_required():
    """Verify that GET /api/feed returns 400 when language parameter is omitted."""
    response = client.get("/api/feed")
    assert response.status_code == 400
    assert "language" in response.json()["detail"].lower()


def test_feed_unsupported_language():
    """Verify that unsupported language returns 400 Bad Request."""
    response = client.get("/api/feed?language=invalid_lang")
    assert response.status_code == 400
    assert "unsupported language" in response.json()["detail"].lower()


# 2. Acceptance Criteria: GET /api/feed returns personalized snap list with all required fields
def test_feed_returns_all_required_item_fields():
    """Verify that each feed item includes all 9 required fields."""
    session = TestingSessionLocal()
    _seed_sample_data(session)
    session.close()

    response = client.get("/api/feed?language=en&limit=10")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "snaps" in data
    assert len(data["items"]) > 0

    required_keys = {
        "snap_id",
        "article_id",
        "title",
        "summary",
        "image_url",
        "category",
        "source",
        "time_ago",
        "interaction_counts",
    }

    for item in data["items"]:
        for key in required_keys:
            assert key in item, f"Missing required key '{key}' in feed item"
        # Validate interaction_counts sub-keys
        counts = item["interaction_counts"]
        assert "likes" in counts
        assert "comments" in counts
        assert "shares" in counts
        assert "bookmarks" in counts
        assert isinstance(item["time_ago"], str)


# 3. Acceptance Criteria: Category filter narrows results to selected categories
def test_feed_category_filtering():
    """Verify that category filter restricts items to specified categories."""
    session = TestingSessionLocal()
    _seed_sample_data(session)
    session.close()

    # Filter to only technology and sports
    response = client.get("/api/feed?language=en&categories=technology,sports")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) > 0

    for item in items:
        assert item["category"] in ["technology", "sports"]
        assert item["category"] != "politics"


# 4. Acceptance Criteria: New users get trending + preference-based default feed
def test_new_user_gets_trending_and_preference_feed():
    """Verify that a newly onboarded user has their preferred categories ranked higher."""
    session = TestingSessionLocal()
    _seed_sample_data(session)

    # Create a new onboarded user preferring sports
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="newuser@example.com",
        name="New User",
        role=UserRole.READER,
        is_active=True,
        is_onboarded=True,
    )
    pref = UserPreference(
        user_id=user_id,
        primary_language=Language.ENGLISH,
        categories=["sports"],
    )
    session.add_all([user, pref])
    session.commit()
    session.close()

    token = create_token({"sub": str(user_id)})
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/feed?language=en&limit=5", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]

    # The top item should be from user's preferred category (sports)
    assert items[0]["category"] == "sports"


# 5. Acceptance Criteria: Cursor-based pagination and graceful end-of-feed
def test_cursor_based_pagination_flow():
    """Verify infinite scroll cursor pagination and graceful end-of-feed."""
    session = TestingSessionLocal()
    _seed_sample_data(session)
    session.close()

    # Request first page with limit=2
    res_p1 = client.get("/api/feed?language=en&limit=2")
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert len(data_p1["items"]) == 2
    assert data_p1["has_more"] is True
    cursor_p1 = data_p1["next_cursor"]
    assert cursor_p1 is not None

    # Request second page with next_cursor
    res_p2 = client.get(f"/api/feed?language=en&limit=2&cursor={cursor_p1}")
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert len(data_p2["items"]) == 2
    assert data_p2["has_more"] is True
    cursor_p2 = data_p2["next_cursor"]
    assert cursor_p2 is not None

    # Page 1 items and Page 2 items should not overlap
    ids_p1 = {item["snap_id"] for item in data_p1["items"]}
    ids_p2 = {item["snap_id"] for item in data_p2["items"]}
    assert ids_p1.isdisjoint(ids_p2)

    # Request third page
    res_p3 = client.get(f"/api/feed?language=en&limit=2&cursor={cursor_p2}")
    assert res_p3.status_code == 200
    data_p3 = res_p3.json()
    assert len(data_p3["items"]) == 1
    # End of feed: next_cursor is None and has_more is False
    assert data_p3["has_more"] is False
    assert data_p3["next_cursor"] is None

    # Request past the end of feed
    res_p4 = client.get(f"/api/feed?language=en&limit=2&cursor={cursor_p2}")
    # Still handles gracefully without error
    assert res_p4.status_code == 200


def test_invalid_cursor_returns_400():
    """Verify that passing an invalid/garbage cursor returns 400 Bad Request."""
    response = client.get("/api/feed?language=en&cursor=invalid_not_base64")
    assert response.status_code == 400
    assert "cursor" in response.json()["detail"].lower()


# 6. Acceptance Criteria: Feed response time < 200ms (cached)
def test_feed_response_time_under_200ms_cached():
    """Verify that cached feed requests respond well under 200ms."""
    session = TestingSessionLocal()
    _seed_sample_data(session)
    session.close()

    # Initial request to populate cache
    client.get("/api/feed?language=en&limit=20")

    # Time cached response
    start_time = time.perf_counter()
    response = client.get("/api/feed?language=en&limit=20")
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    assert response.status_code == 200
    # Response time must be under 200ms (typically under 15ms in test)
    assert elapsed_ms < 200.0, f"Cached response took {elapsed_ms:.2f}ms, expected < 200ms"


# 7. Acceptance Criteria: Redis cache invalidated when new snaps are generated
def test_redis_cache_invalidation_flow():
    """Verify that cache invalidation removes cached feed and forces fresh retrieval."""
    session = TestingSessionLocal()
    _seed_sample_data(session)
    session.close()

    # Populate cache
    res1 = client.get("/api/feed?language=en&limit=10")
    assert res1.status_code == 200
    assert len(fake_redis.store) > 0

    # Invalidate cache
    deleted = invalidate_feed_cache()
    assert deleted > 0
    assert len(fake_redis.store) == 0

    # Next request re-populates cache
    res2 = client.get("/api/feed?language=en&limit=10")
    assert res2.status_code == 200
    assert len(fake_redis.store) > 0


# 8. Multi-language translation support
def test_multi_language_translated_snap_summary():
    """Verify that requesting a specific language returns the translated summary."""
    session = TestingSessionLocal()
    now = datetime.now(timezone.utc)

    cat = Category(id=10, slug="national", name="National", is_active=True)
    src = Source(
        id=uuid.uuid4(),
        slug="src1",
        name="Source 1",
        base_url="https://src1.com",
        article_list_url="https://src1.com/list",
        language=Language.ENGLISH,
        scrape_type=ScrapeType.STATIC,
        is_active=True,
    )
    session.add_all([cat, src])
    session.flush()

    art = Article(
        id=uuid.uuid4(),
        title="Moon Landing",
        body="Details of moon landing.",
        source_id=src.id,
        category_id=cat.id,
        language=Language.ENGLISH,
        source_url="https://src1.com/moon",
        publish_time=now,
        is_duplicate=False,
    )
    session.add(art)
    session.flush()

    snap = Snap(
        id=uuid.uuid4(),
        article_id=art.id,
        language=Language.ENGLISH,
        summary="English summary of moon landing.",
    )
    session.add(snap)
    session.flush()

    # Add Hindi translation
    hindi_trans = SnapTranslation(
        id=uuid.uuid4(),
        snap_id=snap.id,
        language=Language.HINDI,
        summary="Chand par safal landing ka vivaran.",
    )
    session.add(hindi_trans)
    session.commit()
    session.close()

    # Request Hindi feed
    response = client.get("/api/feed?language=hi&limit=10")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) > 0
    assert items[0]["summary"] == "Chand par safal landing ka vivaran."


# 9. Time range filter test
def test_time_range_filter():
    """Verify that time_range filters articles within the specified cutoff."""
    session = TestingSessionLocal()
    now = datetime.now(timezone.utc)

    cat = Category(id=20, slug="science", name="Science", is_active=True)
    src = Source(
        id=uuid.uuid4(),
        slug="src2",
        name="Source 2",
        base_url="https://src2.com",
        article_list_url="https://src2.com/list",
        language=Language.ENGLISH,
        scrape_type=ScrapeType.STATIC,
        is_active=True,
    )
    session.add_all([cat, src])
    session.flush()

    recent_art = Article(
        id=uuid.uuid4(),
        title="Recent Discovery",
        body="Recent body",
        source_id=src.id,
        category_id=cat.id,
        language=Language.ENGLISH,
        source_url="https://src2.com/recent",
        publish_time=now - timedelta(hours=2),
        is_duplicate=False,
    )
    old_art = Article(
        id=uuid.uuid4(),
        title="Old Discovery",
        body="Old body",
        source_id=src.id,
        category_id=cat.id,
        language=Language.ENGLISH,
        source_url="https://src2.com/old",
        publish_time=now - timedelta(days=15),
        is_duplicate=False,
    )
    session.add_all([recent_art, old_art])
    session.flush()

    snap_recent = Snap(id=uuid.uuid4(), article_id=recent_art.id, summary="Recent sum")
    snap_old = Snap(id=uuid.uuid4(), article_id=old_art.id, summary="Old sum")
    session.add_all([snap_recent, snap_old])
    session.commit()
    session.close()

    # Filter with time_range=24h
    res = client.get("/api/feed?language=en&time_range=24h")
    assert res.status_code == 200
    items = res.json()["items"]
    titles = [item["title"] for item in items]
    assert "Recent Discovery" in titles
    assert "Old Discovery" not in titles


def test_guest_feed_works_without_auth():
    """Verify that unauthenticated guest users receive a 200 OK feed."""
    session = TestingSessionLocal()
    _seed_sample_data(session)
    session.close()

    response = client.get("/api/feed?language=en&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) > 0


def test_empty_feed_handled_gracefully():
    """Verify that when no snaps match, empty list is returned with next_cursor=None."""
    # DB is empty in this test
    response = client.get("/api/feed?language=en&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["snaps"] == []
    assert data["next_cursor"] is None
    assert data["has_more"] is False


def test_invalid_auth_token_returns_401():
    """Verify that providing a malformed or invalid Bearer token returns 401 Unauthorized."""
    response = client.get("/api/feed?language=en", headers={"Authorization": "Bearer bad_token"})
    assert response.status_code == 401


def test_snap_generator_triggers_cache_invalidation():
    """Verify that SnapGenerator.generate automatically invalidates the Redis feed cache."""
    from src.snaps.snap_generator import SnapGenerator

    # Populate cache
    fake_redis.setex("feed:test:key", 300, "dummy_data")
    assert "feed:test:key" in fake_redis.store

    # Generate a snap
    gen = SnapGenerator()
    gen.generate(
        title="Breaking News Event",
        summary="A major event just occurred...",
        image_url="",
        category="National",
        source="News Agency",
        language="en",
    )

    # Verify cache key was purged
    assert "feed:test:key" not in fake_redis.store
