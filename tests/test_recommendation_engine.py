"""Tests for Hybrid Recommendation Scorer with Diversity Injection (Issue 23).

Acceptance Criteria:
  AC1 - Blends all signals with configurable weights (content: 0.4, collaborative: 0.35, trending: 0.25)
  AC2 - Recency decay boosts recent articles
  AC3 - 20% diversity picks from new/underrepresented categories
  AC4 - Feed never > 50% single category (filter bubble prevention)
  AC5 - Feed generation < 500ms per user
"""

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.config.settings import Language, ScrapeType
from src.models.article import Article
from src.models.category import Category
from src.models.interaction import Comment, Interaction
from src.models.snap import Snap, SnapTranslation
from src.models.source import Source
from src.models.user import User, UserPreference
from src.recommendation.diversity import (
    DiversityInjector,
    calculate_category_distribution,
)
from src.recommendation.engine import (
    DEFAULT_HYBRID_WEIGHTS,
    RecommendationEngine,
    compute_recency_decay,
    normalize_hybrid_weights,
)

# ---------------------------------------------------------------------------
# In-Memory SQLite Fixtures for Database Integration Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Create isolated SQLite in-memory database with all required models."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    UserPreference.__table__.create(engine)
    Category.__table__.create(engine)
    Source.__table__.create(engine)
    Article.__table__.create(engine)
    Snap.__table__.create(engine)
    SnapTranslation.__table__.create(engine)
    Interaction.__table__.create(engine)
    Comment.__table__.create(engine)

    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# AC1: Blends All Signals with Configurable Weights
# ---------------------------------------------------------------------------


class TestHybridScoringAndWeights:
    """Tests for hybrid score calculation and configurable weights blending."""

    def test_default_weights_values(self):
        """Verify default hybrid weights match Issue 23 specification."""
        assert DEFAULT_HYBRID_WEIGHTS["content"] == 0.40
        assert DEFAULT_HYBRID_WEIGHTS["collaborative"] == 0.35
        assert DEFAULT_HYBRID_WEIGHTS["trending"] == 0.25
        assert sum(DEFAULT_HYBRID_WEIGHTS.values()) == pytest.approx(1.0)

    def test_weight_normalization(self):
        """Verify weights summing to any value normalize to 1.0 while preserving ratios."""
        custom_weights = {"content": 4.0, "collaborative": 3.5, "trending": 2.5}
        normalized = normalize_hybrid_weights(custom_weights)

        assert normalized["content"] == pytest.approx(0.40)
        assert normalized["collaborative"] == pytest.approx(0.35)
        assert normalized["trending"] == pytest.approx(0.25)
        assert sum(normalized.values()) == pytest.approx(1.0)

    def test_blending_signals_formula(self):
        """Verify blended score computes (w_content * Sc + w_collab * Scl + w_trend * St) * decay."""
        engine = RecommendationEngine(weights={"content": 0.40, "collaborative": 0.35, "trending": 0.25})

        now = datetime.now(timezone.utc)
        score = engine.compute_hybrid_score(
            content_score=1.0,
            collab_score=0.5,
            trending_score=0.2,
            publish_time=now,  # decay = 1.0
            now=now,
        )

        expected = (0.40 * 1.0) + (0.35 * 0.5) + (0.25 * 0.2)
        assert score == pytest.approx(expected, abs=1e-4)

    def test_configurable_weights_change_ranking(self):
        """Verify modifying weights shifts the top recommendation based on the boosted signal."""
        engine = RecommendationEngine()
        now = datetime.now(timezone.utc)

        # Article A: High content match, zero collaborative, zero trending
        # Article B: Low content match, high collaborative, zero trending
        # Article C: Low content match, zero collaborative, high trending

        # Case 1: Boost Content (content: 0.8, collab: 0.1, trend: 0.1)
        score_a_content_heavy = engine.compute_hybrid_score(
            content_score=1.0,
            collab_score=0.1,
            trending_score=0.1,
            publish_time=now,
            now=now,
            weights={"content": 0.8, "collaborative": 0.1, "trending": 0.1},
        )
        score_b_content_heavy = engine.compute_hybrid_score(
            content_score=0.1,
            collab_score=1.0,
            trending_score=0.1,
            publish_time=now,
            now=now,
            weights={"content": 0.8, "collaborative": 0.1, "trending": 0.1},
        )
        assert score_a_content_heavy > score_b_content_heavy

        # Case 2: Boost Collaborative (content: 0.1, collab: 0.8, trend: 0.1)
        score_a_collab_heavy = engine.compute_hybrid_score(
            content_score=1.0,
            collab_score=0.1,
            trending_score=0.1,
            publish_time=now,
            now=now,
            weights={"content": 0.1, "collaborative": 0.8, "trending": 0.1},
        )
        score_b_collab_heavy = engine.compute_hybrid_score(
            content_score=0.1,
            collab_score=1.0,
            trending_score=0.1,
            publish_time=now,
            now=now,
            weights={"content": 0.1, "collaborative": 0.8, "trending": 0.1},
        )
        assert score_b_collab_heavy > score_a_collab_heavy

        # Case 3: Boost Trending (content: 0.1, collab: 0.1, trend: 0.8)
        score_c_trending_heavy = engine.compute_hybrid_score(
            content_score=0.1,
            collab_score=0.1,
            trending_score=1.0,
            publish_time=now,
            now=now,
            weights={"content": 0.1, "collaborative": 0.1, "trending": 0.8},
        )
        assert score_c_trending_heavy > score_a_collab_heavy


# ---------------------------------------------------------------------------
# AC2: Recency Decay Boosts Recent Articles
# ---------------------------------------------------------------------------


class TestRecencyDecay:
    """Tests for exponential recency decay boosting recent articles."""

    def test_recency_decay_mathematical_properties(self):
        """Verify exponential decay formula: decay(24h) = 0.5, decay(48h) = 0.25 with 24h half-life."""
        now = datetime.now(timezone.utc)

        # 0 hours old -> decay 1.0
        assert compute_recency_decay(now, now=now, half_life_hours=24.0) == pytest.approx(1.0, abs=1e-3)

        # Exactly 24 hours old -> decay 0.5
        t_24h = now - timedelta(hours=24)
        assert compute_recency_decay(t_24h, now=now, half_life_hours=24.0) == pytest.approx(0.5, abs=1e-3)

        # Exactly 48 hours old -> decay 0.25
        t_48h = now - timedelta(hours=48)
        assert compute_recency_decay(t_48h, now=now, half_life_hours=24.0) == pytest.approx(0.25, abs=1e-3)

        # 72 hours old -> decay 0.125
        t_72h = now - timedelta(hours=72)
        assert compute_recency_decay(t_72h, now=now, half_life_hours=24.0) == pytest.approx(0.125, abs=1e-3)

    def test_recency_decay_boosts_recent_articles_in_hybrid_scoring(self):
        """Two articles with identical content/collab/trending relevance: recent article scores higher."""
        engine = RecommendationEngine()
        now = datetime.now(timezone.utc)

        t_recent = now - timedelta(hours=1)
        t_old = now - timedelta(hours=48)

        # Identical base relevance (0.8, 0.7, 0.5)
        score_recent = engine.compute_hybrid_score(
            content_score=0.8,
            collab_score=0.7,
            trending_score=0.5,
            publish_time=t_recent,
            now=now,
        )

        score_old = engine.compute_hybrid_score(
            content_score=0.8,
            collab_score=0.7,
            trending_score=0.5,
            publish_time=t_old,
            now=now,
        )

        assert score_recent > score_old
        # Ratio should reflect ~47 hour difference
        assert score_recent > (score_old * 3.5)


# ---------------------------------------------------------------------------
# AC3 & AC4: Diversity Injection and Filter Bubble Prevention
# ---------------------------------------------------------------------------


class TestDiversityAndFilterBubblePrevention:
    """Tests for 20% diversity injection and ensuring feed never exceeds 50% single category."""

    def test_twenty_percent_diversity_picks_from_new_categories(self):
        """Verify 20% of feed items come from underrepresented categories."""
        injector = DiversityInjector(diversity_ratio=0.20, max_category_share=0.50)

        # User loves 'technology' (0.5) and 'sports' (0.5). 'science' and 'business' are new/underrepresented (0.0).
        user_affinity = {"technology": 0.5, "sports": 0.5, "science": 0.0, "business": 0.0}

        # Candidate pool: 5 technology, 5 sports, 3 science, 2 business
        candidates = []
        for i in range(5):
            candidates.append((0.95 - (i * 0.01), {"id": f"tech_{i}", "category": "technology"}))
        for i in range(5):
            candidates.append((0.90 - (i * 0.01), {"id": f"sports_{i}", "category": "sports"}))
        for i in range(3):
            candidates.append((0.70 - (i * 0.01), {"id": f"science_{i}", "category": "science"}))
        for i in range(2):
            candidates.append((0.65 - (i * 0.01), {"id": f"biz_{i}", "category": "business"}))

        feed = injector.inject_diversity(
            scored_candidates=candidates,
            user_category_affinity=user_affinity,
            limit=10,
        )

        assert len(feed) == 10
        dist = calculate_category_distribution(feed)

        # Exactly 2 items (20% of 10) must be from underrepresented categories (science / business)
        diverse_items = [it for it in feed if it["category"] in ("science", "business")]
        assert len(diverse_items) == 2
        # Verify no category exceeds 50%
        assert dist.max_category_share <= 0.50

    def test_feed_never_exceeds_50_percent_single_category(self):
        """Verify feed NEVER exceeds 50% from a single category (filter bubble prevention)."""
        injector = DiversityInjector(diversity_ratio=0.20, max_category_share=0.50)

        # Monopolized candidate pool: 35 politics articles (high scores) and 10 articles from other categories
        candidates = []
        for i in range(35):
            candidates.append((0.99 - (i * 0.01), {"id": f"pol_{i}", "category": "politics"}))
        for i in range(5):
            candidates.append((0.60 - (i * 0.01), {"id": f"tech_{i}", "category": "technology"}))
        for i in range(5):
            candidates.append((0.50 - (i * 0.01), {"id": f"sports_{i}", "category": "sports"}))

        # Request feed of 20 items
        feed_20 = injector.inject_diversity(candidates, limit=20)
        assert len(feed_20) == 20
        dist_20 = calculate_category_distribution(feed_20)

        # Max category share must be <= 50% (at most 10 items out of 20)
        assert dist_20.max_category_share <= 0.50
        assert dist_20.category_counts["politics"] <= 10
        assert dist_20.is_bubble_safe is True

        # Request feed of 10 items
        feed_10 = injector.inject_diversity(candidates, limit=10)
        assert len(feed_10) == 10
        dist_10 = calculate_category_distribution(feed_10)

        assert dist_10.max_category_share <= 0.50
        assert dist_10.category_counts["politics"] <= 5
        assert dist_10.is_bubble_safe is True

    def test_interleaved_diversity_distribution(self):
        """Verify diverse picks are interleaved throughout the feed rather than appended at the end."""
        injector = DiversityInjector(diversity_ratio=0.20, max_category_share=0.50)

        candidates = [(0.9, {"id": f"tech_{i}", "category": "technology"}) for i in range(8)] + [
            (0.5, {"id": f"science_{i}", "category": "science"}) for i in range(3)
        ]

        feed = injector.inject_diversity(candidates, limit=10, interleave=True)

        # Diverse items should appear within the first half as well as second half
        categories = [it["category"] for it in feed]
        first_half = categories[:5]
        assert "science" in first_half


# ---------------------------------------------------------------------------
# AC5: Feed Generation < 500ms Per User
# ---------------------------------------------------------------------------


class TestFeedGenerationPerformance:
    """Benchmark test verifying feed generation completes in < 500ms per user."""

    def test_feed_generation_latency_under_500ms(self):
        """Verify hybrid scoring, recency decay, and diversity injection takes < 500ms for 100+ items."""
        now = datetime.now(timezone.utc)
        categories = ["technology", "business", "science", "sports", "entertainment", "health"]

        # Generate 150 candidate articles
        candidates = []
        for i in range(150):
            cat = categories[i % len(categories)]
            pub_time = now - timedelta(hours=(i * 1.5))
            candidates.append(
                {
                    "id": f"art_{i}",
                    "category": cat,
                    "publish_time": pub_time,
                    "quality_score": 0.85,
                }
            )

        user_history = [{"user_id": "bench_user", "article_id": f"art_{i}", "type": "read"} for i in range(25)]

        engine = RecommendationEngine()

        start_time = time.perf_counter()
        ranked = engine.rank_articles_hybrid(
            user_id="bench_user",
            articles=candidates,
            interactions=user_history,
            limit=20,
            apply_diversity=True,
            now=now,
        )
        duration = time.perf_counter() - start_time

        # Acceptance Criteria 5: < 500ms (0.500s)
        assert duration < 0.500, f"Feed generation took {duration:.4f}s (exceeded 500ms limit)"
        assert len(ranked) == 20

        # Verify filter bubble compliance
        dist = calculate_category_distribution(ranked)
        assert dist.max_category_share <= 0.50


# ---------------------------------------------------------------------------
# Database Integration: get_feed() End-to-End
# ---------------------------------------------------------------------------


class TestDatabaseFeedIntegration:
    """End-to-end integration tests using SQLite database."""

    def test_get_feed_database_integration(self, db_session):
        """Verify get_feed executes queries, scores with hybrid blend, and formats standard output."""
        # Setup category and source
        cat_tech = Category(name="Technology", slug="technology")
        cat_sci = Category(name="Science", slug="science")
        cat_sports = Category(name="Sports", slug="sports")
        source = Source(
            name="TechCrunch",
            slug="techcrunch",
            base_url="https://techcrunch.com",
            article_list_url="https://techcrunch.com/feed",
            scrape_type=ScrapeType.RSS,
        )
        db_session.add_all([cat_tech, cat_sci, cat_sports, source])
        db_session.commit()

        # Setup user
        user = User(
            email="testuser@example.com",
            name="Test User",
            hashed_password="hashed_secret",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        now = datetime.now(timezone.utc)

        # Seed 15 articles with snaps (6 tech, 5 science, 4 sports)
        for i in range(15):
            cat = cat_tech if i < 6 else (cat_sci if i < 11 else cat_sports)
            art = Article(
                title=f"Article {i}",
                body=f"Full body text for article {i}",
                source_url=f"https://example.com/art_{i}",
                category_id=cat.id,
                source_id=source.id,
                publish_time=now - timedelta(hours=i * 2),
                quality_score=0.8,
            )
            db_session.add(art)
            db_session.flush()

            snap = Snap(
                article_id=art.id,
                summary=f"Summary of article {i}",
                language=Language.ENGLISH,
            )
            db_session.add(snap)

        db_session.commit()

        engine = RecommendationEngine(db=db_session)
        feed_items = engine.get_feed(
            user=user,
            language="en",
            limit=10,
            db=db_session,
            apply_diversity=True,
        )

        assert len(feed_items) == 10
        # Check standard fields
        for item in feed_items:
            assert "snap_id" in item
            assert "article_id" in item
            assert "title" in item
            assert "summary" in item
            assert "category" in item
            assert "source" in item
            assert "time_ago" in item
            assert "interaction_counts" in item

        # Verify category distribution obeys <= 50% single category rule
        dist = calculate_category_distribution(feed_items)
        assert dist.max_category_share <= 0.50
        assert dist.is_bubble_safe is True
