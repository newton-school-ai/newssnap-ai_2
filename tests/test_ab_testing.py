"""NewsSnap AI - Comprehensive Tests for Recommendation Refresh Scheduler and A/B Testing (Issue 24).

Acceptance Criteria:
- AC1: Refresh runs every 30 minutes for active users (APScheduler job registration & interval)
- AC2: Pre-computed feeds in Redis (top 50 per user per language)
- AC3: Cache invalidated on significant interaction (like, bookmark, share, comment)
- AC4: A/B framework assigns consistent experiment groups (deterministic hashing, traffic ratios)
- AC5: Metrics tracked per variant: CTR, time spent, interaction rates, statistical lift
- AC6: 1000 user refresh < 5 minutes (performance benchmark)
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.api.main import app
from src.api.middleware import get_current_user
from src.config.database import get_db
from src.config.settings import Language, ScrapeType
from src.models.article import Article
from src.models.category import Category
from src.models.interaction import Comment, Interaction
from src.models.snap import Snap, SnapTranslation
from src.models.source import Source
from src.models.user import User, UserPreference
from src.recommendation.ab_testing import (
    ABTestManager,
    Experiment,
    ExperimentStatus,
    Variant,
    get_ab_test_manager,
)
from src.recommendation.metrics import (
    MetricsTracker,
    get_metrics_tracker,
)
from src.recommendation.refresh import (
    DEFAULT_FEED_CACHE_TTL_SECONDS,
    DEFAULT_PRECOMPUTE_LIMIT,
    get_active_users,
    precompute_single_user_feed,
    refresh_user_feeds,
)
from src.scheduler.jobs import (
    DEFAULT_RECOMMENDATION_REFRESH_INTERVAL_MINUTES,
    RECOMMENDATION_REFRESH_JOB_ID,
    create_scheduler,
)
from src.utils.cache import (
    build_feed_cache_key,
    clear_cache,
    get_cached_feed,
    invalidate_feed_cache,
    set_cached_feed,
)

# ---------------------------------------------------------------------------
# Database Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shared_engine():
    """Create in-memory SQLite database engine with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create all required tables
    User.__table__.create(engine)
    UserPreference.__table__.create(engine)
    Category.__table__.create(engine)
    Source.__table__.create(engine)
    Article.__table__.create(engine)
    Snap.__table__.create(engine)
    SnapTranslation.__table__.create(engine)
    Interaction.__table__.create(engine)
    Comment.__table__.create(engine)
    return engine


@pytest.fixture
def db_session(shared_engine):
    """Isolated session per test."""
    session_factory = sessionmaker(bind=shared_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def clean_cache_and_ab():
    """Reset Redis/in-memory cache and A/B test managers before each test."""
    clear_cache()
    get_ab_test_manager().clear()
    get_metrics_tracker().reset()
    yield
    clear_cache()
    get_ab_test_manager().clear()
    get_metrics_tracker().reset()


# ---------------------------------------------------------------------------
# Helper: Seed Database with Categories, Sources, Articles, and Snaps
# ---------------------------------------------------------------------------


def seed_articles_and_snaps(db_session, count: int = 15):
    """Seed test articles and snaps across multiple categories."""
    now = datetime.now(timezone.utc)

    # Categories
    cat_tech = db_session.query(Category).filter(Category.slug == "technology").first()
    if not cat_tech:
        cat_tech = Category(name="Technology", slug="technology")
        db_session.add(cat_tech)
    cat_sci = db_session.query(Category).filter(Category.slug == "science").first()
    if not cat_sci:
        cat_sci = Category(name="Science", slug="science")
        db_session.add(cat_sci)
    cat_sports = db_session.query(Category).filter(Category.slug == "sports").first()
    if not cat_sports:
        cat_sports = Category(name="Sports", slug="sports")
        db_session.add(cat_sports)

    # Source
    source = db_session.query(Source).filter(Source.slug == "techcrunch").first()
    if not source:
        source = Source(
            name="TechCrunch",
            slug="techcrunch",
            base_url="https://techcrunch.com",
            article_list_url="https://techcrunch.com/feed",
            scrape_type=ScrapeType.RSS,
        )
        db_session.add(source)

    db_session.commit()

    cats = [cat_tech, cat_sci, cat_sports]
    for i in range(count):
        cat = cats[i % len(cats)]
        art = Article(
            title=f"Article Title {i}",
            body=f"Full content body for article {i}",
            source_url=f"https://example.com/art_ab_{i}_{uuid.uuid4().hex[:6]}",
            category_id=cat.id,
            source_id=source.id,
            publish_time=now - timedelta(hours=i),
            quality_score=0.85,
        )
        db_session.add(art)
        db_session.flush()

        snap = Snap(
            article_id=art.id,
            summary=f"Snap summary for article {i}",
            language=Language.ENGLISH,
        )
        db_session.add(snap)

    db_session.commit()


# ===========================================================================
# AC1: Refresh runs every 30 minutes for active users
# ===========================================================================


class TestAC1SchedulerRegistration:
    """Test AC1: Periodic 30-minute recommendation refresh job in APScheduler."""

    def test_scheduler_registers_30_minute_refresh_job(self):
        """Verify create_scheduler registers recommendation refresh job with 30-minute interval."""
        scheduler = create_scheduler(async_mode=False)
        job = scheduler.get_job(RECOMMENDATION_REFRESH_JOB_ID)

        assert job is not None
        assert "Recommendation Feed Precompute Refresh" in job.name
        # AC1: Verify interval trigger is exactly 30 minutes
        assert job.trigger.interval == timedelta(minutes=DEFAULT_RECOMMENDATION_REFRESH_INTERVAL_MINUTES)
        assert DEFAULT_RECOMMENDATION_REFRESH_INTERVAL_MINUTES == 30

    def test_async_scheduler_registers_30_minute_refresh_job(self):
        """Verify async scheduler also registers the 30-minute refresh job."""
        scheduler = create_scheduler(async_mode=True)
        job = scheduler.get_job(RECOMMENDATION_REFRESH_JOB_ID)

        assert job is not None
        assert job.trigger.interval == timedelta(minutes=30)

    def test_get_active_users_filters_correctly(self, db_session):
        """Verify get_active_users returns only active users (is_active == True)."""
        u_active1 = User(
            email=f"active1_{uuid.uuid4().hex[:6]}@example.com",
            name="Active One",
            is_active=True,
        )
        u_active2 = User(
            email=f"active2_{uuid.uuid4().hex[:6]}@example.com",
            name="Active Two",
            is_active=True,
        )
        u_inactive = User(
            email=f"inactive_{uuid.uuid4().hex[:6]}@example.com",
            name="Inactive User",
            is_active=False,
        )
        db_session.add_all([u_active1, u_active2, u_inactive])
        db_session.commit()

        active = get_active_users(db_session)
        active_ids = {u.id for u in active}

        assert u_active1.id in active_ids
        assert u_active2.id in active_ids
        assert u_inactive.id not in active_ids


# ===========================================================================
# AC2: Pre-computed feeds in Redis (top 50 per user per language)
# ===========================================================================


class TestAC2PrecomputedFeedsInRedis:
    """Test AC2: Pre-computing and caching top 50 feed items in Redis."""

    def test_precompute_single_user_feed_stores_in_redis(self, db_session):
        """Verify precompute_single_user_feed generates top 50 items and stores in cache."""
        seed_articles_and_snaps(db_session, count=15)

        user = User(
            email=f"redis_user_{uuid.uuid4().hex[:6]}@example.com",
            name="Redis User",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        # Precompute feed for English
        feed_items = precompute_single_user_feed(
            user_id=str(user.id),
            language="en",
            db=db_session,
            user=user,
            limit=DEFAULT_PRECOMPUTE_LIMIT,
            ttl_seconds=DEFAULT_FEED_CACHE_TTL_SECONDS,
        )

        assert len(feed_items) > 0
        assert len(feed_items) <= DEFAULT_PRECOMPUTE_LIMIT
        assert DEFAULT_PRECOMPUTE_LIMIT == 50

        # Verify key exists in Redis / cache
        cache_key = build_feed_cache_key(user_id=str(user.id), language="en", categories=None, time_range=None)
        cached = get_cached_feed(cache_key)

        assert cached is not None
        assert len(cached) == len(feed_items)
        assert cached[0]["title"] == feed_items[0]["title"]
        assert cached[0]["snap_id"] == feed_items[0]["snap_id"]

    def test_user_multi_language_feed_precompute(self, db_session):
        """Verify feeds are cached per user per language according to preferences."""
        seed_articles_and_snaps(db_session, count=12)

        user = User(
            email=f"bilingual_{uuid.uuid4().hex[:6]}@example.com",
            name="Bilingual User",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        pref = UserPreference(
            user_id=user.id,
            primary_language=Language.ENGLISH,
            secondary_language=Language.HINDI,
        )
        db_session.add(pref)
        db_session.commit()

        # Run refresh for this user
        result = refresh_user_feeds(db_session, users=[user])

        assert result["total_users"] == 1
        # Two languages: English and Hindi
        assert result["feeds_cached"] == 2

        # Check English cache key
        en_key = build_feed_cache_key(user_id=str(user.id), language="en", categories=None, time_range=None)
        assert get_cached_feed(en_key) is not None

        # Check Hindi cache key
        hi_key = build_feed_cache_key(user_id=str(user.id), language="hi", categories=None, time_range=None)
        assert get_cached_feed(hi_key) is not None


# ===========================================================================
# AC3: Cache invalidated on significant interaction
# ===========================================================================


class TestAC3CacheInvalidation:
    """Test AC3: Cache invalidation on like, bookmark, share, and comment."""

    def test_invalidate_feed_cache_function(self):
        """Verify invalidate_feed_cache removes user feed keys."""
        u1_id = "user_111"
        u2_id = "user_222"

        key_u1_en = build_feed_cache_key(u1_id, "en")
        key_u1_hi = build_feed_cache_key(u1_id, "hi")
        key_u2_en = build_feed_cache_key(u2_id, "en")

        set_cached_feed(key_u1_en, [{"title": "Art 1"}])
        set_cached_feed(key_u1_hi, [{"title": "Art 2"}])
        set_cached_feed(key_u2_en, [{"title": "Art 3"}])

        assert get_cached_feed(key_u1_en) is not None
        assert get_cached_feed(key_u1_hi) is not None
        assert get_cached_feed(key_u2_en) is not None

        # Invalidate only user 1
        deleted = invalidate_feed_cache(u1_id)
        assert deleted >= 2

        assert get_cached_feed(key_u1_en) is None
        assert get_cached_feed(key_u1_hi) is None
        # User 2 cache must remain intact
        assert get_cached_feed(key_u2_en) is not None

    def test_cache_invalidated_on_like_interaction(self, db_session, shared_engine):
        """Verify liking an article invalidates the interacting user's feed cache."""
        seed_articles_and_snaps(db_session, count=5)
        art = db_session.query(Article).first()

        user = User(
            email=f"liker_{uuid.uuid4().hex[:6]}@example.com",
            name="Liker User",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        # Seed precomputed feed in cache
        user_key = build_feed_cache_key(str(user.id), "en")
        set_cached_feed(user_key, [{"title": "Snap 1"}])
        assert get_cached_feed(user_key) is not None

        # Override dependency
        session_factory = sessionmaker(bind=shared_engine)

        def override_get_db():
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        def override_get_current_user():
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user

        client = TestClient(app)
        try:
            resp = client.post(f"/api/articles/{art.id}/like")
            assert resp.status_code == 200
            assert resp.json()["liked"] is True

            # AC3: Verify user's feed cache was invalidated!
            assert get_cached_feed(user_key) is None
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)

    def test_cache_invalidated_on_bookmark_interaction(self, db_session, shared_engine):
        """Verify bookmarking an article invalidates the user's feed cache."""
        seed_articles_and_snaps(db_session, count=5)
        art = db_session.query(Article).first()

        user = User(
            email=f"bookmarker_{uuid.uuid4().hex[:6]}@example.com",
            name="Bookmarker User",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        user_key = build_feed_cache_key(str(user.id), "en")
        set_cached_feed(user_key, [{"title": "Snap 1"}])
        assert get_cached_feed(user_key) is not None

        session_factory = sessionmaker(bind=shared_engine)
        app.dependency_overrides[get_db] = lambda: session_factory()
        app.dependency_overrides[get_current_user] = lambda: user

        client = TestClient(app)
        try:
            resp = client.post(f"/api/articles/{art.id}/bookmark")
            assert resp.status_code == 200
            assert resp.json()["bookmarked"] is True

            # AC3: Cache must be invalidated
            assert get_cached_feed(user_key) is None
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)

    def test_cache_invalidated_on_comment(self, db_session, shared_engine):
        """Verify creating a comment invalidates the user's feed cache."""
        seed_articles_and_snaps(db_session, count=5)
        art = db_session.query(Article).first()

        user = User(
            email=f"commenter_{uuid.uuid4().hex[:6]}@example.com",
            name="Commenter User",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        user_key = build_feed_cache_key(str(user.id), "en")
        set_cached_feed(user_key, [{"title": "Snap 1"}])
        assert get_cached_feed(user_key) is not None

        session_factory = sessionmaker(bind=shared_engine)
        app.dependency_overrides[get_db] = lambda: session_factory()
        app.dependency_overrides[get_current_user] = lambda: user

        client = TestClient(app)
        try:
            resp = client.post(
                f"/api/articles/{art.id}/comments",
                json={"content": "Insightful read on technology!"},
            )
            assert resp.status_code == 200
            # AC3: Cache must be invalidated
            assert get_cached_feed(user_key) is None
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


# ===========================================================================
# AC4: A/B framework assigns consistent experiment groups
# ===========================================================================


class TestAC4ConsistentVariantAssignment:
    """Test AC4: A/B testing framework consistent deterministic assignment."""

    def test_deterministic_assignment_consistency(self):
        """Verify the same user gets the exact same variant across repeated calls."""
        manager = ABTestManager()
        exp = Experiment(
            name="hybrid_weights_exp",
            description="Testing content-heavy vs collab-heavy weights",
            variants=[
                Variant(
                    name="control",
                    traffic_ratio=0.5,
                    parameters={
                        "weights": {
                            "content": 0.40,
                            "collaborative": 0.35,
                            "trending": 0.25,
                        }
                    },
                    is_control=True,
                ),
                Variant(
                    name="treatment_a",
                    traffic_ratio=0.5,
                    parameters={
                        "weights": {
                            "content": 0.60,
                            "collaborative": 0.20,
                            "trending": 0.20,
                        }
                    },
                ),
            ],
            status=ExperimentStatus.RUNNING,
        )
        manager.register_experiment(exp)

        test_user = "user_42_deterministic"

        # Initial assignment
        first_assignment = manager.assign_variant("hybrid_weights_exp", test_user)

        # Call 50 times
        for _ in range(50):
            repeated = manager.assign_variant("hybrid_weights_exp", test_user)
            # AC4: Must be 100% consistent
            assert repeated.variant_name == first_assignment.variant_name
            assert repeated.is_control == first_assignment.is_control
            assert repeated.parameters == first_assignment.parameters

    def test_traffic_ratio_distribution(self):
        """Verify variant assignments over a large user population adhere to traffic ratios."""
        manager = ABTestManager()
        exp = Experiment(
            name="three_variant_test",
            description="50/25/25 split experiment",
            variants=[
                Variant(name="control", traffic_ratio=0.50, is_control=True),
                Variant(name="treatment_1", traffic_ratio=0.25),
                Variant(name="treatment_2", traffic_ratio=0.25),
            ],
            status=ExperimentStatus.RUNNING,
        )
        manager.register_experiment(exp)

        counts = {"control": 0, "treatment_1": 0, "treatment_2": 0}
        total_sample = 5000

        for i in range(total_sample):
            uid = f"user_{i}"
            res = manager.assign_variant("three_variant_test", uid)
            counts[res.variant_name] += 1

        # Check approximate proportions: control ~ 50%, treatment_1 ~ 25%, treatment_2 ~ 25%
        assert 0.46 <= (counts["control"] / total_sample) <= 0.54
        assert 0.22 <= (counts["treatment_1"] / total_sample) <= 0.28
        assert 0.22 <= (counts["treatment_2"] / total_sample) <= 0.28

    def test_inactive_experiment_falls_back_to_control(self):
        """Verify paused or draft experiments safely return control variant."""
        manager = ABTestManager()
        exp = Experiment(
            name="paused_exp",
            description="Paused experiment",
            variants=[
                Variant(
                    name="control",
                    traffic_ratio=0.5,
                    parameters={"mode": "standard"},
                    is_control=True,
                ),
                Variant(
                    name="treatment",
                    traffic_ratio=0.5,
                    parameters={"mode": "experimental"},
                ),
            ],
            status=ExperimentStatus.PAUSED,
        )
        manager.register_experiment(exp)

        res = manager.assign_variant("paused_exp", "user_123")
        assert res.variant_name == "control"
        assert res.is_in_experiment is False
        assert res.parameters == {"mode": "standard"}


# ===========================================================================
# AC5: Metrics tracked per variant: CTR, time spent
# ===========================================================================


class TestAC5MetricsTrackingPerVariant:
    """Test AC5: Metric aggregation, CTR, time spent, and statistical significance."""

    def test_ctr_and_time_spent_tracking(self):
        """Verify CTR and time spent are computed accurately per variant."""
        tracker = MetricsTracker()
        exp_name = "recommendation_v1"

        # Variant Control: 100 impressions, 10 clicks (CTR = 0.10 / 10%), 200 total seconds (avg 2.0s)
        for i in range(100):
            tracker.record_impression(exp_name, "control", user_id=f"u_ctrl_{i}")
        for i in range(10):
            tracker.record_click(exp_name, "control", user_id=f"u_ctrl_{i}")
        tracker.record_time_spent(exp_name, "control", user_id="u_ctrl_0", seconds=200.0)

        # Variant Treatment: 100 impressions, 20 clicks (CTR = 0.20 / 20%), 500 total seconds (avg 5.0s)
        for i in range(100):
            tracker.record_impression(exp_name, "treatment", user_id=f"u_treat_{i}")
        for i in range(20):
            tracker.record_click(exp_name, "treatment", user_id=f"u_treat_{i}")
        tracker.record_time_spent(exp_name, "treatment", user_id="u_treat_0", seconds=500.0)

        ctrl_m = tracker.get_variant_metrics(exp_name, "control")
        treat_m = tracker.get_variant_metrics(exp_name, "treatment")

        # Verify Control Metrics
        assert ctrl_m.impressions == 100
        assert ctrl_m.clicks == 10
        assert pytest.approx(ctrl_m.ctr, 0.001) == 0.10
        assert ctrl_m.total_time_spent_seconds == 200.0
        assert pytest.approx(ctrl_m.avg_time_spent_seconds, 0.001) == 2.0
        assert pytest.approx(ctrl_m.avg_time_spent_per_click_seconds, 0.001) == 20.0

        # Verify Treatment Metrics
        assert treat_m.impressions == 100
        assert treat_m.clicks == 20
        assert pytest.approx(treat_m.ctr, 0.001) == 0.20
        assert treat_m.total_time_spent_seconds == 500.0
        assert pytest.approx(treat_m.avg_time_spent_seconds, 0.001) == 5.0

    def test_experiment_summary_and_lift_calculation(self):
        """Verify comparative lift calculations and hypothesis testing."""
        tracker = MetricsTracker()
        exp_name = "recs_summary_test"

        # Control: 500 impressions, 25 clicks (CTR = 5%)
        for i in range(500):
            tracker.record_impression(exp_name, "control", user_id=f"ctrl_{i}")
        for i in range(25):
            tracker.record_click(exp_name, "control", user_id=f"ctrl_{i}")
        tracker.record_time_spent(exp_name, "control", user_id="ctrl_0", seconds=500.0)  # avg 1.0s

        # Treatment: 500 impressions, 50 clicks (CTR = 10%) -> +100% lift!
        for i in range(500):
            tracker.record_impression(exp_name, "treatment", user_id=f"treat_{i}")
        for i in range(50):
            tracker.record_click(exp_name, "treatment", user_id=f"treat_{i}")
        tracker.record_time_spent(exp_name, "treatment", user_id="treat_0", seconds=1000.0)  # avg 2.0s -> +100% lift

        summary = tracker.get_summary(exp_name, control_variant="control")

        assert summary.experiment_name == exp_name
        assert "treatment" in summary.lift_metrics

        # CTR Lift = ((0.10 - 0.05) / 0.05) * 100 = 100.0%
        assert pytest.approx(summary.lift_metrics["treatment"]["ctr_lift_percent"], 0.1) == 100.0
        # Time Lift = ((2.0 - 1.0) / 1.0) * 100 = 100.0%
        assert pytest.approx(summary.lift_metrics["treatment"]["time_spent_lift_percent"], 0.1) == 100.0

        # Statistical significance: 5% vs 10% on N=500 each is statistically significant (p < 0.05)
        assert summary.p_values["treatment"] < 0.05
        assert summary.is_significant["treatment"] is True


# ===========================================================================
# AC6: 1000 user refresh < 5 minutes
# ===========================================================================


class TestAC6PerformanceBenchmark:
    """Test AC6: High-throughput batch refresh for 1,000 users in < 5 minutes."""

    def test_1000_user_refresh_latency_benchmark(self, db_session):
        """Verify refreshing feeds for 1,000 users completes in less than 5 minutes (300 seconds)."""
        seed_articles_and_snaps(db_session, count=20)

        # Create 1,000 synthetic test users in memory
        test_users = [
            User(
                id=uuid.uuid4(),
                email=f"bench_{i}_{uuid.uuid4().hex[:6]}@example.com",
                name=f"Benchmark User {i}",
                is_active=True,
            )
            for i in range(1000)
        ]

        start_time = time.perf_counter()

        # Run refresh_user_feeds across the 1,000 users
        result = refresh_user_feeds(
            db=db_session,
            users=test_users,
            languages=["en"],
            limit=50,
            max_workers=8,
        )

        duration = time.perf_counter() - start_time

        # AC6 Acceptance Criteria: < 5 minutes (300 seconds)
        assert duration < 300.0, f"1000 user refresh took {duration:.2f}s (exceeded 300s limit)"
        assert result["total_users"] == 1000
        assert result["feeds_cached"] == 1000
        assert result["errors"] == 0

        # Verify a random sample of cached feeds
        sample_user = test_users[42]
        cached = get_cached_feed(build_feed_cache_key(str(sample_user.id), "en"))
        assert cached is not None
        assert len(cached) > 0
        assert len(cached) <= 50
