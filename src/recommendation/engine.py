"""NewsSnap AI - Hybrid Recommendation Engine with Diversity Injection (Issue 23).

Combines all recommendation signals with configurable weights:
- Content-based similarity (default: 0.40)
- Collaborative filtering latent factors (default: 0.35)
- Trending velocity and engagement (default: 0.25)

Applies exponential recency decay to boost newer articles, injects 20% diversity
from underrepresented categories, and prevents filter bubbles by ensuring no single
category exceeds 50% of the generated feed.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.config.settings import Language
from src.models.article import Article
from src.models.category import Category
from src.models.snap import Snap, SnapTranslation
from src.models.user import User
from src.recommendation.collaborative import (
    CollaborativeRecommender,
    get_collaborative_recommender,
)
from src.recommendation.content_based import (
    ContentBasedRecommender,
    UserProfile,
)
from src.recommendation.diversity import (
    DEFAULT_DIVERSITY_RATIO,
    DEFAULT_MAX_CATEGORY_SHARE,
    DiversityInjector,
    extract_item_id,
)
from src.utils.time_utils import format_time_ago, parse_time_range

logger = logging.getLogger(__name__)

# Default hybrid signal weights (Issue 23 Specification)
DEFAULT_HYBRID_WEIGHTS: dict[str, float] = {
    "content": 0.40,
    "collaborative": 0.35,
    "trending": 0.25,
}

# Default recency half-life in hours (24 hours)
DEFAULT_RECENCY_HALF_LIFE_HOURS: float = 24.0


def normalize_hybrid_weights(weights: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Normalize hybrid scoring weights to sum to 1.0.

    Args:
        weights: Dictionary mapping signal names ('content', 'collaborative', 'trending') to weights.

    Returns:
        Normalized dictionary of weights summing to 1.0.
    """
    if not weights:
        return dict(DEFAULT_HYBRID_WEIGHTS)

    content_w = float(weights.get("content", DEFAULT_HYBRID_WEIGHTS["content"]))
    collab_w = float(weights.get("collaborative", weights.get("collab", DEFAULT_HYBRID_WEIGHTS["collaborative"])))
    trending_w = float(weights.get("trending", DEFAULT_HYBRID_WEIGHTS["trending"]))

    total = content_w + collab_w + trending_w
    if total > 1e-9:
        return {
            "content": content_w / total,
            "collaborative": collab_w / total,
            "trending": trending_w / total,
        }
    return dict(DEFAULT_HYBRID_WEIGHTS)


def compute_recency_decay(
    publish_time: Optional[datetime],
    now: Optional[datetime] = None,
    half_life_hours: float = DEFAULT_RECENCY_HALF_LIFE_HOURS,
) -> float:
    """Calculate exponential recency decay factor: decay(dt) = 2^(-dt / half_life).

    Args:
        publish_time: Publication timestamp of the article.
        now: Reference timestamp (defaults to current UTC time).
        half_life_hours: Elapsed hours at which decay reaches 0.5 (default: 24.0).

    Returns:
        Decay multiplier in (0.0, 1.0]. Returns 1.0 for brand-new or future articles.
    """
    if publish_time is None:
        return 1.0

    current_time = now or datetime.now(timezone.utc)
    if publish_time.tzinfo is None:
        publish_time = publish_time.replace(tzinfo=timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    delta_seconds = max(0.0, (current_time - publish_time).total_seconds())
    delta_hours = delta_seconds / 3600.0

    if half_life_hours <= 0:
        return 1.0

    decay = math.pow(2.0, -delta_hours / half_life_hours)
    return max(0.0, min(1.0, decay))


class RecommendationEngine:
    """Hybrid Recommendation Engine with Diversity Injection and Filter Bubble Prevention (Issue 23).

    Blends multiple signals:
    - Content-Based (0.40): User profile cosine similarity and category affinity.
    - Collaborative Filtering (0.35): ALS implicit feedback matrix latent factors.
    - Trending (0.25): Interaction velocity and recent community engagement.

    Enforces:
    - Exponential recency decay for older articles.
    - 20% diversity injection from underrepresented categories.
    - Filter bubble prevention (feed never > 50% single category).
    - Sub-500ms feed generation latency per user.
    """

    def __init__(
        self,
        db: Optional[Session] = None,
        content_scorer: Optional[ContentBasedRecommender] = None,
        collaborative_scorer: Optional[CollaborativeRecommender] = None,
        diversity_injector: Optional[DiversityInjector] = None,
        weights: Optional[Dict[str, float]] = None,
        recency_half_life_hours: float = DEFAULT_RECENCY_HALF_LIFE_HOURS,
    ) -> None:
        """Initialize the hybrid recommendation engine.

        Args:
            db: Optional SQLAlchemy Session.
            content_scorer: Optional ContentBasedRecommender instance.
            collaborative_scorer: Optional CollaborativeRecommender instance.
            diversity_injector: Optional DiversityInjector instance.
            weights: Optional custom dictionary of signal weights.
            recency_half_life_hours: Half-life in hours for recency decay.
        """
        self.db = db
        self.content_scorer = content_scorer or ContentBasedRecommender()
        self.collaborative_scorer = collaborative_scorer or get_collaborative_recommender()
        self.diversity_injector = diversity_injector or DiversityInjector(
            diversity_ratio=DEFAULT_DIVERSITY_RATIO,
            max_category_share=DEFAULT_MAX_CATEGORY_SHARE,
        )
        self.weights = normalize_hybrid_weights(weights)
        self.recency_half_life_hours = recency_half_life_hours

    def _resolve_weights(self, weights: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """Resolve and normalize active scoring weights."""
        if weights:
            return normalize_hybrid_weights(weights)
        return self.weights

    def compute_hybrid_score(
        self,
        content_score: float,
        collab_score: float,
        trending_score: float,
        publish_time: Optional[datetime] = None,
        now: Optional[datetime] = None,
        weights: Optional[Dict[str, float]] = None,
        recency_half_life_hours: Optional[float] = None,
    ) -> float:
        """Compute blended hybrid recommendation score with recency decay.

        Formula:
            base_score = (w_content * content_score) + (w_collab * collab_score) + (w_trending * trending_score)
            final_score = base_score * recency_decay(publish_time)

        Args:
            content_score: Content-based relevance score in [0, 1].
            collab_score: Collaborative filtering score in [0, 1].
            trending_score: Trending engagement score in [0, 1].
            publish_time: Timestamp when article was published.
            now: Current reference timestamp.
            weights: Optional custom signal weights override.
            recency_half_life_hours: Optional recency half-life override.

        Returns:
            Final decayed hybrid score.
        """
        w = self._resolve_weights(weights)
        half_life = recency_half_life_hours or self.recency_half_life_hours

        # 1. Base blended score
        base_score = (
            (w["content"] * float(content_score))
            + (w["collaborative"] * float(collab_score))
            + (w["trending"] * float(trending_score))
        )

        # 2. Recency decay multiplier
        recency = compute_recency_decay(publish_time, now=now, half_life_hours=half_life)

        return float(base_score * recency)

    def _calculate_trending_score(self, article: Any) -> float:
        """Compute normalized trending engagement score in range [0.0, 1.0]."""
        interactions = getattr(article, "interactions", []) or []
        likes = sum(1 for i in interactions if getattr(i, "type", None) == "like")
        comments_from_int = sum(1 for i in interactions if getattr(i, "type", None) == "comment")
        comments_from_table = len(article.comments) if getattr(article, "comments", None) else 0
        comments = max(comments_from_int, comments_from_table)
        shares = sum(1 for i in interactions if getattr(i, "type", None) == "share")
        bookmarks = sum(1 for i in interactions if getattr(i, "type", None) == "bookmark")
        views = sum(1 for i in interactions if getattr(i, "type", None) == "view")

        # Engagement points: share=5.0, comment=4.0, like=3.0, bookmark=2.0, view=0.5
        points = (shares * 5.0) + (comments * 4.0) + (likes * 3.0) + (bookmarks * 2.0) + (views * 0.5)

        # Logarithmic normalization into [0.0, 1.0] (50 points maps to ~1.0)
        norm_score = math.log1p(points) / math.log1p(50.0)
        return min(1.0, max(0.0, norm_score))

    def score_candidates_hybrid(
        self,
        user_id: Any,
        candidates: Sequence[Any],
        user: Optional[User] = None,
        user_profile: Optional[UserProfile] = None,
        interactions: Optional[Sequence[Any]] = None,
        onboarding_categories: Optional[Sequence[str]] = None,
        now: Optional[datetime] = None,
        weights: Optional[Dict[str, float]] = None,
        article_map: Optional[Dict[Any, Any]] = None,
    ) -> List[Tuple[float, Any]]:
        """Score a list of candidate items using the hybrid blend with recency decay.

        Args:
            user_id: Target user identifier.
            candidates: Sequence of items (Article models, Snap-Article tuples, or dicts).
            user: Optional User model.
            user_profile: Optional precomputed UserProfile.
            interactions: Optional sequence of interaction records for the user.
            onboarding_categories: User onboarding categories for cold-start fallback.
            now: Current reference timestamp.
            weights: Optional custom signal weights override.
            article_map: Optional dictionary of article metadata.

        Returns:
            List of (hybrid_score, item) tuples sorted in descending order of score.
        """
        if not candidates:
            return []

        current_time = now or datetime.now(timezone.utc)
        resolved_weights = self._resolve_weights(weights)

        # Extract articles from candidates
        clean_articles: list[Any] = []
        for cand in candidates:
            if (
                isinstance(cand, (list, tuple, Sequence))
                and not isinstance(cand, (str, bytes, dict))
                and len(cand) >= 2
            ):
                # Format: (snap, article)
                clean_articles.append(cand[1])
            else:
                clean_articles.append(cand)

        # 1. Batched Content-based scores
        cb_scores: dict[Any, float] = {}
        try:
            cb_scores = self.content_scorer.score_articles(
                user_id=user_id,
                candidate_articles=clean_articles,
                user_profile=user_profile,
                interactions=interactions,
                onboarding_categories=onboarding_categories,
                article_map=article_map,
            )
        except Exception as e:
            logger.warning(f"Error computing content-based scores: {e}")

        # 2. Batched Collaborative filtering scores
        cf_scores: dict[Any, float] = {}
        try:
            cf_scores = self.collaborative_scorer.score_articles(
                user_id=user_id,
                candidate_articles=clean_articles,
                user_profile=user_profile,
                interactions=interactions,
                onboarding_categories=onboarding_categories,
                article_map=article_map,
            )
        except Exception as e:
            logger.warning(f"Error computing collaborative scores: {e}")

        # Normalize CF scores into [0, 1] range if present
        if cf_scores:
            cf_vals = list(cf_scores.values())
            min_v = min(cf_vals)
            max_v = max(cf_vals)
            range_v = max_v - min_v
            if range_v > 1e-6:
                cf_scores = {aid: (v - min_v) / range_v for aid, v in cf_scores.items()}
            else:
                cf_scores = {aid: max(0.0, min(1.0, v)) for aid, v in cf_scores.items()}

        # 3. Blend hybrid score for each candidate with recency decay
        scored_candidates: list[tuple[float, Any]] = []

        for cand, art in zip(candidates, clean_articles):
            aid = extract_item_id(art)

            s_content = float(cb_scores.get(aid, 0.0))
            s_collab = float(cf_scores.get(aid, s_content))  # Fallback to content if collab absent
            s_trending = self._calculate_trending_score(art)

            # Determine publication timestamp
            pub_time = getattr(art, "publish_time", None)
            if (
                not pub_time
                and isinstance(cand, (list, tuple, Sequence))
                and not isinstance(cand, (str, bytes, dict))
                and len(cand) >= 1
            ):
                snap_obj = cand[0]
                pub_time = getattr(snap_obj, "created_at", None)
            if not pub_time and isinstance(art, dict):
                pub_time = art.get("publish_time") or art.get("created_at")

            # Quality factor if present
            quality = getattr(art, "quality_score", None)
            if quality is None and isinstance(art, dict):
                quality = art.get("quality_score")
            q_factor = float(quality) if quality is not None else 1.0

            hybrid = self.compute_hybrid_score(
                content_score=s_content,
                collab_score=s_collab,
                trending_score=s_trending,
                publish_time=pub_time,
                now=current_time,
                weights=resolved_weights,
            )

            final_score = hybrid * max(0.1, q_factor)
            scored_candidates.append((final_score, cand))

        # Sort descending by score, tie-breaking by publication time
        def sort_key(entry: tuple[float, Any]) -> tuple[float, float]:
            score_val, item = entry
            art_obj = (
                item[1]
                if isinstance(item, (list, tuple, Sequence))
                and not isinstance(item, (str, bytes, dict))
                and len(item) >= 2
                else item
            )
            dt = getattr(art_obj, "publish_time", None) or getattr(art_obj, "created_at", None)
            pub_ts = 0.0
            if dt:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                pub_ts = dt.timestamp()
            return (score_val, pub_ts)

        scored_candidates.sort(key=sort_key, reverse=True)
        return scored_candidates

    def rank_articles_hybrid(
        self,
        user_id: Any,
        articles: Sequence[Any],
        user: Optional[User] = None,
        interactions: Optional[Sequence[Any]] = None,
        onboarding_categories: Optional[Sequence[str]] = None,
        weights: Optional[Dict[str, float]] = None,
        limit: int = 20,
        apply_diversity: bool = True,
        now: Optional[datetime] = None,
        article_map: Optional[Dict[Any, Any]] = None,
    ) -> List[Any]:
        """Rank an arbitrary sequence of articles using hybrid scoring and diversity injection.

        Args:
            user_id: Target user identifier.
            articles: Sequence of articles (models, dicts).
            user: Optional User model.
            interactions: Optional sequence of user interaction history.
            onboarding_categories: Optional onboarding category preferences.
            weights: Optional custom signal weights override.
            limit: Maximum items to return.
            apply_diversity: Whether to apply 20% diversity injection and 50% category cap.
            now: Reference timestamp.
            article_map: Optional dictionary of article metadata.

        Returns:
            List of ranked article items.
        """
        start_time = time.perf_counter()

        scored = self.score_candidates_hybrid(
            user_id=user_id,
            candidates=articles,
            user=user,
            interactions=interactions,
            onboarding_categories=onboarding_categories,
            now=now,
            weights=weights,
            article_map=article_map,
        )

        if not apply_diversity:
            ranked = [it for _, it in scored[:limit]]
        else:
            # Extract category affinity if available
            affinity = None
            if interactions:
                try:
                    affinity = self.content_scorer.get_category_affinity(
                        user_id=user_id,
                        interactions=interactions,
                        article_map=article_map,
                    )
                except Exception:
                    pass

            ranked = self.diversity_injector.inject_diversity(
                scored_candidates=scored,
                user_category_affinity=affinity,
                limit=limit,
                interleave=True,
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.debug(f"rank_articles_hybrid generated {len(ranked)} items in {elapsed_ms:.2f}ms")
        return ranked

    def get_feed(
        self,
        user: Optional[User] = None,
        user_id: Optional[Any] = None,
        language: str = "en",
        categories: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        limit: int = 50,
        db: Optional[Session] = None,
        weights: Optional[Dict[str, float]] = None,
        apply_diversity: bool = True,
    ) -> List[Dict[str, Any]]:
        """Generate a personalized ranked feed using hybrid scoring and diversity injection.

        Guarantees:
        - Blends content (0.4), collaborative (0.35), and trending (0.25).
        - Applies recency decay to boost newer articles.
        - Injects 20% diversity from underrepresented categories.
        - Enforces filter bubble prevention (feed never > 50% single category).
        - Response generation in < 500ms.

        Args:
            user: Authenticated User object (if any).
            user_id: Optional user identifier.
            language: Requested language code.
            categories: Optional list of category slugs to filter by.
            time_range: Optional time range filter.
            limit: Maximum items to produce.
            db: SQLAlchemy session.
            weights: Optional custom signal weights override.
            apply_diversity: Whether to enforce diversity injection and filter bubble cap.

        Returns:
            List of formatted feed item dictionaries.
        """
        start_time = time.perf_counter()
        session = db or self.db
        if session is None:
            raise ValueError("A database session must be provided to get_feed()")

        # Resolve user
        if user is None and user_id is not None:
            user = self._resolve_user(session, user_id)

        target_uid = str(user.id) if user else (user_id or "guest")

        # 1. Fetch candidate pool
        candidates = self._fetch_candidates(
            session=session,
            language=language,
            categories=categories,
            time_range=time_range,
            candidate_pool_limit=max(limit * 3, 100),
        )

        if not candidates:
            return []

        # 2. Extract user preferences and interaction affinities
        preferred_categories, user_category_weights = self._get_user_preferences_and_affinities(
            session=session, user=user
        )

        # Extract user interactions if user is present
        user_interactions = getattr(user, "interactions", []) if user else []

        # 3. Score candidates using hybrid scorer with recency decay
        now = datetime.now(timezone.utc)
        scored_candidates = self.score_candidates_hybrid(
            user_id=target_uid,
            candidates=candidates,
            user=user,
            interactions=user_interactions,
            onboarding_categories=list(preferred_categories),
            now=now,
            weights=weights,
        )

        # 4. Inject Diversity and Enforce Filter Bubble Cap (never > 50% single category)
        if apply_diversity:
            top_candidate_pairs = self.diversity_injector.inject_diversity(
                scored_candidates=scored_candidates,
                user_category_affinity=user_category_weights,
                limit=limit,
                interleave=True,
            )
        else:
            top_candidate_pairs = [item for _, item in scored_candidates[:limit]]

        # 5. Format items into standard feed JSON structure
        formatted_feed = [
            self._format_feed_item(snap=snap, article=article, target_language=language)
            for snap, article in top_candidate_pairs
        ]

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            f"Feed generated for user={target_uid}: {len(formatted_feed)} items in {elapsed_ms:.2f}ms "
            f"(diversity={apply_diversity})"
        )
        return formatted_feed

    def _resolve_user(self, session: Session, user_id: Any) -> Optional[User]:
        """Look up user by id if possible."""
        try:
            if isinstance(user_id, str):
                u_uuid = uuid.UUID(user_id)
                return session.query(User).filter(User.id == u_uuid).first()
            elif isinstance(user_id, uuid.UUID):
                return session.query(User).filter(User.id == user_id).first()
        except Exception:
            pass
        return None

    def _fetch_candidates(
        self,
        session: Session,
        language: str,
        categories: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        candidate_pool_limit: int = 150,
    ) -> List[tuple[Snap, Article]]:
        """Query recent candidate snaps joined with articles based on filters."""
        query = (
            session.query(Snap, Article)
            .join(Article, Snap.article_id == Article.id)
            .join(Category, Article.category_id == Category.id)
        )

        if categories:
            clean_categories = [c.lower().strip() for c in categories]
            query = query.filter(Category.slug.in_(clean_categories))

        if time_range:
            cutoff_dt = parse_time_range(time_range)
            if cutoff_dt:
                query = query.filter(Article.publish_time >= cutoff_dt)

        lang_enum = None
        for member in Language:
            if member.value == language:
                lang_enum = member
                break

        if lang_enum is not None:
            lang_condition = or_(
                Snap.language == lang_enum,
                Snap.translations.any(SnapTranslation.language == lang_enum),
                Article.language == lang_enum,
            )
        else:
            lang_condition = or_(
                Snap.language == language,
                Snap.translations.any(SnapTranslation.language == language),
                Article.language == language,
            )

        lang_filtered_query = query.filter(lang_condition)
        results = lang_filtered_query.order_by(Article.publish_time.desc()).limit(candidate_pool_limit).all()

        if results:
            return [(row[0], row[1]) for row in results]

        fallback = query.order_by(Article.publish_time.desc()).limit(candidate_pool_limit).all()
        return [(row[0], row[1]) for row in fallback]

    def _get_user_preferences_and_affinities(
        self, session: Session, user: Optional[User]
    ) -> tuple[Set[str], Dict[str, float]]:
        """Extract explicit user preferences and implicit category affinities from interactions."""
        preferred_categories: Set[str] = set()
        user_category_weights: Dict[str, float] = {}

        if not user:
            return preferred_categories, user_category_weights

        # 1. Explicit onboarding preferences
        prefs = user.preferences
        if prefs and prefs.categories:
            for cat in prefs.categories:
                slug = cat.slug.lower() if hasattr(cat, "slug") else str(cat).lower()
                preferred_categories.add(slug)

        # 2. Implicit category affinities from past interactions
        try:
            interactions = user.interactions
            if interactions:
                for inter in interactions:
                    art = getattr(inter, "article", None)
                    if art and art.category:
                        slug = art.category.slug.lower()
                        weight = 1.0
                        itype = getattr(inter, "type", "")
                        if itype == "like":
                            weight = 3.0
                        elif itype == "comment":
                            weight = 5.0
                        elif itype == "share":
                            weight = 7.0
                        elif itype == "bookmark":
                            weight = 3.0
                        user_category_weights[slug] = user_category_weights.get(slug, 0.0) + weight

                total_weight = sum(user_category_weights.values())
                if total_weight > 0:
                    for k in user_category_weights:
                        user_category_weights[k] /= total_weight
        except Exception:
            pass

        return preferred_categories, user_category_weights

    def _get_translated_summary(self, snap: Snap, target_language: str) -> str:
        """Retrieve the snap summary translated into target_language if available."""
        snap_lang_str = snap.language.value if hasattr(snap.language, "value") else str(snap.language)
        if snap_lang_str == target_language:
            return snap.summary

        translations = getattr(snap, "translations", []) or []
        for trans in translations:
            t_lang_str = trans.language.value if hasattr(trans.language, "value") else str(trans.language)
            if t_lang_str == target_language and trans.summary:
                return trans.summary

        return snap.summary

    def _calculate_interaction_counts(self, article: Article) -> Dict[str, int]:
        """Aggregate interaction and comment counts for an article."""
        interactions = getattr(article, "interactions", []) or []
        likes = sum(1 for i in interactions if getattr(i, "type", None) == "like")
        comments_from_int = sum(1 for i in interactions if getattr(i, "type", None) == "comment")
        comments_from_table = len(article.comments) if getattr(article, "comments", None) else 0
        comments = max(comments_from_int, comments_from_table)
        shares = sum(1 for i in interactions if getattr(i, "type", None) == "share")
        bookmarks = sum(1 for i in interactions if getattr(i, "type", None) == "bookmark")

        return {
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "bookmarks": bookmarks,
        }

    def _format_feed_item(self, snap: Snap, article: Article, target_language: str) -> Dict[str, Any]:
        """Format an individual snap item into standard feed JSON structure."""
        category_slug = article.category.slug if getattr(article, "category", None) else "national"
        source_name = article.source.name if getattr(article, "source", None) else "NewsSnap"
        image_url = snap.image_url or article.image_url
        summary = self._get_translated_summary(snap, target_language)
        time_ago = format_time_ago(article.publish_time or snap.created_at)
        interaction_counts = self._calculate_interaction_counts(article)

        return {
            "snap_id": str(snap.id),
            "article_id": str(article.id),
            "title": article.title,
            "summary": summary,
            "image_url": image_url,
            "category": category_slug,
            "source": source_name,
            "time_ago": time_ago,
            "interaction_counts": interaction_counts,
        }
