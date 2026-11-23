"""Tests for Collaborative Filtering Recommender using Implicit Feedback Signals (Issue 22).

Acceptance Criteria:
  AC1 - Interaction matrix from weighted signals (read=1, like=3, comment=5, share=7)
  AC2 - ALS model trains successfully via implicit library
  AC3 - Retrains every 6 hours (lifecycle checks and APScheduler integration)
  AC4 - Different recommendations than content-based (cross-category discovery)
  AC5 - Cold start fallback for < 20 interactions
  AC6 - Training on 10K interactions in < 60 seconds
"""

import time
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import scipy.sparse as sp
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.models.article import Article
from src.models.category import Category
from src.models.interaction import Comment, Interaction
from src.models.user import User
from src.recommendation.collaborative import (
    DEFAULT_CF_SIGNAL_WEIGHTS,
    DEFAULT_COLD_START_THRESHOLD,
    DEFAULT_RETRAIN_INTERVAL_HOURS,
    CollaborativeRecommender,
    InteractionMatrixResult,
    build_interaction_matrix,
    get_collaborative_recommender,
)
from src.recommendation.content_based import ContentBasedRecommender
from src.scheduler.jobs import (
    COLLABORATIVE_RETRAIN_JOB_ID,
    create_scheduler,
)

# ---------------------------------------------------------------------------
# In-Memory Database Fixtures for DB Integration Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite session with required tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(engine)
    Category.__table__.create(engine)
    Article.__table__.create(engine)
    Interaction.__table__.create(engine)
    Comment.__table__.create(engine)

    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# AC1: Interaction Matrix from Weighted Signals
# ---------------------------------------------------------------------------


class TestInteractionMatrix:
    """Tests for building implicit feedback interaction matrix from weighted signals."""

    def test_signal_weights_mapping(self):
        """Verify the exact signal weights required by Issue 22 specification."""
        assert DEFAULT_CF_SIGNAL_WEIGHTS["read"] == 1.0
        assert DEFAULT_CF_SIGNAL_WEIGHTS["like"] == 3.0
        assert DEFAULT_CF_SIGNAL_WEIGHTS["comment"] == 5.0
        assert DEFAULT_CF_SIGNAL_WEIGHTS["share"] == 7.0

    def test_build_interaction_matrix_basic(self):
        """Verify sparse matrix creation and weight aggregation for user-article pairs."""
        interactions = [
            {"user_id": "u1", "article_id": "a1", "type": "read"},  # weight 1
            {"user_id": "u1", "article_id": "a1", "type": "like"},  # weight 3 (sum = 4)
            {"user_id": "u1", "article_id": "a2", "type": "share"},  # weight 7
            {"user_id": "u2", "article_id": "a2", "type": "read"},  # weight 1
            {"user_id": "u2", "article_id": "a3", "type": "like"},  # weight 3
        ]

        result: InteractionMatrixResult = build_interaction_matrix(interactions)

        assert result.num_users == 2
        assert result.num_articles == 3
        assert result.total_interactions == 5
        assert isinstance(result.matrix, sp.csr_matrix)
        assert result.matrix.shape == (2, 3)

        u1_idx = result.user_to_idx["u1"]
        a1_idx = result.article_to_idx["a1"]
        a2_idx = result.article_to_idx["a2"]

        # u1 on a1 should have aggregated weight: 1.0 + 3.0 = 4.0
        assert result.matrix[u1_idx, a1_idx] == 4.0
        # u1 on a2 should have weight 7.0
        assert result.matrix[u1_idx, a2_idx] == 7.0

        # Check interaction counts per user
        assert result.user_interaction_counts["u1"] == 3
        assert result.user_interaction_counts["u2"] == 2

    def test_comments_signal_integration(self):
        """Verify comments from comments table are incorporated with weight 5.0."""
        interactions = [
            {"user_id": "u1", "article_id": "a1", "type": "read"},  # 1.0
        ]
        comments = [
            {"user_id": "u1", "article_id": "a1"},  # comment weight 5.0 -> total 6.0
            {"user_id": "u2", "article_id": "a1"},  # comment weight 5.0
        ]

        result = build_interaction_matrix(interactions=interactions, comments=comments)
        assert result.num_users == 2
        assert result.total_interactions == 3

        u1_idx = result.user_to_idx["u1"]
        u2_idx = result.user_to_idx["u2"]
        a1_idx = result.article_to_idx["a1"]

        assert result.matrix[u1_idx, a1_idx] == 6.0
        assert result.matrix[u2_idx, a1_idx] == 5.0

    def test_empty_interaction_matrix(self):
        """Verify empty inputs yield an empty CSR matrix without raising errors."""
        result = build_interaction_matrix([])
        assert result.num_users == 0
        assert result.num_articles == 0
        assert result.total_interactions == 0
        assert result.matrix.shape == (0, 0)

    def test_tuple_and_object_input_support(self):
        """Verify extraction from tuples and objects with attributes."""

        class MockInteraction:
            def __init__(self, uid, aid, itype):
                self.user_id = uid
                self.article_id = aid
                self.type = itype

        records = [
            ("u1", "a1", "share"),  # tuple format
            MockInteraction("u2", "a2", "like"),  # object format
        ]
        result = build_interaction_matrix(records)
        assert result.num_users == 2
        assert result.num_articles == 2
        assert result.matrix[result.user_to_idx["u1"], result.article_to_idx["a1"]] == 7.0
        assert result.matrix[result.user_to_idx["u2"], result.article_to_idx["a2"]] == 3.0


# ---------------------------------------------------------------------------
# AC2: ALS Model Trains Successfully
# ---------------------------------------------------------------------------


class TestALSModelTraining:
    """Tests for training the Alternating Least Squares (ALS) model via implicit."""

    def test_als_training_success(self):
        """Verify model trains on interaction matrix and populates factors."""
        recommender = CollaborativeRecommender(factors=16, iterations=5, random_state=42)
        interactions = [{"user_id": f"u{i % 5}", "article_id": f"a{i % 8}", "type": "read"} for i in range(40)]

        recommender.fit(interactions)

        assert recommender.is_fitted is True
        assert recommender.model is not None
        assert recommender.last_trained_at is not None
        assert recommender.model.user_factors is not None
        assert recommender.model.item_factors is not None

        # Verify factors dimension
        assert recommender.model.user_factors.shape == (5, 16)
        assert recommender.model.item_factors.shape == (8, 16)

    def test_empty_dataset_handling(self):
        """Verify fitting on empty data does not crash and leaves is_fitted False."""
        recommender = CollaborativeRecommender()
        recommender.fit([])
        assert recommender.is_fitted is False
        assert recommender.model is None

    def test_similar_articles_and_users(self):
        """Verify item-to-item and user-to-user similarity in latent space."""
        # 3 users, 3 articles: u0 & u1 both like a0 and a1; u2 likes a2
        interactions = [
            {"user_id": "u0", "article_id": "a0", "type": "like"},
            {"user_id": "u0", "article_id": "a1", "type": "like"},
            {"user_id": "u1", "article_id": "a0", "type": "like"},
            {"user_id": "u1", "article_id": "a1", "type": "like"},
            {"user_id": "u2", "article_id": "a2", "type": "like"},
        ]
        recommender = CollaborativeRecommender(factors=8, iterations=10, random_state=42)
        recommender.fit(interactions)

        sim_articles = recommender.get_similar_articles("a0", n=2)
        assert len(sim_articles) > 0
        # a1 should be more similar to a0 than a2
        sim_ids = [aid for aid, _ in sim_articles]
        assert "a1" in sim_ids

        sim_users = recommender.get_similar_users("u0", n=2)
        assert len(sim_users) > 0
        u_sim_ids = [uid for uid, _ in sim_users]
        assert "u1" in u_sim_ids


# ---------------------------------------------------------------------------
# AC3: Retrains Every 6 Hours
# ---------------------------------------------------------------------------


class TestRetrainLifecycle:
    """Tests for 6-hour retraining lifecycle and scheduler integration."""

    def test_should_retrain_policy(self):
        """Verify should_retrain triggers initially and after 6 hours."""
        recommender = CollaborativeRecommender(retrain_interval_hours=6.0)

        # Untrained recommender should retrain
        assert recommender.should_retrain() is True

        # Fit model
        recommender.fit([{"user_id": "u1", "article_id": "a1", "type": "read"}])
        assert recommender.should_retrain() is False

        # Simulate 5 hours elapsed (under 6 hours) -> should NOT retrain
        recommender.last_trained_at = datetime.now(timezone.utc) - timedelta(hours=5.0)
        assert recommender.should_retrain() is False

        # Simulate 6.1 hours elapsed -> should retrain
        recommender.last_trained_at = datetime.now(timezone.utc) - timedelta(hours=6.1)
        assert recommender.should_retrain() is True

    def test_retrain_method_metrics(self):
        """Verify retrain method runs and returns performance metrics."""
        recommender = CollaborativeRecommender(factors=8, iterations=3)
        interactions = [
            {"user_id": "u1", "article_id": "a1", "type": "read"},
            {"user_id": "u2", "article_id": "a2", "type": "share"},
        ]

        metrics = recommender.retrain(interactions)
        assert metrics["is_fitted"] is True
        assert metrics["num_users"] == 2
        assert metrics["num_articles"] == 2
        assert metrics["num_interactions"] == 2
        assert metrics["duration_seconds"] >= 0.0
        assert metrics["trained_at"] is not None

    def test_scheduler_registers_6_hour_retrain_job(self):
        """Verify APScheduler registers the 6-hour collaborative retrain job."""
        scheduler = create_scheduler(async_mode=False)
        job = scheduler.get_job(COLLABORATIVE_RETRAIN_JOB_ID)

        assert job is not None
        assert "Collaborative Filtering ALS Retrain" in job.name
        # IntervalTrigger hours should equal 6
        assert job.trigger.interval == timedelta(hours=DEFAULT_RETRAIN_INTERVAL_HOURS)

    def test_retrain_from_db(self, db_session):
        """Verify fit_from_db extracts DB interactions and comments and trains."""
        # Insert test users, articles, interactions, comments
        u1_id = uuid.uuid4()
        u2_id = uuid.uuid4()
        a1_id = uuid.uuid4()
        a2_id = uuid.uuid4()

        int1 = Interaction(user_id=u1_id, article_id=a1_id, type="read")
        int2 = Interaction(user_id=u1_id, article_id=a2_id, type="like")
        com1 = Comment(user_id=u2_id, article_id=a1_id, content="Great article!")

        db_session.add_all([int1, int2, com1])
        db_session.commit()

        recommender = CollaborativeRecommender(factors=8, iterations=5)
        recommender.fit_from_db(db_session)

        assert recommender.is_fitted is True
        assert recommender.total_interactions == 3
        assert recommender.get_user_interaction_count(u1_id) == 2
        assert recommender.get_user_interaction_count(u2_id) == 1


# ---------------------------------------------------------------------------
# AC4: Different Recommendations than Content-Based
# ---------------------------------------------------------------------------


class TestDifferentRecommendationsThanContentBased:
    """Tests that collaborative filtering discovers unexpected cross-category connections."""

    def test_collaborative_discovers_cross_category_unexpected_connections(self):
        """Verify CF recommends articles outside the user's primary category that content-based would not."""
        # Target user: 'alice' has 25 interactions solely in category 'technology'.
        # Articles:
        # - a_tech_1 .. a_tech_5 in 'technology'
        # - a_science_1 in 'science' (breaking quantum discovery)
        # - a_sports_1 in 'sports'

        articles_metadata = {
            f"a_tech_{i}": {"id": f"a_tech_{i}", "category": "technology", "title": f"Tech {i}"} for i in range(1, 10)
        }
        articles_metadata["a_science_1"] = {
            "id": "a_science_1",
            "category": "science",
            "title": "Quantum breakthrough",
        }
        articles_metadata["a_sports_1"] = {
            "id": "a_sports_1",
            "category": "sports",
            "title": "Football Finals",
        }

        # Alice's 25 interactions on technology articles
        alice_interactions = [
            {"user_id": "alice", "article_id": f"a_tech_{i % 5 + 1}", "type": "like"} for i in range(25)
        ]

        # Content-based recommender on Alice:
        cb = ContentBasedRecommender()
        cb_scores = cb.score_articles(
            user_id="alice",
            candidate_articles=list(articles_metadata.values()),
            interactions=alice_interactions,
            article_map=articles_metadata,
        )

        # In content-based, science and sports get 0.0 or near 0.0 score because Alice has 0 science/sports history
        assert cb_scores["a_science_1"] == 0.0
        assert cb_scores["a_tech_1"] > 0.0

        # Now, other tech peers (bob, charlie, david, elena) also interact heavily with Alice's tech articles
        # AND they heavily share/comment on 'a_science_1'
        peer_interactions = []
        for peer in ["bob", "charlie", "david", "elena"]:
            # Peers read tech articles
            for i in range(1, 4):
                peer_interactions.append({"user_id": peer, "article_id": f"a_tech_{i}", "type": "read"})
            # Peers also read and share the science breakthrough article
            peer_interactions.append({"user_id": peer, "article_id": "a_science_1", "type": "share"})
            peer_interactions.append({"user_id": peer, "article_id": "a_science_1", "type": "comment"})

        # Sports peers only interact with sports articles
        for s_peer in ["frank", "george", "harry"]:
            for _ in range(5):
                peer_interactions.append({"user_id": s_peer, "article_id": "a_sports_1", "type": "like"})

        # Train collaborative filtering on Alice + peers
        all_interactions = alice_interactions + peer_interactions
        cf = CollaborativeRecommender(factors=16, iterations=25, random_state=42)
        cf.fit(all_interactions)

        assert cf.is_cold_start("alice") is False

        # Candidates Alice hasn't read yet: a_science_1, a_sports_1
        candidate_pool = [
            articles_metadata["a_science_1"],
            articles_metadata["a_sports_1"],
        ]

        cf_scores = cf.score_articles(
            user_id="alice",
            candidate_articles=candidate_pool,
            article_map=articles_metadata,
        )

        # Collaborative filtering discovers 'a_science_1' through peer co-engagement:
        # CF score for science should be significantly higher than sports (unrelated community)
        assert cf_scores["a_science_1"] > cf_scores["a_sports_1"]

        # Contrast with content-based:
        # In CB: a_science_1 == a_sports_1 == 0.0 (Alice only read tech)
        # In CF: a_science_1 has strong positive latent affinity (> 0.0)
        assert cf_scores["a_science_1"] > 0.0
        assert cb_scores["a_science_1"] == 0.0

        # Verify recommend() produces different recommendations than content-based
        cf_recs = cf.recommend("alice", n=3)
        top_cf_article = cf_recs[0][0]
        # In CF, top recommended unread article is 'a_science_1'
        assert top_cf_article == "a_science_1"
        # In CB, top recommendations are strictly technology articles
        cb_ranked = sorted(cb_scores.items(), key=lambda x: x[1], reverse=True)
        top_cb_article = cb_ranked[0][0]
        assert top_cb_article.startswith("a_tech_")
        assert top_cf_article != top_cb_article


# ---------------------------------------------------------------------------
# AC5: Cold Start Fallback for < 20 Interactions
# ---------------------------------------------------------------------------


class TestColdStartFallback:
    """Tests for cold start fallback (< 20 interactions) to content-based filtering."""

    def test_cold_start_threshold_boundary(self):
        """Verify is_cold_start accurately switches at 20 interactions."""
        recommender = CollaborativeRecommender(cold_start_threshold=DEFAULT_COLD_START_THRESHOLD)

        # 1. Unknown user -> cold start
        assert recommender.is_cold_start("non_existent_user") is True

        # 2. User with 0 interactions -> cold start
        # 3. User with 5 interactions -> cold start
        int_5 = [{"user_id": "u_cold_5", "article_id": f"a{i}", "type": "read"} for i in range(5)]
        # 4. User with 19 interactions -> cold start
        int_19 = [{"user_id": "u_cold_19", "article_id": f"a{i}", "type": "read"} for i in range(19)]
        # 5. User with 20 interactions -> NOT cold start
        int_20 = [{"user_id": "u_warm_20", "article_id": f"a{i}", "type": "read"} for i in range(20)]
        # 6. User with 30 interactions -> NOT cold start
        int_30 = [{"user_id": "u_warm_30", "article_id": f"a{i}", "type": "read"} for i in range(30)]

        recommender.fit(int_5 + int_19 + int_20 + int_30)

        assert recommender.is_cold_start("u_cold_5") is True
        assert recommender.is_cold_start("u_cold_19") is True
        assert recommender.is_cold_start("u_warm_20") is False
        assert recommender.is_cold_start("u_warm_30") is False

    def test_cold_start_score_articles_falls_back_to_content_based(self):
        """Verify cold-start user (<20 interactions) delegates scoring to ContentBasedRecommender."""
        recommender = CollaborativeRecommender()
        interactions = [{"user_id": "u_cold", "article_id": "a1", "type": "read"}]
        recommender.fit(interactions)

        candidates = [
            {"id": "a_tech", "category": "technology"},
            {"id": "a_sports", "category": "sports"},
        ]

        # User is cold-start and onboarding category is 'technology'
        scores = recommender.score_articles(
            user_id="u_cold",
            candidate_articles=candidates,
            onboarding_categories=["technology"],
        )

        # Fallback to content-based onboarding preference: technology should score 1.0, sports 0.0
        assert scores["a_tech"] > scores["a_sports"]
        assert scores["a_tech"] == pytest.approx(1.0, abs=1e-3)
        assert scores["a_sports"] == pytest.approx(0.0, abs=1e-3)

    def test_cold_start_recommend_returns_content_based_recommendations(self):
        """Verify recommend() for cold-start user uses content-based ranking."""
        recommender = CollaborativeRecommender()
        recommender.fit([{"user_id": "u_cold", "article_id": "a1", "type": "read"}])

        candidates = [
            {"id": "a_sports", "category": "sports"},
            {"id": "a_tech", "category": "technology"},
        ]

        recs = recommender.recommend(
            user_id="u_cold",
            n=2,
            candidate_articles=candidates,
            onboarding_categories=["technology"],
        )

        assert len(recs) == 2
        # Tech should be ranked first due to onboarding category fallback
        assert recs[0][0] == "a_tech"
        assert recs[1][0] == "a_sports"

    def test_unseen_candidate_article_in_warm_user_uses_content_fallback(self):
        """Verify unseen candidate articles for warm users seamlessly get content-based scores."""
        # Train warm user (25 interactions)
        warm_interactions = [{"user_id": "warm_user", "article_id": f"art_{i % 5}", "type": "like"} for i in range(25)]
        recommender = CollaborativeRecommender(factors=8, iterations=5, random_state=42)
        recommender.fit(warm_interactions)

        # Candidate pool contains 1 seen article and 1 brand-new unseen article
        candidates = [
            {"id": "art_0", "category": "technology"},
            {"id": "art_unseen_999", "category": "technology"},
        ]

        scores = recommender.score_articles(
            user_id="warm_user",
            candidate_articles=candidates,
            onboarding_categories=["technology"],
        )

        assert "art_0" in scores
        assert "art_unseen_999" in scores
        # Unseen article received a valid fallback score
        assert scores["art_unseen_999"] >= 0.0


# ---------------------------------------------------------------------------
# AC6: Training on 10K Interactions < 60 Seconds
# ---------------------------------------------------------------------------


class TestTrainingPerformance:
    """Benchmark test verifying training on 10,000 interactions finishes in < 60 seconds."""

    def test_training_10k_interactions_under_60_seconds(self):
        """Verify 10,000 synthetic interaction events train in < 60 seconds (Acceptance Criteria 6)."""
        num_users = 250
        num_articles = 1000
        num_interactions = 10000

        np.random.seed(42)
        user_ids = [f"usr_{i}" for i in range(num_users)]
        article_ids = [f"art_{i}" for i in range(num_articles)]
        signal_types = ["read", "like", "comment", "share"]

        # Generate 10,000 synthetic interactions with realistic engagement distribution
        synthetic_interactions = [
            {
                "user_id": user_ids[np.random.randint(0, num_users)],
                "article_id": article_ids[np.random.randint(0, num_articles)],
                "type": np.random.choice(signal_types, p=[0.60, 0.25, 0.10, 0.05]),
            }
            for _ in range(num_interactions)
        ]

        recommender = CollaborativeRecommender(
            factors=32,
            iterations=15,
            regularization=0.05,
            random_state=42,
        )

        start_time = time.perf_counter()
        metrics = recommender.retrain(synthetic_interactions)
        duration = time.perf_counter() - start_time

        # Verify acceptance criteria: < 60 seconds
        assert duration < 60.0, f"Training 10K interactions took {duration:.2f}s (exceeded 60s limit)"
        assert metrics["num_interactions"] == num_interactions
        assert metrics["num_users"] <= num_users
        assert metrics["num_articles"] <= num_articles
        assert metrics["is_fitted"] is True

        # Verify model recommendations work after training on 10K dataset
        sample_user = user_ids[0]
        recs = recommender.recommend(sample_user, n=5)
        assert isinstance(recs, list)
        assert len(recs) <= 5


# ---------------------------------------------------------------------------
# Singleton and Module Function Tests
# ---------------------------------------------------------------------------


def test_get_collaborative_recommender_singleton():
    """Verify get_collaborative_recommender returns persistent singleton instance."""
    rec1 = get_collaborative_recommender()
    rec2 = get_collaborative_recommender()
    assert rec1 is rec2
    assert isinstance(rec1, CollaborativeRecommender)
