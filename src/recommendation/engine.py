"""NewsSnap AI - Recommendation Engine (Issue 17 / M6).

Provides personalized feed ranking, trending score calculation, and
blended recommendations for new and returning users.
"""

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.config.settings import Language
from src.models.article import Article
from src.models.category import Category
from src.models.snap import Snap, SnapTranslation
from src.models.user import User
from src.utils.time_utils import format_time_ago, parse_time_range


class RecommendationEngine:
    """Recommendation engine for generating personalized and trending news feeds."""

    def __init__(self, db: Optional[Session] = None) -> None:
        """Initialize the recommendation engine.

        Args:
            db: Optional SQLAlchemy Session.
        """
        self.db = db

    def get_feed(
        self,
        user: Optional[User] = None,
        user_id: Optional[Any] = None,
        language: str = "en",
        categories: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        limit: int = 50,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Generate a personalized ranked feed of snap items.

            For new users (no interactions or newly onboarded), returns a blended
            feed combining trending snaps with preferred onboarding categories.
            For returning users, incorporates category affinity from past interactions.
            For guest users, serves trending snaps ranked by engagement and recency.

            Args:
                user: Authenticated User object (if any).
                user_id: Optional user identifier (used to look up User if user is None).
                language: Requested language code (e.g. 'en', 'hi').
                categories: Optional list of category slugs to filter by.
                time_range: Optional time range filter (e.g. '24h', '7d').
                limit: Maximum number of ranked items to produce (default: 50).
                db: SQLAlchemy session (overrides self.db if provided).

        Returns:
            List of formatted feed item dictionaries.
        """
        session = db or self.db
        if session is None:
            raise ValueError("A database session must be provided to get_feed()")

        # Resolve user if user_id was passed
        if user is None and user_id is not None:
            user = self._resolve_user(session, user_id)

        # 1. Build base candidate query
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

        # 3. Score and rank candidates
        now = datetime.now(timezone.utc)
        scored_items: List[tuple[float, Snap, Article]] = []

        for snap, article in candidates:
            score = self._score_item(
                snap=snap,
                article=article,
                user=user,
                preferred_categories=preferred_categories,
                user_category_weights=user_category_weights,
                now=now,
            )
            scored_items.append((score, snap, article))

        # Sort descending by score, breaking ties with article publish time
        def sort_key(item: tuple[float, Snap, Article]) -> tuple[float, float]:
            score_val, snap_obj, art_obj = item
            pub_ts = 0.0
            dt = art_obj.publish_time or snap_obj.created_at
            if dt:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                pub_ts = dt.timestamp()
            return (score_val, pub_ts)

        scored_items.sort(key=sort_key, reverse=True)

        # 4. Format top items into feed item dictionaries
        top_items = scored_items[:limit]
        formatted_feed = [
            self._format_feed_item(snap=snap, article=article, target_language=language)
            for _, snap, article in top_items
        ]

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
        """Fetch candidate Snap and Article pairs matching basic filters."""
        query = (
            session.query(Snap, Article)
            .join(Article, Snap.article_id == Article.id)
            .filter(Article.is_duplicate.is_(False))
        )

        # Category filter
        if categories:
            normalized_categories = [c.strip().lower() for c in categories if c.strip()]
            if normalized_categories:
                query = query.join(Category, Article.category_id == Category.id).filter(
                    Category.slug.in_(normalized_categories)
                )

        # Time range filter
        cutoff = parse_time_range(time_range)
        if cutoff is not None:
            query = query.filter(Article.publish_time >= cutoff)

        # Language matching:
        # Match snap original language OR snap translations
        lang_enum = None
        for member in Language:
            if member.value == language or member.name.lower() == language.lower():
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

        # If strict language filtering yields results, use them.
        # Otherwise, if no translated snaps exist in DB, fallback to query without language restriction
        # to ensure resilience while preserving translation preference when available.
        if results:
            return results

        return query.order_by(Article.publish_time.desc()).limit(candidate_pool_limit).all()

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
                preferred_categories.add(str(cat).lower())

        # 2. Implicit affinities from interactions (if any)
        try:
            interactions = getattr(user, "interactions", None)
            if interactions:
                for inter in interactions:
                    art = getattr(inter, "article", None)
                    if art and art.category:
                        slug = art.category.slug.lower()
                        weight = 1.0
                        if inter.type == "like":
                            weight = 2.0
                        elif inter.type == "share":
                            weight = 3.0
                        elif inter.type == "comment":
                            weight = 2.5
                        elif inter.type == "bookmark":
                            weight = 2.0
                        user_category_weights[slug] = user_category_weights.get(slug, 0.0) + weight

                # Normalize weights
                total_weight = sum(user_category_weights.values())
                if total_weight > 0:
                    for k in user_category_weights:
                        user_category_weights[k] /= total_weight
        except Exception:
            pass

        return preferred_categories, user_category_weights

    def _score_item(
        self,
        snap: Snap,
        article: Article,
        user: Optional[User],
        preferred_categories: Set[str],
        user_category_weights: Dict[str, float],
        now: datetime,
    ) -> float:
        """Compute the hybrid ranking score for a snap item."""
        # 1. Article quality score
        quality = article.quality_score if article.quality_score is not None else 0.75

        # 2. Recency decay (half-life of 24 hours)
        pub_time = article.publish_time or snap.created_at or now
        if pub_time.tzinfo is None:
            pub_time = pub_time.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (now - pub_time).total_seconds() / 3600.0)
        recency_factor = 1.0 / (1.0 + (age_hours / 24.0))

        # 3. Trending / Engagement points
        interactions = getattr(article, "interactions", []) or []
        likes = sum(1 for i in interactions if i.type == "like")
        comments = sum(1 for i in interactions if i.type == "comment") + (
            len(article.comments) if getattr(article, "comments", None) else 0
        )
        shares = sum(1 for i in interactions if i.type == "share")
        bookmarks = sum(1 for i in interactions if i.type == "bookmark")
        views = sum(1 for i in interactions if i.type == "view")

        engagement_points = (likes * 3.0) + (comments * 4.0) + (shares * 5.0) + (bookmarks * 2.0) + (views * 0.5)
        trending_score = 1.0 + math.log1p(engagement_points)

        # 4. Category and preference match
        cat_slug = article.category.slug.lower() if getattr(article, "category", None) else ""
        pref_multiplier = 1.0

        if user:
            # New user or existing user: boost items in preferred categories
            if cat_slug in preferred_categories:
                pref_multiplier += 1.5
            # Affinity boost for returning users
            if cat_slug in user_category_weights:
                pref_multiplier += user_category_weights[cat_slug] * 2.0
        elif not user:
            # Guest user: trending-focused with neutral preference multiplier
            pref_multiplier = 1.0

        final_score = quality * recency_factor * trending_score * pref_multiplier
        return final_score

    def _get_translated_summary(self, snap: Snap, target_language: str) -> str:
        """Retrieve the snap summary translated into target_language if available."""
        # If the snap itself is in the target language
        snap_lang_str = snap.language.value if hasattr(snap.language, "value") else str(snap.language)
        if snap_lang_str == target_language:
            return snap.summary

        # Check translations
        translations = getattr(snap, "translations", []) or []
        for trans in translations:
            t_lang_str = trans.language.value if hasattr(trans.language, "value") else str(trans.language)
            if t_lang_str == target_language and trans.summary:
                return trans.summary

        return snap.summary

    def _calculate_interaction_counts(self, article: Article) -> Dict[str, int]:
        """Aggregate interaction and comment counts for an article."""
        interactions = getattr(article, "interactions", []) or []
        likes = sum(1 for i in interactions if i.type == "like")
        comments_from_interactions = sum(1 for i in interactions if i.type == "comment")
        comments_from_table = len(article.comments) if getattr(article, "comments", None) else 0
        comments = max(comments_from_interactions, comments_from_table)
        shares = sum(1 for i in interactions if i.type == "share")
        bookmarks = sum(1 for i in interactions if i.type == "bookmark")

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
