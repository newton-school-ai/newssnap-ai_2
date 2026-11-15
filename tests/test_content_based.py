"""NewsSnap AI - Content-Based Recommender Tests (Issue 21).

Acceptance Criteria covered:
  AC1 - User profile vector from engagement history
  AC2 - Articles scored by similarity to profile
  AC3 - Recent interactions weighted higher (exponential decay, 3-day half-life)
  AC4 - Cold start uses onboarding preferences until user has 20+ interactions
  AC5 - Category affinity tracker calculates per-category engagement rate
  AC6 - Scoring 1000 articles < 1 second
  AC7 - Database integration with SQLAlchemy models and SQLite in-memory
"""

import time
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.config.settings import Category as CategoryEnum
from src.config.settings import Language
from src.models.article import Article, ArticleEmbedding
from src.models.category import Category
from src.models.interaction import Interaction
from src.models.source import Source
from src.models.user import User, UserPreference
from src.recommendation import (
    ALL_CATEGORIES,
    NUM_CATEGORIES,
    CategoryAffinityTracker,
    ContentBasedRecommender,
    InteractionSignal,
    InteractionType,
    SignalProcessor,
    build_category_vector,
    compute_dwell_time_multiplier,
    compute_interaction_weight,
    compute_recency_weight,
    cosine_similarity,
    normalize_category_name,
)

# ---------------------------------------------------------------------------
# Database Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_engine():
    """Create in-memory SQLite engine for tests."""
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
    ArticleEmbedding.__table__.create(engine)
    Interaction.__table__.create(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Provide a transactional database session rolled back after test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()

    # Seed standard 19 categories
    existing = {c.slug for c in session.query(Category).all()}
    for cat in CategoryEnum:
        if cat.value not in existing:
            session.add(Category(slug=cat.value, name=cat.value.replace("_", " ").title(), is_active=True))
    session.flush()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# AC3: Recency Weighting & Dwell Time Tests
# ---------------------------------------------------------------------------


class TestSignalsAndRecencyWeighting:
    """Tests for signal weighting and 3-day half-life exponential decay."""

    def test_recency_exponential_decay_half_life(self):
        """Verify exact exponential decay at 0, 3, 6, and 9 days."""
        now = datetime.now(timezone.utc)

        # Delta t = 0 days -> 1.0
        w0 = compute_recency_weight(now, reference_time=now, half_life_days=3.0)
        assert pytest.approx(w0, rel=1e-3) == 1.0

        # Delta t = 3 days -> 0.5 (half-life)
        t_3d = now - timedelta(days=3)
        w3 = compute_recency_weight(t_3d, reference_time=now, half_life_days=3.0)
        assert pytest.approx(w3, rel=1e-3) == 0.5

        # Delta t = 6 days -> 0.25 (2 half-lives)
        t_6d = now - timedelta(days=6)
        w6 = compute_recency_weight(t_6d, reference_time=now, half_life_days=3.0)
        assert pytest.approx(w6, rel=1e-3) == 0.25

        # Delta t = 9 days -> 0.125 (3 half-lives)
        t_9d = now - timedelta(days=9)
        w9 = compute_recency_weight(t_9d, reference_time=now, half_life_days=3.0)
        assert pytest.approx(w9, rel=1e-3) == 0.125

    def test_future_timestamp_caps_at_one(self):
        """Future timestamp due to minor server clock skew should cap at 1.0."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(minutes=5)
        w = compute_recency_weight(future, reference_time=now)
        assert w == 1.0

    def test_interaction_signal_weights(self):
        """Verify signal weights hierarchy: share > bookmark > comment > like > read > view."""
        w_share = compute_interaction_weight(InteractionType.SHARE)
        w_bookmark = compute_interaction_weight(InteractionType.BOOKMARK)
        w_comment = compute_interaction_weight(InteractionType.COMMENT)
        w_like = compute_interaction_weight(InteractionType.LIKE)
        w_read = compute_interaction_weight(InteractionType.READ)
        w_view = compute_interaction_weight(InteractionType.VIEW)

        assert w_share == 4.0
        assert w_bookmark == 3.0
        assert w_comment == 2.5
        assert w_like == 2.0
        assert w_read == 1.0
        assert w_view == 0.5
        assert w_share > w_bookmark > w_comment > w_like > w_read > w_view

    def test_dwell_time_multipliers(self):
        """Verify dwell time penalizes bounces (<5s) and rewards deep reads (>60s)."""
        bounce = compute_dwell_time_multiplier(2)
        skimming = compute_dwell_time_multiplier(10)
        standard = compute_dwell_time_multiplier(30)
        deep = compute_dwell_time_multiplier(180)

        assert bounce == 0.3
        assert skimming == 0.7
        assert standard == 1.0
        assert deep == 1.5

    def test_signal_processor_batch(self):
        """SignalProcessor converts raw dicts/models into InteractionSignals."""
        processor = SignalProcessor(half_life_days=3.0)
        now = datetime.now(timezone.utc)

        raw = [
            {"user_id": 1, "article_id": 101, "type": "share", "created_at": now, "category": "sports"},
            {
                "user_id": 1,
                "article_id": 102,
                "type": "read",
                "created_at": now - timedelta(days=3),
                "time_spent_seconds": 90,
                "category": "technology",
            },
        ]

        signals = processor.process_batch(raw, reference_time=now)
        assert len(signals) == 2
        assert signals[0].raw_weight == 4.0
        assert pytest.approx(signals[0].recency_weight, rel=1e-3) == 1.0
        assert signals[0].effective_weight == 4.0

        assert signals[1].raw_weight == 1.0 * 1.125  # read base 1.0 * dwell bonus
        assert pytest.approx(signals[1].recency_weight, rel=1e-3) == 0.5


# ---------------------------------------------------------------------------
# AC1: User Profile Vector & AC5: Category Affinity Tracker
# ---------------------------------------------------------------------------


class TestUserProfileAndAffinity:
    """Tests for user profile vector generation and category affinity tracking."""

    def test_user_profile_vector_normalized(self):
        """Profile vector must be L2-normalized unit vector."""
        rec = ContentBasedRecommender(cold_start_threshold=3)
        now = datetime.now(timezone.utc)

        interactions = [
            {"user_id": 1, "article_id": 1, "type": "like", "created_at": now, "category": "sports"},
            {"user_id": 1, "article_id": 2, "type": "share", "created_at": now, "category": "sports"},
            {"user_id": 1, "article_id": 3, "type": "bookmark", "created_at": now, "category": "technology"},
        ]

        profile = rec.build_user_profile(user_id=1, interactions=interactions, reference_time=now)
        assert not profile.is_cold_start
        assert profile.interaction_count == 3
        assert profile.category_vector.shape == (NUM_CATEGORIES,)

        # Unit norm check
        norm = np.linalg.norm(profile.category_vector)
        assert pytest.approx(norm, rel=1e-4) == 1.0

        # Sports should have higher weight than technology (like 2 + share 4 = 6 vs bookmark 3)
        sports_idx = ALL_CATEGORIES.index("sports")
        tech_idx = ALL_CATEGORIES.index("technology")
        assert profile.category_vector[sports_idx] > profile.category_vector[tech_idx]
        assert profile.category_vector[tech_idx] > 0.0

    def test_category_affinity_proportions(self):
        """Category affinity tracker calculates accurate proportions summing to 1.0."""
        rec = ContentBasedRecommender(cold_start_threshold=2)
        now = datetime.now(timezone.utc)

        interactions = [
            {"user_id": 1, "article_id": 1, "type": "like", "created_at": now, "category": "finance"},  # w = 2.0
            {"user_id": 1, "article_id": 2, "type": "like", "created_at": now, "category": "technology"},  # w = 2.0
        ]

        affinities = rec.get_category_affinity(user_id=1, interactions=interactions, reference_time=now)
        assert "finance" in affinities
        assert "technology" in affinities
        assert pytest.approx(affinities["finance"], rel=1e-3) == 0.5
        assert pytest.approx(affinities["technology"], rel=1e-3) == 0.5
        assert pytest.approx(sum(affinities.values()), rel=1e-3) == 1.0

    def test_top_categories_ranking(self):
        """CategoryAffinityTracker returns top categories ordered by affinity."""
        tracker = CategoryAffinityTracker()
        sig1 = InteractionSignal(1, 10, "share", 4.0, 1.0, 4.0, datetime.now(timezone.utc), category="sports")
        sig2 = InteractionSignal(1, 20, "like", 2.0, 1.0, 2.0, datetime.now(timezone.utc), category="politics")
        sig3 = InteractionSignal(1, 30, "read", 1.0, 1.0, 1.0, datetime.now(timezone.utc), category="technology")

        aff = tracker.compute_affinity([sig1, sig2, sig3])
        tracker.record_user_affinity(1, aff)

        top = tracker.get_top_categories(1, n=2)
        assert len(top) == 2
        assert top[0][0] == "sports"
        assert top[1][0] == "politics"
        assert top[0][1] > top[1][1]

    def test_incremental_profile_update(self):
        """Profile updates incrementally without recomputing entire history from scratch."""
        rec = ContentBasedRecommender(cold_start_threshold=20)
        now = datetime.now(timezone.utc)

        # Initialize with onboarding preferences
        rec.build_user_profile(user_id="inc_user", onboarding_categories=["sports", "technology"])
        initial_profile = rec._profile_cache["inc_user"]
        assert initial_profile.is_cold_start is True
        assert initial_profile.interaction_count == 0

        # Incrementally add a new interaction on finance
        new_event = {"type": "share", "category": "finance", "created_at": now}
        updated_profile = rec.update_profile_incremental(
            user_id="inc_user",
            interaction=new_event,
            reference_time=now,
        )

        assert updated_profile.interaction_count == 1
        fin_idx = ALL_CATEGORIES.index("finance")
        assert updated_profile.category_vector[fin_idx] > 0.0
        assert "finance" in updated_profile.category_affinity
        assert updated_profile.category_affinity["finance"] > 0.0


# ---------------------------------------------------------------------------
# AC2 & AC3: Scoring & Recency Bias
# ---------------------------------------------------------------------------


class TestArticleScoringAndRecency:
    """Tests for cosine similarity scoring and recency impact on recommendations."""

    def test_cosine_similarity_basic(self):
        """Test cosine similarity between identical, orthogonal, and mixed vectors."""
        v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v2 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        v3 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        assert pytest.approx(cosine_similarity(v1, v2), rel=1e-4) == 1.0
        assert pytest.approx(cosine_similarity(v1, v3), rel=1e-4) == 0.0

    def test_articles_scored_by_profile_similarity(self):
        """Articles matching user preference score higher than unrelated ones."""
        rec = ContentBasedRecommender(cold_start_threshold=3)
        now = datetime.now(timezone.utc)

        # User heavily engaged with sports
        interactions = [
            {"user_id": 42, "article_id": 1, "type": "share", "created_at": now, "category": "sports"},
            {"user_id": 42, "article_id": 2, "type": "like", "created_at": now, "category": "sports"},
            {"user_id": 42, "article_id": 3, "type": "read", "created_at": now, "category": "technology"},
        ]

        candidates = [
            {"id": "art_sports", "category": "sports"},
            {"id": "art_tech", "category": "technology"},
            {"id": "art_crime", "category": "crime"},
        ]

        scores = rec.score_articles(user_id=42, candidate_articles=candidates, interactions=interactions)

        assert scores["art_sports"] > scores["art_tech"]
        assert scores["art_tech"] > scores["art_crime"]
        assert scores["art_crime"] == 0.0

    def test_recent_interactions_weighted_higher_in_recommendations(self):
        """Recent interaction (0 days ago) outweighs older interaction (6 days ago)."""
        rec = ContentBasedRecommender(cold_start_threshold=2)
        now = datetime.now(timezone.utc)

        # 6 days ago: user liked sports (recency factor = 0.25 -> effective weight = 2.0 * 0.25 = 0.5)
        # Today: user liked technology (recency factor = 1.0 -> effective weight = 2.0 * 1.0 = 2.0)
        interactions = [
            {
                "user_id": 99,
                "article_id": 1,
                "type": "like",
                "created_at": now - timedelta(days=6),
                "category": "sports",
            },
            {"user_id": 99, "article_id": 2, "type": "like", "created_at": now, "category": "technology"},
        ]

        candidates = [
            {"id": "sports_candidate", "category": "sports"},
            {"id": "tech_candidate", "category": "technology"},
        ]

        scores = rec.score_articles(
            user_id=99,
            candidate_articles=candidates,
            interactions=interactions,
            reference_time=now,
        )

        # Technology must score significantly higher than sports due to recency decay
        assert scores["tech_candidate"] > scores["sports_candidate"]
        # Tech weight was 4x sports weight (2.0 vs 0.5)
        assert scores["tech_candidate"] > 0.8
        assert scores["sports_candidate"] < 0.4

    def test_topic_embedding_hybrid_scoring(self):
        """Scorer blends category similarity and dense topic embedding similarity."""
        rec = ContentBasedRecommender(cold_start_threshold=1, category_weight=0.5, topic_weight=0.5)
        now = datetime.now(timezone.utc)

        dim = 8
        ai_topic_vec = np.zeros(dim, dtype=np.float32)
        ai_topic_vec[0] = 1.0  # AI topic dimension

        gadgets_topic_vec = np.zeros(dim, dtype=np.float32)
        gadgets_topic_vec[1] = 1.0

        article_map = {
            1: {"id": 1, "category": "technology", "embedding": ai_topic_vec},
        }

        interactions = [
            {"user_id": 5, "article_id": 1, "type": "bookmark", "created_at": now, "category": "technology"},
        ]

        candidates = [
            {"id": "tech_ai", "category": "technology", "embedding": ai_topic_vec},  # matches category + topic
            {"id": "tech_gadget", "category": "technology", "embedding": gadgets_topic_vec},  # matches category only
        ]

        scores = rec.score_articles(
            user_id=5,
            candidate_articles=candidates,
            interactions=interactions,
            article_map=article_map,
        )

        assert scores["tech_ai"] > scores["tech_gadget"]
        assert pytest.approx(scores["tech_ai"], rel=1e-2) == 1.0
        assert pytest.approx(scores["tech_gadget"], rel=1e-2) == 0.5


# ---------------------------------------------------------------------------
# AC4: Cold Start Handling
# ---------------------------------------------------------------------------


class TestColdStartHandling:
    """Tests for cold start onboarding preferences (< 20 interactions)."""

    def test_cold_start_uses_onboarding_preferences_zero_interactions(self):
        """User with 0 interactions uses onboarding categories."""
        rec = ContentBasedRecommender(cold_start_threshold=20)

        onboarding_cats = ["politics", "sports", "technology"]
        candidates = [
            {"id": 1, "category": "politics"},
            {"id": 2, "category": "sports"},
            {"id": 3, "category": "technology"},
            {"id": 4, "category": "entertainment"},
            {"id": 5, "category": "education"},
        ]

        scores = rec.score_articles(
            user_id="cold_user_1",
            candidate_articles=candidates,
            interactions=[],
            onboarding_categories=onboarding_cats,
        )

        profile = rec._profile_cache["cold_user_1"]
        assert profile.is_cold_start is True
        assert profile.interaction_count == 0

        # Onboarding categories should score equally high (~1/sqrt(3) ~= 0.577)
        assert scores[1] > 0.5
        assert scores[2] > 0.5
        assert scores[3] > 0.5
        assert pytest.approx(scores[1], rel=1e-2) == scores[2]

        # Non-onboarding categories must score 0.0
        assert scores[4] == 0.0
        assert scores[5] == 0.0

    def test_cold_start_below_threshold_retains_cold_start(self):
        """User with 19 interactions (< 20) is still marked cold start."""
        rec = ContentBasedRecommender(cold_start_threshold=20)
        now = datetime.now(timezone.utc)

        # 19 interactions
        interactions = [
            {"user_id": "user_19", "article_id": i, "type": "read", "created_at": now, "category": "finance"}
            for i in range(19)
        ]

        profile = rec.build_user_profile(
            user_id="user_19",
            interactions=interactions,
            onboarding_categories=["finance", "business", "technology"],
        )

        assert profile.is_cold_start is True
        assert profile.interaction_count == 19

    def test_active_user_exceeding_threshold_exits_cold_start(self):
        """User with 20 interactions exits cold start and uses engagement profile."""
        rec = ContentBasedRecommender(cold_start_threshold=20)
        now = datetime.now(timezone.utc)

        # 20 interactions on 'finance'
        interactions = [
            {"user_id": "active_user", "article_id": i, "type": "like", "created_at": now, "category": "finance"}
            for i in range(20)
        ]

        profile = rec.build_user_profile(
            user_id="active_user",
            interactions=interactions,
            onboarding_categories=["sports", "entertainment"],  # Onboarding was different
        )

        assert profile.is_cold_start is False
        assert profile.interaction_count == 20

        # Profile vector should now reflect finance, NOT onboarding sports/entertainment
        fin_idx = ALL_CATEGORIES.index("finance")
        sports_idx = ALL_CATEGORIES.index("sports")
        assert profile.category_vector[fin_idx] > 0.99
        assert profile.category_vector[sports_idx] == 0.0

    def test_cold_start_without_onboarding_preferences_fallback(self):
        """User with no interactions and no onboarding preferences falls back safely."""
        rec = ContentBasedRecommender(cold_start_threshold=20)
        profile = rec.build_user_profile(user_id="empty_user", interactions=[], onboarding_categories=[])

        assert profile.is_cold_start is True
        assert len(profile.category_affinity) == NUM_CATEGORIES


# ---------------------------------------------------------------------------
# AC6: Performance Benchmark (Scoring 1000 articles < 1 second)
# ---------------------------------------------------------------------------


class TestPerformanceBenchmark:
    """Benchmark tests to guarantee scoring 1000 candidate articles in < 1 second."""

    def test_scoring_1000_articles_under_one_second(self):
        """AC6: Scoring 1000 candidate articles takes strictly less than 1.0 second."""
        rec = ContentBasedRecommender(cold_start_threshold=20)
        now = datetime.now(timezone.utc)

        # Active user with 25 diverse interactions
        interactions = [
            {
                "user_id": "perf_user",
                "article_id": f"art_{i}",
                "type": "like" if i % 2 == 0 else "read",
                "created_at": now - timedelta(hours=i * 2),
                "category": ALL_CATEGORIES[i % NUM_CATEGORIES],
            }
            for i in range(25)
        ]

        # Generate 1000 candidate articles across categories
        candidates = [
            {
                "id": f"candidate_{i}",
                "category": ALL_CATEGORIES[i % NUM_CATEGORIES],
            }
            for i in range(1000)
        ]

        # Warm up profile building
        profile = rec.build_user_profile(user_id="perf_user", interactions=interactions)

        # Time scoring 1000 articles
        start_time = time.perf_counter()
        scores = rec.score_articles(
            user_id="perf_user",
            candidate_articles=candidates,
            user_profile=profile,
        )
        elapsed = time.perf_counter() - start_time

        # Verification
        assert len(scores) == 1000
        assert elapsed < 1.0, f"Scoring 1000 articles took {elapsed:.4f}s, expected < 1.0s"
        # In practice with vectorized numpy, it should take < 0.05s
        assert elapsed < 0.1, f"Expected fast execution under 100ms, took {elapsed:.4f}s"

    def test_scoring_5000_articles_scale(self):
        """Stress test: 5000 articles scored in well under 1 second."""
        rec = ContentBasedRecommender(cold_start_threshold=20)
        now = datetime.now(timezone.utc)

        interactions = [
            {"user_id": 1, "article_id": i, "type": "share", "created_at": now, "category": "sports"} for i in range(25)
        ]
        candidates = [{"id": f"c_{i}", "category": ALL_CATEGORIES[i % NUM_CATEGORIES]} for i in range(5000)]

        start_time = time.perf_counter()
        scores = rec.score_articles(user_id=1, candidate_articles=candidates, interactions=interactions)
        elapsed = time.perf_counter() - start_time

        assert len(scores) == 5000
        assert elapsed < 1.0, f"Scoring 5000 articles took {elapsed:.4f}s, expected < 1.0s"


# ---------------------------------------------------------------------------
# AC7: Database Integration with SQLAlchemy
# ---------------------------------------------------------------------------


class TestDatabaseIntegration:
    """Tests for ContentBasedRecommender querying live SQLAlchemy session."""

    def test_recommender_with_database_session(self, db_session):
        """Verify recommender loads UserPreference and Interactions directly from DB."""
        user_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Create user
        user = User(
            id=user_id,
            email=f"user_{user_id.hex[:6]}@example.com",
            name="DB Test User",
            is_active=True,
            is_onboarded=True,
        )
        db_session.add(user)

        # Create preference (onboarding: sports, technology, business)
        pref = UserPreference(
            user_id=user_id,
            primary_language=Language.ENGLISH,
            categories=["sports", "technology", "business"],
        )
        db_session.add(pref)

        # Create source
        source = Source(
            id=uuid.uuid4(),
            slug="test_source",
            name="Test Source",
            base_url="https://test.com",
            article_list_url="https://test.com/news",
            language=Language.ENGLISH,
        )
        db_session.add(source)

        # Get category IDs
        sports_cat = db_session.query(Category).filter_by(slug="sports").first()
        tech_cat = db_session.query(Category).filter_by(slug="technology").first()
        crime_cat = db_session.query(Category).filter_by(slug="crime").first()

        # Create articles
        art_sports = Article(
            id=uuid.uuid4(),
            title="Sports Article",
            body="Sports content",
            source_id=source.id,
            category_id=sports_cat.id,
            language=Language.ENGLISH,
            source_url="https://test.com/sports/1",
            publish_time=now,
        )
        art_tech = Article(
            id=uuid.uuid4(),
            title="Tech Article",
            body="Tech content",
            source_id=source.id,
            category_id=tech_cat.id,
            language=Language.ENGLISH,
            source_url="https://test.com/tech/1",
            publish_time=now,
        )
        art_crime = Article(
            id=uuid.uuid4(),
            title="Crime Article",
            body="Crime content",
            source_id=source.id,
            category_id=crime_cat.id,
            language=Language.ENGLISH,
            source_url="https://test.com/crime/1",
            publish_time=now,
        )
        db_session.add_all([art_sports, art_tech, art_crime])
        db_session.flush()

        # 1. Cold start test via DB (0 interactions in DB)
        rec = ContentBasedRecommender(db=db_session, cold_start_threshold=20)
        candidates = [art_sports, art_tech, art_crime]
        scores = rec.score_articles(user_id=user_id, candidate_articles=candidates)

        assert scores[art_sports.id] > 0.5
        assert scores[art_tech.id] > 0.5
        assert scores[art_crime.id] == 0.0

        # 2. Add 20 interactions to DB -> Active user
        for _ in range(20):
            db_session.add(
                Interaction(
                    user_id=user_id,
                    article_id=art_sports.id,
                    type="like",
                    time_spent_seconds=60,
                )
            )
        db_session.commit()

        # Re-score: sports should now dominate
        active_scores = rec.score_articles(user_id=user_id, candidate_articles=candidates)
        assert active_scores[art_sports.id] > 0.99
        assert active_scores[art_tech.id] == 0.0


# ---------------------------------------------------------------------------
# Edge Cases & Utility Functions
# ---------------------------------------------------------------------------


class TestEdgeCasesAndUtilities:
    """Tests for edge cases, category normalization, and ranking utilities."""

    def test_normalize_category_name(self):
        """Test diverse category inputs: Enum, string, uppercase, spaced."""
        assert normalize_category_name(CategoryEnum.SPORTS) == "sports"
        assert normalize_category_name("TECHNOLOGY") == "technology"
        assert normalize_category_name("real estate") == "real_estate"
        assert normalize_category_name("real-estate") == "real_estate"
        assert normalize_category_name(None) is None
        assert normalize_category_name("invalid_cat_xyz") is None

    def test_build_category_vector(self):
        """Category vector is 19-dim unit vector with 1.0 at matching index."""
        vec = build_category_vector("sports")
        assert vec.shape == (NUM_CATEGORIES,)
        idx = ALL_CATEGORIES.index("sports")
        assert vec[idx] == 1.0
        assert np.sum(vec) == 1.0
        assert pytest.approx(np.linalg.norm(vec), rel=1e-4) == 1.0

    def test_recommend_returns_top_k_sorted(self):
        """recommend method returns top-k items sorted descending by score."""
        rec = ContentBasedRecommender()
        candidates = [
            {"id": "a", "category": "sports"},
            {"id": "b", "category": "technology"},
            {"id": "c", "category": "politics"},
        ]

        top_recs = rec.recommend(
            user_id="test_user",
            candidate_articles=candidates,
            limit=2,
            onboarding_categories=["sports", "technology"],
        )

        assert len(top_recs) == 2
        # Both sports and technology should be returned with scores > 0
        top_ids = [r[0] for r in top_recs]
        assert "politics" not in top_ids
        assert top_recs[0][1] >= top_recs[1][1]

    def test_empty_candidates_returns_empty_dict(self):
        """Scoring empty candidate list returns empty dict."""
        rec = ContentBasedRecommender()
        scores = rec.score_articles(user_id=1, candidate_articles=[])
        assert scores == {}
