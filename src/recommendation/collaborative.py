"""NewsSnap AI - Collaborative Filtering Recommendation Engine (Issue 22).

Builds implicit feedback interaction matrices from user engagement signals
(read=1, like=3, comment=5, share=7), trains Alternating Least Squares (ALS)
latent factor models via the `implicit` library, manages 6-hour periodic retraining,
and provides seamless cold-start fallback to content-based recommendations
for users with fewer than 20 interactions.
"""

from __future__ import annotations

import logging
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import numpy as np
import scipy.sparse as sp

# Set OpenBLAS to single-thread mode before implicit import to prevent threading warnings & overhead
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from implicit.als import AlternatingLeastSquares

from src.recommendation.content_based import (
    COLD_START_THRESHOLD as DEFAULT_COLD_START_THRESHOLD,
)
from src.recommendation.content_based import (
    ContentBasedRecommender,
    UserProfile,
    extract_article_id,
)

logger = logging.getLogger(__name__)

# Default implicit feedback signal weights (Issue 22 Specification)
DEFAULT_CF_SIGNAL_WEIGHTS: dict[str, float] = {
    "read": 1.0,
    "like": 3.0,
    "comment": 5.0,
    "share": 7.0,
    "bookmark": 3.0,
    "view": 0.5,
}

# Retraining interval in hours (6 hours as per acceptance criteria)
DEFAULT_RETRAIN_INTERVAL_HOURS: float = 6.0
DEFAULT_FACTORS: int = 32
DEFAULT_REGULARIZATION: float = 0.05
DEFAULT_ITERATIONS: int = 15
DEFAULT_ALPHA: float = 1.0


@dataclass
class InteractionMatrixResult:
    """Container for the sparse user-article interaction matrix and mappings."""

    matrix: sp.csr_matrix
    user_to_idx: dict[Any, int]
    idx_to_user: dict[int, Any]
    article_to_idx: dict[Any, int]
    idx_to_article: dict[int, Any]
    user_interaction_counts: dict[Any, int]
    total_interactions: int
    user_interactions: dict[Any, list[Any]] = field(default_factory=dict)

    @property
    def num_users(self) -> int:
        return len(self.user_to_idx)

    @property
    def num_articles(self) -> int:
        return len(self.article_to_idx)


def _extract_user_id(record: Any) -> Any:
    """Extract user identifier from dict, model instance, or tuple."""
    if isinstance(record, dict):
        return record.get("user_id") or record.get("uid") or record.get("user")
    if hasattr(record, "user_id"):
        return getattr(record, "user_id")
    if isinstance(record, (list, tuple)) and len(record) >= 2:
        return record[0]
    return getattr(record, "id", None)


def _extract_article_id(record: Any) -> Any:
    """Extract article identifier from dict, model instance, or tuple."""
    if isinstance(record, dict):
        return record.get("article_id") or record.get("id") or record.get("article")
    if hasattr(record, "article_id"):
        return getattr(record, "article_id")
    if isinstance(record, (list, tuple)) and len(record) >= 2:
        return record[1]
    return getattr(record, "id", None)


def _extract_signal_type(record: Any) -> str:
    """Extract interaction type from dict, model instance, or tuple."""
    if isinstance(record, dict):
        t = record.get("type") or record.get("interaction_type") or record.get("event") or "read"
        return str(t).lower().strip()
    if hasattr(record, "type"):
        val = getattr(record, "type")
        if hasattr(val, "value"):
            return str(val.value).lower().strip()
        return str(val).lower().strip()
    if isinstance(record, (list, tuple)):
        if len(record) >= 3:
            val = record[2]
            if isinstance(val, (int, float)):
                return "custom_weight"
            return str(val).lower().strip()
    return "read"


def _extract_weight(record: Any, signal_weights: dict[str, float]) -> float:
    """Extract or calculate numeric signal weight for an interaction."""
    # Check for direct numeric weight in record
    if isinstance(record, dict) and "weight" in record and record["weight"] is not None:
        try:
            return float(record["weight"])
        except (ValueError, TypeError):
            pass
    if isinstance(record, (list, tuple)) and len(record) >= 3:
        if isinstance(record[2], (int, float)):
            return float(record[2])
    if hasattr(record, "weight") and getattr(record, "weight", None) is not None:
        try:
            return float(getattr(record, "weight"))
        except (ValueError, TypeError):
            pass

    # Map signal type to configured weight
    sig_type = _extract_signal_type(record)
    return signal_weights.get(sig_type, 1.0)


def build_interaction_matrix(
    interactions: Sequence[Any] | None = None,
    comments: Sequence[Any] | None = None,
    signal_weights: dict[str, float] | None = None,
) -> InteractionMatrixResult:
    """Construct an implicit feedback sparse matrix (users x articles) from weighted signals.

    Signal weights:
        read: 1.0
        like: 3.0
        comment: 5.0
        share: 7.0
        (and custom mappings)

    Returns:
        InteractionMatrixResult with scipy.sparse.csr_matrix and bidirectional index mappings.
    """
    weights_map = DEFAULT_CF_SIGNAL_WEIGHTS if signal_weights is None else signal_weights

    user_to_idx: dict[Any, int] = {}
    idx_to_user: dict[int, Any] = {}
    article_to_idx: dict[Any, int] = {}
    idx_to_article: dict[int, Any] = {}
    user_interaction_counts: dict[Any, int] = Counter()
    user_interactions_map: dict[Any, list[Any]] = defaultdict(list)
    aggregated_weights: dict[tuple[int, int], float] = defaultdict(float)
    total_interactions = 0

    # 1. Process regular interactions
    if interactions:
        for record in interactions:
            if record is None:
                continue
            uid = _extract_user_id(record)
            aid = _extract_article_id(record)
            if uid is None or aid is None:
                continue

            user_interaction_counts[uid] += 1
            user_interactions_map[uid].append(record)
            total_interactions += 1

            if uid not in user_to_idx:
                idx = len(user_to_idx)
                user_to_idx[uid] = idx
                idx_to_user[idx] = uid
            u_idx = user_to_idx[uid]

            if aid not in article_to_idx:
                idx = len(article_to_idx)
                article_to_idx[aid] = idx
                idx_to_article[idx] = aid
            a_idx = article_to_idx[aid]

            w = _extract_weight(record, weights_map)
            aggregated_weights[(u_idx, a_idx)] += w

    # 2. Process comments (implicit feedback signal weight = 5.0)
    if comments:
        comment_weight = weights_map.get("comment", 5.0)
        for record in comments:
            if record is None:
                continue
            uid = _extract_user_id(record)
            aid = _extract_article_id(record)
            if uid is None or aid is None:
                continue

            user_interaction_counts[uid] += 1
            user_interactions_map[uid].append(record)
            total_interactions += 1

            if uid not in user_to_idx:
                idx = len(user_to_idx)
                user_to_idx[uid] = idx
                idx_to_user[idx] = uid
            u_idx = user_to_idx[uid]

            if aid not in article_to_idx:
                idx = len(article_to_idx)
                article_to_idx[aid] = idx
                idx_to_article[idx] = aid
            a_idx = article_to_idx[aid]

            aggregated_weights[(u_idx, a_idx)] += comment_weight

    num_users = len(user_to_idx)
    num_articles = len(article_to_idx)

    if num_users == 0 or num_articles == 0:
        empty_matrix = sp.csr_matrix((0, 0), dtype=np.float32)
        return InteractionMatrixResult(
            matrix=empty_matrix,
            user_to_idx={},
            idx_to_user={},
            article_to_idx={},
            idx_to_article={},
            user_interaction_counts=dict(user_interaction_counts),
            total_interactions=0,
            user_interactions={},
        )

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []

    for (u_idx, a_idx), val in aggregated_weights.items():
        rows.append(u_idx)
        cols.append(a_idx)
        data.append(float(val))

    matrix = sp.csr_matrix(
        (data, (rows, cols)),
        shape=(num_users, num_articles),
        dtype=np.float32,
    )

    return InteractionMatrixResult(
        matrix=matrix,
        user_to_idx=user_to_idx,
        idx_to_user=idx_to_user,
        article_to_idx=article_to_idx,
        idx_to_article=idx_to_article,
        user_interaction_counts=dict(user_interaction_counts),
        total_interactions=total_interactions,
        user_interactions=dict(user_interactions_map),
    )


class CollaborativeRecommender:
    """Collaborative Filtering Recommender using Implicit Feedback ALS (Issue 22).

    Features:
    - Builds sparse user-article implicit feedback matrix from weighted signals:
      read=1, like=3, comment=5, share=7 (and custom weights).
    - Fits Alternating Least Squares (ALS) latent factor models using the `implicit` library.
    - Cold-start fallback: users with < 20 interactions fall back to content-based recommender.
    - Automated 6-hour retraining lifecycle support.
    - Discovers unexpected connections and cross-category affinities.
    """

    def __init__(
        self,
        factors: int = DEFAULT_FACTORS,
        regularization: float = DEFAULT_REGULARIZATION,
        iterations: int = DEFAULT_ITERATIONS,
        alpha: float = DEFAULT_ALPHA,
        random_state: int | None = 42,
        cold_start_threshold: int = DEFAULT_COLD_START_THRESHOLD,
        retrain_interval_hours: float = DEFAULT_RETRAIN_INTERVAL_HOURS,
        signal_weights: dict[str, float] | None = None,
        content_based_recommender: ContentBasedRecommender | None = None,
    ) -> None:
        """Initialize CollaborativeRecommender.

        Args:
            factors: Number of latent factors for ALS (default: 32).
            regularization: Regularization factor lambda (default: 0.05).
            iterations: Number of ALS iterations (default: 15).
            alpha: Confidence multiplier for positive interactions (default: 1.0).
            random_state: Random seed for factor initialization reproducibility.
            cold_start_threshold: Interaction count below which user is cold start (default: 20).
            retrain_interval_hours: Maximum hours before model requires retraining (default: 6.0).
            signal_weights: Mapping of interaction type to confidence weight.
            content_based_recommender: Optional ContentBasedRecommender instance for cold start.
        """
        self.factors = factors
        self.regularization = regularization
        self.iterations = iterations
        self.alpha = alpha
        self.random_state = random_state
        self.cold_start_threshold = cold_start_threshold
        self.retrain_interval_hours = retrain_interval_hours
        self.signal_weights = dict(DEFAULT_CF_SIGNAL_WEIGHTS if signal_weights is None else signal_weights)

        self.content_based_recommender = content_based_recommender or ContentBasedRecommender()

        # Model state
        self.model: Optional[AlternatingLeastSquares] = None
        self.is_fitted: bool = False
        self.last_trained_at: Optional[datetime] = None

        # Interaction matrix and index mappings
        self._interaction_matrix: Optional[sp.csr_matrix] = None
        self.user_to_idx: dict[Any, int] = {}
        self.idx_to_user: dict[int, Any] = {}
        self.article_to_idx: dict[Any, int] = {}
        self.idx_to_article: dict[int, Any] = {}
        self.user_interaction_counts: dict[Any, int] = {}
        self.user_interactions: dict[Any, list[Any]] = {}
        self.total_interactions: int = 0

    def fit(
        self,
        interactions: Sequence[Any] | None = None,
        comments: Sequence[Any] | None = None,
        show_progress: bool = False,
    ) -> CollaborativeRecommender:
        """Fit the Alternating Least Squares (ALS) model on provided interaction events.

        Args:
            interactions: Sequence of interaction records (dicts, objects, tuples).
            comments: Sequence of comment records.
            show_progress: Whether to show implicit progress bar during fitting.

        Returns:
            self
        """
        matrix_result = build_interaction_matrix(
            interactions=interactions,
            comments=comments,
            signal_weights=self.signal_weights,
        )

        self._interaction_matrix = matrix_result.matrix
        self.user_to_idx = matrix_result.user_to_idx
        self.idx_to_user = matrix_result.idx_to_user
        self.article_to_idx = matrix_result.article_to_idx
        self.idx_to_article = matrix_result.idx_to_article
        self.user_interaction_counts = matrix_result.user_interaction_counts
        self.user_interactions = matrix_result.user_interactions
        self.total_interactions = matrix_result.total_interactions

        if matrix_result.num_users == 0 or matrix_result.num_articles == 0:
            logger.warning("Interaction matrix is empty; ALS model not trained.")
            self.model = None
            self.is_fitted = False
            return self

        # Initialize and fit implicit ALS model
        self.model = AlternatingLeastSquares(
            factors=self.factors,
            regularization=self.regularization,
            alpha=self.alpha,
            iterations=self.iterations,
            random_state=self.random_state,
        )

        self.model.fit(self._interaction_matrix, show_progress=show_progress)
        self.is_fitted = True
        self.last_trained_at = datetime.now(timezone.utc)
        logger.info(
            f"ALS collaborative model fitted successfully on {matrix_result.num_users} users, "
            f"{matrix_result.num_articles} articles ({matrix_result.total_interactions} interactions)."
        )
        return self

    def fit_from_db(self, db: Any, show_progress: bool = False) -> CollaborativeRecommender:
        """Fetch all user interactions and comments from the database and fit the ALS model.

        Args:
            db: SQLAlchemy Session.
            show_progress: Whether to display ALS fitting progress.

        Returns:
            self
        """
        from src.models.interaction import Comment, Interaction

        try:
            interactions = db.query(
                Interaction.user_id,
                Interaction.article_id,
                Interaction.type,
            ).all()
        except Exception as e:
            logger.warning(f"Could not load interactions from database: {e}")
            interactions = []

        try:
            comments = db.query(
                Comment.user_id,
                Comment.article_id,
            ).all()
        except Exception as e:
            logger.warning(f"Could not load comments from database: {e}")
            comments = []

        return self.fit(interactions=interactions, comments=comments, show_progress=show_progress)

    def retrain(
        self,
        interactions: Sequence[Any] | None = None,
        comments: Sequence[Any] | None = None,
        db: Any | None = None,
        show_progress: bool = False,
    ) -> dict[str, Any]:
        """Retrain the ALS model and return training performance metrics.

        Args:
            interactions: Optional in-memory interactions.
            comments: Optional in-memory comments.
            db: Optional SQLAlchemy Session.
            show_progress: Whether to show ALS training progress.

        Returns:
            Dictionary containing retrain execution statistics.
        """
        start_time = time.perf_counter()

        if db is not None and interactions is None and comments is None:
            self.fit_from_db(db, show_progress=show_progress)
        else:
            self.fit(interactions=interactions, comments=comments, show_progress=show_progress)

        elapsed = time.perf_counter() - start_time

        metrics = {
            "num_users": len(self.user_to_idx),
            "num_articles": len(self.article_to_idx),
            "num_interactions": self.total_interactions,
            "duration_seconds": round(elapsed, 4),
            "trained_at": self.last_trained_at.isoformat() if self.last_trained_at else None,
            "is_fitted": self.is_fitted,
        }
        logger.info(f"Collaborative model retrained in {elapsed:.4f}s: {metrics}")
        return metrics

    def should_retrain(self) -> bool:
        """Check if the model requires retraining based on the 6-hour interval policy.

        Returns:
            True if model has never been trained or last_trained_at is older than retrain_interval_hours.
        """
        if not self.is_fitted or self.last_trained_at is None:
            return True
        now = datetime.now(timezone.utc)
        elapsed_seconds = (now - self.last_trained_at).total_seconds()
        return elapsed_seconds >= (self.retrain_interval_hours * 3600.0)

    def is_cold_start(self, user_id: Any) -> bool:
        """Determine if a user qualifies for cold-start fallback (< 20 interactions).

        Args:
            user_id: User identifier.

        Returns:
            True if user has fewer than cold_start_threshold interactions or is not in training set.
        """
        if user_id not in self.user_to_idx:
            return True
        count = self.user_interaction_counts.get(user_id, 0)
        return count < self.cold_start_threshold

    def get_user_interaction_count(self, user_id: Any) -> int:
        """Get the recorded count of interactions for a user."""
        return self.user_interaction_counts.get(user_id, 0)

    def score_articles(
        self,
        user_id: Any,
        candidate_articles: Sequence[Any],
        user_profile: UserProfile | None = None,
        interactions: Sequence[Any] | None = None,
        onboarding_categories: Sequence[str] | None = None,
        article_map: dict[Any, Any] | None = None,
    ) -> dict[Any, float]:
        """Score candidate articles for a user.

        If user has < 20 interactions (cold start) or model is not fitted, falls back
        to ContentBasedRecommender. If user is warm (>= 20 interactions), computes
        collaborative filtering factor dot-product scores (u_i dot v_j), using
        content-based fallback for any unseen candidate articles.

        Args:
            user_id: Target user identifier.
            candidate_articles: Sequence of candidate articles (models, dicts, IDs).
            user_profile: Optional precomputed UserProfile for content fallback.
            interactions: Optional interaction events for content fallback.
            onboarding_categories: Optional user onboarding categories for cold start.
            article_map: Optional mapping from article ID to article object.

        Returns:
            Dictionary mapping article_id -> recommendation score.
        """
        if not candidate_articles:
            return {}

        # 1. Check for Cold Start Fallback (< 20 interactions or model not fitted)
        if not self.is_fitted or self.model is None or self.is_cold_start(user_id):
            return self.content_based_recommender.score_articles(
                user_id=user_id,
                candidate_articles=candidate_articles,
                user_profile=user_profile,
                interactions=interactions,
                onboarding_categories=onboarding_categories,
                article_map=article_map,
            )

        # 2. Warm user scoring via ALS latent factors
        user_idx = self.user_to_idx[user_id]
        user_factor = self.model.user_factors[user_idx]  # shape: (factors,)

        scores: dict[Any, float] = {}
        unseen_candidates: list[Any] = []

        for cand in candidate_articles:
            aid = extract_article_id(cand) if not isinstance(cand, (str, int)) else cand
            if aid in self.article_to_idx:
                a_idx = self.article_to_idx[aid]
                item_factor = self.model.item_factors[a_idx]
                dot_val = float(np.dot(user_factor, item_factor))
                scores[aid] = dot_val
            else:
                unseen_candidates.append(cand)

        # 3. For any unseen articles not in CF training matrix, use content-based score fallback
        if unseen_candidates:
            user_history = interactions if interactions is not None else self.user_interactions.get(user_id)
            cb_scores = self.content_based_recommender.score_articles(
                user_id=user_id,
                candidate_articles=unseen_candidates,
                user_profile=user_profile,
                interactions=user_history,
                onboarding_categories=onboarding_categories,
                article_map=article_map,
            )
            # Normalize or assign CB scores for unseen articles
            for cand in unseen_candidates:
                aid = extract_article_id(cand) if not isinstance(cand, (str, int)) else cand
                scores[aid] = float(cb_scores.get(aid, 0.0))

        return scores

    def recommend(
        self,
        user_id: Any,
        n: int = 10,
        candidate_articles: Sequence[Any] | None = None,
        filter_already_interacted: bool = True,
        interactions: Sequence[Any] | None = None,
        onboarding_categories: Sequence[str] | None = None,
        article_map: dict[Any, Any] | None = None,
    ) -> list[tuple[Any, float]]:
        """Recommend top N articles for a given user.

        For cold-start users (< 20 interactions) or unfitted models, transparently falls
        back to content-based recommendations.
        For warm users (>= 20 interactions), uses ALS latent factor collaborative ranking.

        Args:
            user_id: Target user identifier.
            n: Number of recommendations to produce.
            candidate_articles: Optional explicit pool of candidates to rank.
            filter_already_interacted: Whether to exclude already interacted articles.
            interactions: Optional user interaction history for fallback.
            onboarding_categories: User onboarding categories for cold-start fallback.
            article_map: Optional dictionary of article metadata.

        Returns:
            List of (article_id, score) tuples ranked in descending score order.
        """
        # 1. Cold start fallback
        if not self.is_fitted or self.model is None or self.is_cold_start(user_id):
            if candidate_articles:
                scores = self.content_based_recommender.score_articles(
                    user_id=user_id,
                    candidate_articles=candidate_articles,
                    interactions=interactions,
                    onboarding_categories=onboarding_categories,
                    article_map=article_map,
                )
                sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                return sorted_items[:n]
            return []

        # 2. Warm user: ALS recommendation
        user_idx = self.user_to_idx[user_id]
        user_row = self._interaction_matrix[user_idx] if self._interaction_matrix is not None else None

        if candidate_articles is not None:
            # Score candidate list and pick top N
            scores_dict = self.score_articles(
                user_id=user_id,
                candidate_articles=candidate_articles,
                interactions=interactions,
                onboarding_categories=onboarding_categories,
                article_map=article_map,
            )
            sorted_items = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
            return sorted_items[:n]

        # Use implicit model.recommend
        if user_row is None:
            return []

        try:
            item_indices, raw_scores = self.model.recommend(
                user_idx,
                user_row,
                N=min(n, len(self.article_to_idx)),
                filter_already_liked_items=filter_already_interacted,
            )
            recommendations: list[tuple[Any, float]] = []
            for a_idx, score in zip(item_indices, raw_scores):
                aid = self.idx_to_article.get(int(a_idx))
                if aid is not None:
                    recommendations.append((aid, float(score)))
            return recommendations
        except Exception as e:
            logger.error(f"Error during collaborative recommend: {e}", exc_info=True)
            return []

    def get_similar_articles(self, article_id: Any, n: int = 10) -> list[tuple[Any, float]]:
        """Find the top N most similar articles in the collaborative latent space.

        Args:
            article_id: Target article identifier.
            n: Number of similar articles to retrieve.

        Returns:
            List of (article_id, similarity_score) tuples.
        """
        if not self.is_fitted or self.model is None or article_id not in self.article_to_idx:
            return []

        a_idx = self.article_to_idx[article_id]
        item_indices, raw_scores = self.model.similar_items(
            a_idx,
            N=min(n + 1, len(self.article_to_idx)),
        )

        similar: list[tuple[Any, float]] = []
        for idx, score in zip(item_indices, raw_scores):
            aid = self.idx_to_article.get(int(idx))
            if aid is not None and aid != article_id:
                similar.append((aid, float(score)))
            if len(similar) >= n:
                break
        return similar

    def get_similar_users(self, user_id: Any, n: int = 10) -> list[tuple[Any, float]]:
        """Find the top N most similar users in the collaborative latent space.

        Args:
            user_id: Target user identifier.
            n: Number of similar users to retrieve.

        Returns:
            List of (user_id, similarity_score) tuples.
        """
        if not self.is_fitted or self.model is None or user_id not in self.user_to_idx:
            return []

        u_idx = self.user_to_idx[user_id]
        user_indices, raw_scores = self.model.similar_users(
            u_idx,
            N=min(n + 1, len(self.user_to_idx)),
        )

        similar: list[tuple[Any, float]] = []
        for idx, score in zip(user_indices, raw_scores):
            uid = self.idx_to_user.get(int(idx))
            if uid is not None and uid != user_id:
                similar.append((uid, float(score)))
            if len(similar) >= n:
                break
        return similar


# Global singleton instance
_collaborative_recommender: Optional[CollaborativeRecommender] = None


def get_collaborative_recommender() -> CollaborativeRecommender:
    """Get or initialize the global CollaborativeRecommender instance."""
    global _collaborative_recommender
    if _collaborative_recommender is None:
        _collaborative_recommender = CollaborativeRecommender()
    return _collaborative_recommender
