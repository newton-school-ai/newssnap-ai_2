"""NewsSnap AI - Content-Based Recommendation Engine (Issue 21).

Builds user profile vectors from engagement history with exponential recency decay (3-day half-life),
tracks per-category affinity, falls back to onboarding preferences for cold start (< 20 interactions),
and scores candidate articles using cosine similarity across category and topic vectors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

import numpy as np

from src.config.settings import Category as CategoryEnum
from src.recommendation.signals import (
    DEFAULT_HALF_LIFE_DAYS,
    InteractionSignal,
    SignalProcessor,
)

# Canonical list of 19 content categories in NewsSnap AI
ALL_CATEGORIES: list[str] = [c.value for c in CategoryEnum]
CATEGORY_TO_IDX: dict[str, int] = {cat: idx for idx, cat in enumerate(ALL_CATEGORIES)}
IDX_TO_CATEGORY: dict[int, str] = {idx: cat for idx, cat in enumerate(ALL_CATEGORIES)}
NUM_CATEGORIES: int = len(ALL_CATEGORIES)  # 19

# Cold-start threshold: users with fewer than 20 interactions use onboarding preferences
COLD_START_THRESHOLD: int = 20


def normalize_category_name(category: Any) -> str | None:
    """Normalize a category value (Enum, string slug/name, ID, or model object) to slug."""
    if category is None:
        return None

    # Handle CategoryEnum or objects with .value
    if hasattr(category, "value"):
        val = str(category.value).lower().strip()
        if val in CATEGORY_TO_IDX:
            return val

    # Handle models or objects with .slug
    if hasattr(category, "slug"):
        val = str(category.slug).lower().strip()
        if val in CATEGORY_TO_IDX:
            return val

    # Handle strings
    if isinstance(category, str):
        val = category.lower().strip()
        if val in CATEGORY_TO_IDX:
            return val
        # Handle spaced names like "real estate" -> "real_estate"
        snake_val = val.replace(" ", "_").replace("-", "_")
        if snake_val in CATEGORY_TO_IDX:
            return snake_val

    # Handle integer IDs (1-based from seed data or 0-based)
    if isinstance(category, int):
        if 1 <= category <= NUM_CATEGORIES:
            return ALL_CATEGORIES[category - 1]
        if 0 <= category < NUM_CATEGORIES:
            return ALL_CATEGORIES[category]

    return None


def extract_article_id(article: Any) -> Any:
    """Extract article identifier from dict, model instance, or object."""
    if isinstance(article, dict):
        return article.get("id") if article.get("id") is not None else article.get("article_id")
    return (
        getattr(article, "id", None)
        if getattr(article, "id", None) is not None
        else getattr(article, "article_id", None)
    )


def extract_interaction_article_id(interaction: Any) -> Any:
    """Extract target article identifier from an interaction record."""
    if isinstance(interaction, dict):
        return interaction.get("article_id") if interaction.get("article_id") is not None else interaction.get("id")
    return (
        getattr(interaction, "article_id", None)
        if getattr(interaction, "article_id", None) is not None
        else getattr(interaction, "id", None)
    )


def extract_article_category(article: Any) -> str | None:
    """Extract and normalize category from article dict, model instance, or object."""
    if isinstance(article, dict):
        cat = (
            article.get("category")
            or article.get("category_slug")
            or article.get("category_name")
            or article.get("category_id")
        )
        return normalize_category_name(cat)

    # Check relation or attributes
    cat_obj = getattr(article, "category", None)
    if cat_obj is not None:
        norm = normalize_category_name(cat_obj)
        if norm:
            return norm

    cat_id = getattr(article, "category_id", None)
    if cat_id is not None:
        norm = normalize_category_name(cat_id)
        if norm:
            return norm

    return None


def extract_article_embedding(article: Any) -> np.ndarray | None:
    """Extract dense vector embedding from article dict, model instance, or object."""
    raw_emb = None
    if isinstance(article, dict):
        raw_emb = article.get("embedding")
        if raw_emb is None:
            raw_emb = article.get("topic_vector")
    else:
        # Check article.embedding relationship or attribute
        emb_rel = getattr(article, "embedding", None)
        if emb_rel is not None:
            if hasattr(emb_rel, "embedding"):
                raw_emb = emb_rel.embedding
            else:
                raw_emb = emb_rel
        if raw_emb is None:
            raw_emb = getattr(article, "topic_vector", None)

    if raw_emb is None:
        return None

    try:
        arr = np.asarray(raw_emb, dtype=np.float32).ravel()
        if arr.size == 0:
            return None
        norm = np.linalg.norm(arr)
        if norm > 1e-9:
            return arr / norm
        return arr
    except (ValueError, TypeError):
        return None


def build_category_vector(
    category: Any,
    num_categories: int = NUM_CATEGORIES,
) -> np.ndarray:
    """Build an L2-normalized 19-dimensional category indicator vector."""
    vec = np.zeros(num_categories, dtype=np.float32)
    cat_slug = normalize_category_name(category)
    if cat_slug and cat_slug in CATEGORY_TO_IDX:
        vec[CATEGORY_TO_IDX[cat_slug]] = 1.0
        return vec  # Unit vector since norm is 1.0

    # If category is an iterable of categories (multi-category)
    if isinstance(category, (list, tuple, set)):
        matched = False
        for c in category:
            slug = normalize_category_name(c)
            if slug and slug in CATEGORY_TO_IDX:
                vec[CATEGORY_TO_IDX[slug]] = 1.0
                matched = True
        if matched:
            norm = np.linalg.norm(vec)
            if norm > 1e-9:
                return vec / norm
    return vec


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Compute cosine similarity between two 1D vectors."""
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    dot_product = float(np.dot(vec_a, vec_b))
    sim = dot_product / (norm_a * norm_b)
    return float(max(0.0, min(1.0, sim)))


@dataclass
class UserProfile:
    """User preference profile vector and affinity metrics."""

    user_id: Any
    category_vector: np.ndarray  # shape: (NUM_CATEGORIES,), L2-normalized
    topic_vector: np.ndarray | None  # shape: (D,), L2-normalized or None
    category_affinity: dict[str, float]  # per-category engagement rate (sums to 1.0)
    interaction_count: int
    is_cold_start: bool
    onboarding_categories: list[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    unnormalized_category_vector: np.ndarray | None = None
    category_weights: dict[str, float] = field(default_factory=dict)

    @property
    def vector(self) -> np.ndarray:
        """Alias for category_vector as the primary profile vector."""
        return self.category_vector


class CategoryAffinityTracker:
    """Tracks per-category engagement rate for users."""

    def __init__(self) -> None:
        self._user_affinities: dict[Any, dict[str, float]] = {}

    def compute_affinity(
        self,
        signals: Sequence[InteractionSignal],
        article_categories: dict[Any, str] | None = None,
    ) -> dict[str, float]:
        """Compute normalized per-category engagement rate from interaction signals."""
        if not signals:
            return {}

        cat_weights: dict[str, float] = {}
        cat_map = article_categories or {}

        for sig in signals:
            cat = sig.category or cat_map.get(sig.article_id)
            cat_slug = normalize_category_name(cat)
            if cat_slug:
                cat_weights[cat_slug] = cat_weights.get(cat_slug, 0.0) + sig.effective_weight

        total_weight = sum(cat_weights.values())
        if total_weight <= 1e-9:
            return {}

        return {cat: weight / total_weight for cat, weight in cat_weights.items()}

    def record_user_affinity(self, user_id: Any, affinity: dict[str, float]) -> None:
        """Save computed affinity for user in memory."""
        self._user_affinities[user_id] = dict(affinity)

    def get_affinity(self, user_id: Any) -> dict[str, float]:
        """Get stored affinity for a user."""
        return self._user_affinities.get(user_id, {})

    def get_top_categories(self, user_id: Any, n: int = 5) -> list[tuple[str, float]]:
        """Get top N categories by affinity score for a user."""
        affinities = self.get_affinity(user_id)
        sorted_cats = sorted(affinities.items(), key=lambda x: -x[1])
        return sorted_cats[:n]


class ContentBasedRecommender:
    """Content-based recommendation engine using topic and category similarity."""

    def __init__(
        self,
        db: Any | None = None,
        signal_processor: SignalProcessor | None = None,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
        cold_start_threshold: int = COLD_START_THRESHOLD,
        category_weight: float = 0.6,
        topic_weight: float = 0.4,
    ) -> None:
        self.db = db
        self.half_life_days = float(half_life_days)
        self.cold_start_threshold = int(cold_start_threshold)
        self.category_weight = float(category_weight)
        self.topic_weight = float(topic_weight)

        self.signal_processor = signal_processor or SignalProcessor(
            half_life_days=self.half_life_days,
            adjust_for_dwell=True,
        )
        self.affinity_tracker = CategoryAffinityTracker()
        self._profile_cache: dict[Any, UserProfile] = {}

    def clear_cache(self, user_id: Any | None = None) -> None:
        """Clear user profile cache."""
        if user_id is not None:
            self._profile_cache.pop(user_id, None)
        else:
            self._profile_cache.clear()

    def _fetch_db_interactions(self, user_id: Any) -> list[Any]:
        """Fetch raw user interactions from database session if available."""
        if not self.db:
            return []
        try:
            from src.models.interaction import Interaction

            # Query all interactions for this user ordered by created_at desc
            return self.db.query(Interaction).filter(Interaction.user_id == user_id).all()
        except Exception:
            return []

    def _fetch_db_preferences(self, user_id: Any) -> list[str]:
        """Fetch onboarding category preferences from database session if available."""
        if not self.db:
            return []
        try:
            from src.models.user import UserPreference

            pref = self.db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
            if pref and pref.categories:
                return [str(c) for c in pref.categories]
            return []
        except Exception:
            return []

    def _fetch_db_article_categories(self, article_ids: Sequence[Any]) -> dict[Any, str]:
        """Fetch category slugs for article IDs from database session if available."""
        if not self.db or not article_ids:
            return {}
        try:
            from src.models.article import Article
            from src.models.category import Category

            articles = (
                self.db.query(Article.id, Category.slug)
                .join(Category, Article.category_id == Category.id)
                .filter(Article.id.in_(list(article_ids)))
                .all()
            )
            return {art_id: slug for art_id, slug in articles}
        except Exception:
            return {}

    def build_user_profile(
        self,
        user_id: Any,
        interactions: Sequence[Any] | None = None,
        onboarding_categories: Sequence[str] | None = None,
        reference_time: datetime | None = None,
        article_map: dict[Any, Any] | None = None,
    ) -> UserProfile:
        """Construct user profile vector from engagement history or onboarding preferences.

        Args:
            user_id: User identifier.
            interactions: Optional sequence of interaction records (dicts or ORM models).
                          If omitted and db session is present, queried from DB.
            onboarding_categories: Categories chosen at onboarding (for cold start).
            reference_time: Timestamp to calculate recency decay against (defaults to now).
            article_map: Optional dict mapping article_id to Article object or dict
                         (useful when interactions only store article_id).

        Returns:
            UserProfile containing category_vector, topic_vector, category_affinity, etc.
        """
        raw_interactions = list(interactions) if interactions is not None else self._fetch_db_interactions(user_id)
        total_interactions = len(raw_interactions)

        # Onboarding preferences
        onboard_cats = (
            [normalize_category_name(c) for c in onboarding_categories if normalize_category_name(c)]
            if onboarding_categories is not None
            else [normalize_category_name(c) for c in self._fetch_db_preferences(user_id) if normalize_category_name(c)]
        )

        # Cold start check (< 20 interactions)
        is_cold_start = total_interactions < self.cold_start_threshold

        if is_cold_start:
            # Cold start: use onboarding preferences
            cat_vector = np.zeros(NUM_CATEGORIES, dtype=np.float32)
            cat_affinity: dict[str, float] = {}

            if onboard_cats:
                # Distribute equal preference across chosen onboarding categories
                prob = 1.0 / len(onboard_cats)
                for cat in onboard_cats:
                    if cat in CATEGORY_TO_IDX:
                        idx = CATEGORY_TO_IDX[cat]
                        cat_vector[idx] = 1.0
                        cat_affinity[cat] = prob

                # L2 normalize category vector
                norm = np.linalg.norm(cat_vector)
                if norm > 1e-9:
                    cat_vector = cat_vector / norm
            else:
                # No onboarding preferences provided: uniform fallback
                cat_vector.fill(1.0 / math.sqrt(NUM_CATEGORIES))
                prob = 1.0 / NUM_CATEGORIES
                for cat in ALL_CATEGORIES:
                    cat_affinity[cat] = prob

            profile = UserProfile(
                user_id=user_id,
                category_vector=cat_vector,
                topic_vector=None,
                category_affinity=cat_affinity,
                interaction_count=total_interactions,
                is_cold_start=True,
                onboarding_categories=onboard_cats,
                last_updated=reference_time or datetime.now(timezone.utc),
                unnormalized_category_vector=np.copy(cat_vector),
                category_weights=dict(cat_affinity),
            )
            self.affinity_tracker.record_user_affinity(user_id, cat_affinity)
            self._profile_cache[user_id] = profile
            return profile

        # Active user (>= 20 interactions): build profile from weighted engagement history
        art_map = dict(article_map or {})

        # Process interactions into signals with recency weighting
        signals = self.signal_processor.process_batch(
            raw_interactions,
            reference_time=reference_time,
        )

        # Resolve article category and embedding lookups from DB for missing articles
        missing_ids = [
            sig.article_id for sig in signals if sig.article_id is not None and sig.article_id not in art_map
        ]
        if missing_ids and self.db:
            db_cats = self._fetch_db_article_categories(missing_ids)
            for m_id, slug in db_cats.items():
                if m_id not in art_map:
                    art_map[m_id] = {"id": m_id, "category": slug}

        cat_vector_acc = np.zeros(NUM_CATEGORIES, dtype=np.float32)
        topic_vector_acc: np.ndarray | None = None
        total_topic_weight: float = 0.0

        for sig in signals:
            w = sig.effective_weight
            art = art_map.get(sig.article_id)

            # Category resolution
            cat_slug = sig.category
            if not cat_slug and art:
                cat_slug = extract_article_category(art)

            if cat_slug and cat_slug in CATEGORY_TO_IDX:
                idx = CATEGORY_TO_IDX[cat_slug]
                cat_vector_acc[idx] += w

            # Topic / embedding resolution
            if art:
                emb = extract_article_embedding(art)
                if emb is not None:
                    if topic_vector_acc is None:
                        topic_vector_acc = np.zeros_like(emb, dtype=np.float32)
                    topic_vector_acc += w * emb
                    total_topic_weight += w

        # L2-normalize category vector
        cat_norm = np.linalg.norm(cat_vector_acc)
        if cat_norm > 1e-9:
            final_cat_vector = cat_vector_acc / cat_norm
        else:
            final_cat_vector = np.zeros(NUM_CATEGORIES, dtype=np.float32)

        # L2-normalize topic vector
        final_topic_vector: np.ndarray | None = None
        if topic_vector_acc is not None and total_topic_weight > 1e-9:
            topic_norm = np.linalg.norm(topic_vector_acc)
            if topic_norm > 1e-9:
                final_topic_vector = topic_vector_acc / topic_norm

        # Compute per-category affinity
        art_cat_dict = {aid: extract_article_category(a) for aid, a in art_map.items() if extract_article_category(a)}
        cat_affinity = self.affinity_tracker.compute_affinity(
            signals,
            article_categories=art_cat_dict,
        )
        cat_raw_weights = {
            cat: float(cat_vector_acc[idx]) for cat, idx in CATEGORY_TO_IDX.items() if cat_vector_acc[idx] > 0
        }

        profile = UserProfile(
            user_id=user_id,
            category_vector=final_cat_vector,
            topic_vector=final_topic_vector,
            category_affinity=cat_affinity,
            interaction_count=total_interactions,
            is_cold_start=False,
            onboarding_categories=onboard_cats,
            last_updated=reference_time or datetime.now(timezone.utc),
            unnormalized_category_vector=np.copy(cat_vector_acc),
            category_weights=cat_raw_weights,
        )
        self.affinity_tracker.record_user_affinity(user_id, cat_affinity)
        self._profile_cache[user_id] = profile
        return profile

    def update_profile_incremental(
        self,
        user_id: Any,
        interaction: Any,
        article: Any | None = None,
        reference_time: datetime | None = None,
    ) -> UserProfile:
        """Update user profile incrementally with a single new interaction event.

        Avoids recomputing the profile from scratch across the entire interaction history.
        """
        profile = self._profile_cache.get(user_id)
        if profile is None:
            profile = self.build_user_profile(user_id=user_id, reference_time=reference_time)

        # Process the new interaction
        sig = self.signal_processor.process(interaction, reference_time=reference_time)
        cat_slug = sig.category
        if not cat_slug and article:
            cat_slug = extract_article_category(article)

        new_count = profile.interaction_count + 1
        is_cold = new_count < self.cold_start_threshold

        unnorm = (
            np.copy(profile.unnormalized_category_vector)
            if profile.unnormalized_category_vector is not None
            else np.copy(profile.category_vector)
        )
        cat_weights = dict(profile.category_weights)

        if cat_slug and cat_slug in CATEGORY_TO_IDX:
            idx = CATEGORY_TO_IDX[cat_slug]
            unnorm[idx] += sig.effective_weight
            cat_weights[cat_slug] = cat_weights.get(cat_slug, 0.0) + sig.effective_weight

        norm = np.linalg.norm(unnorm)
        norm_cat_vec = unnorm / norm if norm > 1e-9 else unnorm

        total_w = sum(cat_weights.values())
        new_affinities = (
            {cat: w / total_w for cat, w in cat_weights.items()} if total_w > 1e-9 else dict(profile.category_affinity)
        )

        updated_profile = UserProfile(
            user_id=user_id,
            category_vector=norm_cat_vec,
            topic_vector=profile.topic_vector,
            category_affinity=new_affinities,
            interaction_count=new_count,
            is_cold_start=is_cold,
            onboarding_categories=profile.onboarding_categories,
            last_updated=reference_time or datetime.now(timezone.utc),
            unnormalized_category_vector=unnorm,
            category_weights=cat_weights,
        )
        self.affinity_tracker.record_user_affinity(user_id, new_affinities)
        self._profile_cache[user_id] = updated_profile
        return updated_profile

    def get_category_affinity(
        self,
        user_id: Any,
        interactions: Sequence[Any] | None = None,
        onboarding_categories: Sequence[str] | None = None,
        reference_time: datetime | None = None,
        article_map: dict[Any, Any] | None = None,
        use_cache: bool = False,
    ) -> dict[str, float]:
        """Get per-category engagement rate for a user."""
        profile = self._profile_cache.get(user_id) if use_cache else None
        if profile is None or interactions is not None:
            profile = self.build_user_profile(
                user_id=user_id,
                interactions=interactions,
                onboarding_categories=onboarding_categories,
                reference_time=reference_time,
                article_map=article_map,
            )
        return profile.category_affinity

    def score_articles(
        self,
        user_id: Any,
        candidate_articles: Sequence[Any],
        user_profile: UserProfile | None = None,
        interactions: Sequence[Any] | None = None,
        onboarding_categories: Sequence[str] | None = None,
        reference_time: datetime | None = None,
        article_map: dict[Any, Any] | None = None,
        use_cache: bool = False,
    ) -> dict[Any, float]:
        """Score candidate articles by cosine similarity to the user profile vector.

        Optimized with vectorized NumPy matrix operations to score 1000+ articles in < 1 second.

        Returns:
            dict mapping article_id -> cosine similarity score (in range [0.0, 1.0]).
        """
        if not candidate_articles:
            return {}

        # 1. Resolve user profile
        profile = user_profile
        if profile is None and use_cache:
            profile = self._profile_cache.get(user_id)

        if profile is None:
            profile = self.build_user_profile(
                user_id=user_id,
                interactions=interactions,
                onboarding_categories=onboarding_categories,
                reference_time=reference_time,
                article_map=article_map,
            )

        n_candidates = len(candidate_articles)
        article_ids: list[Any] = []

        # 2. Build candidate category matrix (n_candidates x 19)
        cat_matrix = np.zeros((n_candidates, NUM_CATEGORIES), dtype=np.float32)

        # 3. Build candidate topic matrix (n_candidates x D) if user has topic profile
        has_user_topic = profile.topic_vector is not None
        user_topic_dim = profile.topic_vector.shape[0] if has_user_topic else 0
        topic_matrix = np.zeros((n_candidates, user_topic_dim), dtype=np.float32) if has_user_topic else None
        has_article_embedding = np.zeros(n_candidates, dtype=bool)

        for i, cand in enumerate(candidate_articles):
            art_id = extract_article_id(cand) or i
            article_ids.append(art_id)

            # Category vector
            cat = extract_article_category(cand)
            if cat and cat in CATEGORY_TO_IDX:
                cat_matrix[i, CATEGORY_TO_IDX[cat]] = 1.0
            elif isinstance(cand, dict) and "category_vector" in cand:
                cat_vec = np.asarray(cand["category_vector"], dtype=np.float32)
                if cat_vec.shape == (NUM_CATEGORIES,):
                    norm = np.linalg.norm(cat_vec)
                    cat_matrix[i] = cat_vec / norm if norm > 1e-9 else cat_vec

            # Topic embedding
            if has_user_topic and topic_matrix is not None:
                emb = extract_article_embedding(cand)
                if emb is not None and emb.shape[0] == user_topic_dim:
                    topic_matrix[i] = emb
                    has_article_embedding[i] = True

        # 4. Compute vectorized category cosine similarities
        # Since cat_matrix rows are unit vectors and profile.category_vector is unit vector:
        # cat_scores = cat_matrix @ profile.category_vector
        cat_scores = np.dot(cat_matrix, profile.category_vector)

        # 5. Compute vectorized topic cosine similarities if available
        if has_user_topic and topic_matrix is not None and profile.topic_vector is not None:
            topic_scores = np.dot(topic_matrix, profile.topic_vector)
            # Combine scores: where candidate has embedding, blend category and topic;
            # where candidate lacks embedding, use pure category similarity.
            final_scores = np.where(
                has_article_embedding,
                self.category_weight * cat_scores + self.topic_weight * topic_scores,
                cat_scores,
            )
        else:
            final_scores = cat_scores

        # 6. Clip scores between 0.0 and 1.0
        final_scores = np.clip(final_scores, 0.0, 1.0)

        # Return dict mapping article_id -> float score
        return {article_ids[i]: float(round(final_scores[i], 4)) for i in range(n_candidates)}

    def recommend(
        self,
        user_id: Any,
        candidate_articles: Sequence[Any],
        limit: int = 10,
        user_profile: UserProfile | None = None,
        interactions: Sequence[Any] | None = None,
        onboarding_categories: Sequence[str] | None = None,
        reference_time: datetime | None = None,
        article_map: dict[Any, Any] | None = None,
        use_cache: bool = False,
    ) -> list[tuple[Any, float]]:
        """Get top-N recommended articles ranked by content similarity score."""
        scores = self.score_articles(
            user_id=user_id,
            candidate_articles=candidate_articles,
            user_profile=user_profile,
            interactions=interactions,
            onboarding_categories=onboarding_categories,
            reference_time=reference_time,
            article_map=article_map,
            use_cache=use_cache,
        )
        ranked = sorted(scores.items(), key=lambda item: -item[1])
        return ranked[:limit]
