"""NewsSnap AI - Trending, Category Top, and Breaking News Recommendation Engine (Issue 20).

Features:
- Interaction velocity computation over a 1-hour window (interactions per minute)
- Redis sorted set velocity storage (ZSET) with 5-minute auto-refresh TTL
- Trending article ranking by velocity with language filtering
- Breaking news detection (< 30 minutes old with velocity > threshold)
- Top articles per category from the last 24 hours
- Explore feed aggregator combining breaking, trending, and top per category
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.config.settings import Language, settings
from src.models.article import Article
from src.models.category import Category
from src.models.interaction import Comment, Interaction, InteractionType
from src.models.snap import Snap
from src.utils.cache import get_cache, set_cache, zadd

logger = logging.getLogger(__name__)

# Configurable interaction weights for velocity and engagement scoring
INTERACTION_WEIGHTS = {
    InteractionType.SHARE.value: 3.0,
    "comment": 2.0,
    InteractionType.LIKE.value: 1.5,
    InteractionType.BOOKMARK.value: 1.5,
    InteractionType.READ.value: 0.5,
}


def _normalize_language(language: Optional[str]) -> Optional[str]:
    """Normalize language string or return None if 'all'."""
    if not language or language.lower() in ("all", "*"):
        return None
    val = language.lower().strip()
    return val


def format_article_item(
    article: Article,
    snap: Optional[Snap] = None,
    velocity: float = 0.0,
    is_breaking: bool = False,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Format an article model into a comprehensive client-friendly dictionary."""
    cat_slug = article.category.slug if article.category else "national"
    cat_name = article.category.name if article.category else "National"
    src_slug = article.source.slug if article.source else "unknown"
    src_name = article.source.name if article.source else "Unknown"

    # Select snap matching requested language or first snap
    chosen_snap = None
    if article.snaps:
        if language:
            for s in article.snaps:
                s_lang = s.language.value if hasattr(s.language, "value") else str(s.language)
                if s_lang == language:
                    chosen_snap = s
                    break
        if not chosen_snap:
            chosen_snap = article.snaps[0]
    elif snap:
        chosen_snap = snap

    summary = ""
    image_url = article.image_url or ""
    if chosen_snap:
        summary = chosen_snap.summary
        if chosen_snap.image_url:
            image_url = chosen_snap.image_url
    elif article.body:
        summary = article.body[:200]

    lang_val = article.language.value if hasattr(article.language, "value") else str(article.language)

    return {
        "id": str(article.id),
        "article_id": str(article.id),
        "title": article.title,
        "summary": summary,
        "category": cat_slug,
        "category_name": cat_name,
        "category_id": article.category_id,
        "source": src_slug,
        "source_name": src_name,
        "image_url": image_url,
        "source_url": article.source_url,
        "publish_time": article.publish_time.isoformat() if article.publish_time else None,
        "author": article.author,
        "language": lang_val,
        "quality_score": article.quality_score,
        "velocity": round(float(velocity), 4),
        "is_breaking": is_breaking,
    }


def compute_article_velocities(
    db: Session,
    window_hours: float = 1.0,
    language: Optional[str] = None,
) -> Dict[uuid.UUID, float]:
    """
    Compute interaction velocity for all articles with activity in the last window_hours.
    Velocity = weighted_interactions / effective_window_minutes.
    Stores computed scores in Redis sorted sets.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=window_hours)
    norm_lang = _normalize_language(language)

    # 1. Query interaction counts per article in the window
    int_query = (
        db.query(
            Interaction.article_id,
            Interaction.type,
            func.count(Interaction.id).label("count"),
        )
        .filter(Interaction.created_at >= cutoff)
        .group_by(Interaction.article_id, Interaction.type)
    )
    interaction_counts = int_query.all()

    # 2. Query comments per article in the window
    com_query = (
        db.query(
            Comment.article_id,
            func.count(Comment.id).label("count"),
        )
        .filter(Comment.created_at >= cutoff)
        .group_by(Comment.article_id)
    )
    comment_counts = com_query.all()

    # Build weighted interaction score per article
    article_scores: Dict[uuid.UUID, float] = {}
    for art_id, int_type, count in interaction_counts:
        weight = INTERACTION_WEIGHTS.get(int_type, 1.0)
        article_scores[art_id] = article_scores.get(art_id, 0.0) + (count * weight)

    comment_weight = INTERACTION_WEIGHTS.get("comment", 2.0)
    for art_id, count in comment_counts:
        article_scores[art_id] = article_scores.get(art_id, 0.0) + (count * comment_weight)

    if not article_scores:
        return {}

    # 3. Retrieve publish_time and language for active articles
    active_articles = (
        db.query(Article.id, Article.publish_time, Article.language, Article.is_duplicate)
        .filter(Article.id.in_(list(article_scores.keys())))
        .all()
    )

    velocities: Dict[uuid.UUID, float] = {}
    redis_mapping: Dict[str, float] = {}

    for art_id, pub_time, art_lang, is_dup in active_articles:
        if is_dup:
            continue

        raw_score = article_scores.get(art_id, 0.0)
        if pub_time:
            elapsed_minutes = (now - pub_time).total_seconds() / 60.0
            # Effective minutes: between 1 minute and window_hours * 60
            effective_minutes = max(1.0, min(window_hours * 60.0, elapsed_minutes))
        else:
            effective_minutes = window_hours * 60.0

        velocity = raw_score / effective_minutes
        velocities[art_id] = velocity

        art_lang_str = art_lang.value if hasattr(art_lang, "value") else str(art_lang)
        if not norm_lang or art_lang_str == norm_lang:
            redis_mapping[str(art_id)] = round(velocity, 4)

    # Store in Redis sorted set
    if redis_mapping:
        zset_key = f"trending:velocity:{norm_lang or 'all'}"
        zadd(zset_key, redis_mapping)

    return velocities


def get_trending_articles(
    db: Session,
    language: Optional[str] = None,
    category_slug: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    window_hours: float = 1.0,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Get articles ranked by interaction velocity in the last window_hours.
    Cached in Redis with 5-minute TTL.
    """
    norm_lang = _normalize_language(language)
    cache_key = f"trending:articles:{norm_lang or 'all'}:{category_slug or 'all'}:{limit}:{offset}"

    if not force_refresh:
        cached = get_cache(cache_key)
        if cached is not None:
            return cached

    # Compute latest velocities
    velocities = compute_article_velocities(db, window_hours=window_hours, language=norm_lang)

    # Query candidate articles
    query = (
        db.query(Article)
        .options(
            joinedload(Article.category),
            joinedload(Article.source),
            joinedload(Article.snaps),
        )
        .filter(Article.is_duplicate.is_(False))
    )

    if norm_lang:
        query = query.filter(Article.language == norm_lang)

    if category_slug:
        query = query.join(Article.category).filter(Category.slug == category_slug)

    candidate_articles = query.all()

    # Sort primarily by velocity descending, secondarily by publish_time descending
    def sort_key(art: Article) -> Tuple[float, datetime]:
        vel = velocities.get(art.id, 0.0)
        pub = art.publish_time or datetime.min
        return (vel, pub)

    sorted_articles = sorted(candidate_articles, key=sort_key, reverse=True)
    paged = sorted_articles[offset : offset + limit]

    result = [
        format_article_item(
            art,
            velocity=velocities.get(art.id, 0.0),
            language=norm_lang,
        )
        for art in paged
    ]

    set_cache(cache_key, result, ttl_seconds=settings.TRENDING_CACHE_TTL_SECONDS)
    return result


def detect_breaking_news(
    db: Session,
    language: Optional[str] = None,
    threshold: Optional[float] = None,
    max_age_minutes: Optional[int] = None,
    limit: int = 5,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Detect breaking news: articles < max_age_minutes old with velocity > threshold.
    Cached in Redis with 5-minute TTL.
    """
    norm_lang = _normalize_language(language)
    thresh = threshold if threshold is not None else settings.BREAKING_NEWS_VELOCITY_THRESHOLD
    max_age = max_age_minutes if max_age_minutes is not None else settings.BREAKING_NEWS_MAX_AGE_MINUTES

    cache_key = f"breaking:articles:{norm_lang or 'all'}:{thresh}:{max_age}:{limit}"

    if not force_refresh:
        cached = get_cache(cache_key)
        if cached is not None:
            return cached

    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=max_age)

    # Compute current velocities
    velocities = compute_article_velocities(db, window_hours=1.0, language=norm_lang)

    # Query recent non-duplicate articles
    query = (
        db.query(Article)
        .options(
            joinedload(Article.category),
            joinedload(Article.source),
            joinedload(Article.snaps),
        )
        .filter(
            Article.is_duplicate.is_(False),
            Article.publish_time >= cutoff,
        )
    )

    if norm_lang:
        query = query.filter(Article.language == norm_lang)

    recent_articles = query.all()

    # Filter by velocity > threshold
    breaking_candidates = []
    for art in recent_articles:
        vel = velocities.get(art.id, 0.0)
        if vel >= thresh:
            breaking_candidates.append((art, vel))

    # Rank by velocity desc, then publish_time desc
    breaking_candidates.sort(
        key=lambda pair: (pair[1], pair[0].publish_time or datetime.min),
        reverse=True,
    )

    paged = breaking_candidates[:limit]
    result = [
        format_article_item(
            art,
            velocity=vel,
            is_breaking=True,
            language=norm_lang,
        )
        for art, vel in paged
    ]

    set_cache(cache_key, result, ttl_seconds=settings.TRENDING_CACHE_TTL_SECONDS)
    return result


def get_top_articles_by_category(
    db: Session,
    category_slug: str,
    language: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    window_hours: int = 24,
    force_refresh: bool = False,
) -> Optional[List[Dict[str, Any]]]:
    """
    Retrieve best articles for a specific category from the last 24 hours.
    Returns None if category does not exist.
    Cached in Redis with 5-minute TTL.
    """
    norm_lang = _normalize_language(language)
    cache_key = f"category_top:{category_slug}:{norm_lang or 'all'}:{limit}:{offset}:{window_hours}"

    if not force_refresh:
        cached = get_cache(cache_key)
        if cached is not None:
            return cached

    # Verify category exists
    cat = db.query(Category).filter(Category.slug == category_slug).first()
    if not cat:
        return None

    now = datetime.utcnow()
    cutoff = now - timedelta(hours=window_hours)

    # Velocities for ranking signal
    velocities = compute_article_velocities(db, window_hours=1.0, language=norm_lang)

    # Query articles published within the last 24 hours
    query = (
        db.query(Article)
        .options(
            joinedload(Article.category),
            joinedload(Article.source),
            joinedload(Article.snaps),
        )
        .filter(
            Article.category_id == cat.id,
            Article.is_duplicate.is_(False),
            Article.publish_time >= cutoff,
        )
    )

    if norm_lang:
        query = query.filter(Article.language == norm_lang)

    articles = query.all()

    # Calculate 24-hour engagement score per candidate article
    if articles:
        art_ids = [a.id for a in articles]
        int_totals = dict(
            db.query(Interaction.article_id, func.count(Interaction.id))
            .filter(
                Interaction.article_id.in_(art_ids),
                Interaction.created_at >= cutoff,
            )
            .group_by(Interaction.article_id)
            .all()
        )
        com_totals = dict(
            db.query(Comment.article_id, func.count(Comment.id))
            .filter(
                Comment.article_id.in_(art_ids),
                Comment.created_at >= cutoff,
            )
            .group_by(Comment.article_id)
            .all()
        )
    else:
        int_totals = {}
        com_totals = {}

    def category_score(art: Article) -> Tuple[float, datetime]:
        vel = velocities.get(art.id, 0.0)
        tot_int = int_totals.get(art.id, 0)
        tot_com = com_totals.get(art.id, 0)
        q_score = art.quality_score if art.quality_score is not None else 0.5

        # Blended engagement score
        score = (vel * 3.0) + (tot_int * 1.0) + (tot_com * 2.0) + (q_score * 2.0)
        return (score, art.publish_time or datetime.min)

    articles.sort(key=category_score, reverse=True)
    paged = articles[offset : offset + limit]

    result = [
        format_article_item(
            art,
            velocity=velocities.get(art.id, 0.0),
            language=norm_lang,
        )
        for art in paged
    ]

    set_cache(cache_key, result, ttl_seconds=settings.TRENDING_CACHE_TTL_SECONDS)
    return result


def get_explore_feed(
    db: Session,
    language: Optional[str] = None,
    trending_limit: int = 10,
    category_top_limit: int = 4,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Combined Explore endpoint data:
    - Breaking news (if any)
    - Trending articles (velocity-ranked)
    - Top articles per active category
    Cached in Redis with 5-minute TTL.
    """
    norm_lang = _normalize_language(language)
    cache_key = f"explore:feed:{norm_lang or 'all'}:{trending_limit}:{category_top_limit}"

    if not force_refresh:
        cached = get_cache(cache_key)
        if cached is not None:
            return cached

    breaking = detect_breaking_news(
        db,
        language=norm_lang,
        limit=5,
        force_refresh=force_refresh,
    )
    trending = get_trending_articles(
        db,
        language=norm_lang,
        limit=trending_limit,
        force_refresh=force_refresh,
    )

    # Top articles per active category
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.name.asc()).all()

    category_sections = []
    for cat in categories:
        top_arts = get_top_articles_by_category(
            db,
            category_slug=cat.slug,
            language=norm_lang,
            limit=category_top_limit,
            window_hours=24,
            force_refresh=force_refresh,
        )
        if top_arts:
            category_sections.append(
                {
                    "id": cat.id,
                    "slug": cat.slug,
                    "name": cat.name,
                    "articles": top_arts,
                    "count": len(top_arts),
                }
            )

    feed = {
        "breaking": breaking,
        "trending": trending,
        "categories": category_sections,
        "language": norm_lang or "all",
        "timestamp": datetime.utcnow().isoformat(),
    }

    set_cache(cache_key, feed, ttl_seconds=settings.TRENDING_CACHE_TTL_SECONDS)
    return feed


def refresh_all_trending_caches(db: Session) -> Dict[str, Any]:
    """
    Recompute and warm Redis caches for all supported languages.
    Called on 5-minute schedule or on demand.
    """
    results = {}
    languages = [None] + [lang.value for lang in Language]

    for lang in languages:
        lang_key = lang or "all"
        compute_article_velocities(db, window_hours=1.0, language=lang)
        trending = get_trending_articles(db, language=lang, limit=10, force_refresh=True)
        breaking = detect_breaking_news(db, language=lang, limit=5, force_refresh=True)
        explore = get_explore_feed(db, language=lang, force_refresh=True)
        results[lang_key] = {
            "trending_count": len(trending),
            "breaking_count": len(breaking),
            "explore_sections": len(explore.get("categories", [])),
        }

    return results
