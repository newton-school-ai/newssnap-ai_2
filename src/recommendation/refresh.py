"""NewsSnap AI - Recommendation Refresh Engine (Issue 24).

Precomputes and caches personalized news feeds in Redis for active users:
- Refresh runs every 30 minutes for active users (via APScheduler)
- Pre-computes top 50 feed items per user per language
- Fast parallel execution (< 5 minutes for 1000 users)
- Seamless integration with Redis cache and in-memory fallback
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.user import User
from src.recommendation.ab_testing import get_ab_test_manager
from src.recommendation.engine import RecommendationEngine
from src.utils.cache import build_feed_cache_key, set_cached_feed

logger = logging.getLogger(__name__)

DEFAULT_FEED_CACHE_TTL_SECONDS: int = 1800  # 30 minutes
DEFAULT_PRECOMPUTE_LIMIT: int = 50  # Top 50 snaps per user per language
DEFAULT_BATCH_WORKERS: int = 8


def get_active_users(
    db: Session,
    limit: Optional[int] = None,
) -> List[User]:
    """Retrieve active users eligible for feed precomputation."""
    query = db.query(User).filter(User.is_active.is_(True))
    if limit is not None and limit > 0:
        query = query.limit(limit)
    return query.all()


def _resolve_user_languages(user: User, fallback_languages: Optional[List[str]] = None) -> List[str]:
    """Determine the languages to precompute for a given user."""
    langs: List[str] = []
    prefs = getattr(user, "preferences", None)
    if prefs:
        prim = getattr(prefs, "primary_language", None)
        if prim:
            lang_val = prim.value if hasattr(prim, "value") else str(prim)
            langs.append(lang_val.lower().strip())
        sec = getattr(prefs, "secondary_language", None)
        if sec:
            lang_val = sec.value if hasattr(sec, "value") else str(sec)
            langs.append(lang_val.lower().strip())

    if not langs:
        langs = [lang_code.lower().strip() for lang_code in (fallback_languages or ["en"])]

    # Deduplicate while preserving order
    seen = set()
    result = []
    for lang_code in langs:
        if lang_code and lang_code not in seen:
            seen.add(lang_code)
            result.append(lang_code)
    return result or ["en"]


def precompute_single_user_feed(
    user_id: str | UUID,
    language: str,
    db: Optional[Session] = None,
    user: Optional[User] = None,
    engine: Optional[RecommendationEngine] = None,
    limit: int = DEFAULT_PRECOMPUTE_LIMIT,
    ttl_seconds: int = DEFAULT_FEED_CACHE_TTL_SECONDS,
    experiment_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Precompute and cache the top 50 feed items for a single user and language."""
    rec_engine = engine or RecommendationEngine(db=db)
    uid_str = str(user_id)

    # 1. Check for active A/B testing experiment parameters
    weights_override = None
    if experiment_name:
        ab_mgr = get_ab_test_manager()
        params = ab_mgr.get_variant_parameters(experiment_name, uid_str)
        weights_override = params.get("weights")

    # 2. Generate feed items (top 50)
    feed_items = rec_engine.get_feed(
        user=user,
        user_id=uid_str,
        language=language,
        categories=None,
        time_range=None,
        limit=limit,
        db=db,
        weights=weights_override,
        apply_diversity=True,
    )

    # 3. Store in Redis
    cache_key = build_feed_cache_key(
        user_id=uid_str,
        language=language,
        categories=None,
        time_range=None,
    )
    set_cached_feed(cache_key=cache_key, items=feed_items, ttl=ttl_seconds)

    return feed_items


def refresh_user_feeds(
    db: Session,
    users: Optional[List[User]] = None,
    languages: Optional[List[str]] = None,
    limit: int = DEFAULT_PRECOMPUTE_LIMIT,
    ttl_seconds: int = DEFAULT_FEED_CACHE_TTL_SECONDS,
    max_workers: int = DEFAULT_BATCH_WORKERS,
    experiment_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute high-throughput batch precomputation of feeds for active users.

    Acceptance Criteria:
    - Pre-computed feeds in Redis (top 50 per user per language)
    - 1000 user refresh < 5 minutes
    """
    start_time = time.perf_counter()

    # 1. Fetch active users if not provided
    active_users = users if users is not None else get_active_users(db)
    total_users = len(active_users)

    if total_users == 0:
        return {
            "total_users": 0,
            "feeds_cached": 0,
            "duration_seconds": 0.0,
            "users_per_second": 0.0,
            "errors": 0,
        }

    rec_engine = RecommendationEngine(db=db)

    # 2. Determine all distinct languages needed
    all_needed_langs: set[str] = set()
    user_lang_map: dict[str, list[str]] = {}
    for u in active_users:
        u_langs = _resolve_user_languages(u, fallback_languages=languages)
        user_lang_map[str(u.id)] = u_langs
        all_needed_langs.update(u_langs)

    # 3. Pre-fetch candidates once per language using the db session on main thread
    candidates_by_lang: dict[str, list[Any]] = {}
    for lang in all_needed_langs:
        try:
            candidates_by_lang[lang] = rec_engine._fetch_candidates(
                session=db, language=lang, candidate_pool_limit=max(limit * 3, 150)
            )
        except Exception as exc:
            logger.debug(f"Error fetching candidates for lang {lang}: {exc}")
            candidates_by_lang[lang] = []

    feeds_cached = 0
    errors = 0

    # 4. Worker task
    def process_user(u: User) -> int:
        nonlocal errors
        user_cached = 0
        uid_str = str(u.id)
        u_langs = user_lang_map.get(uid_str, ["en"])

        # Check for active A/B testing experiment parameters
        weights_override = None
        if experiment_name:
            ab_mgr = get_ab_test_manager()
            params = ab_mgr.get_variant_parameters(experiment_name, uid_str)
            weights_override = params.get("weights")

        for lang in u_langs:
            try:
                candidates = candidates_by_lang.get(lang)
                if not candidates:
                    # Fallback to direct get_feed
                    feed_items = precompute_single_user_feed(
                        user_id=uid_str,
                        language=lang,
                        db=db,
                        user=u,
                        engine=rec_engine,
                        limit=limit,
                        ttl_seconds=ttl_seconds,
                        experiment_name=experiment_name,
                    )
                else:
                    # Fast in-memory scoring without repeated concurrent DB queries
                    user_interactions = getattr(u, "interactions", []) or []
                    preferred_categories, user_category_weights = rec_engine._get_user_preferences_and_affinities(
                        session=db, user=u
                    )
                    now = datetime.now(timezone.utc)
                    scored = rec_engine.score_candidates_hybrid(
                        user_id=uid_str,
                        candidates=candidates,
                        user=u,
                        interactions=user_interactions,
                        onboarding_categories=list(preferred_categories),
                        now=now,
                        weights=weights_override,
                    )
                    top_candidate_pairs = rec_engine.diversity_injector.inject_diversity(
                        scored_candidates=scored,
                        user_category_affinity=user_category_weights,
                        limit=limit,
                        interleave=True,
                    )
                    feed_items = [
                        rec_engine._format_feed_item(snap=snap, article=article, target_language=lang)
                        for snap, article in top_candidate_pairs
                    ]
                    cache_key = build_feed_cache_key(
                        user_id=uid_str,
                        language=lang,
                        categories=None,
                        time_range=None,
                    )
                    set_cached_feed(cache_key=cache_key, items=feed_items, ttl=ttl_seconds)

                user_cached += 1
            except Exception as exc:
                errors += 1
                logger.debug(f"Error precomputing feed for user {uid_str} lang {lang}: {exc}")
        return user_cached

    # 5. Parallel execution with ThreadPoolExecutor
    workers = min(max_workers, max(1, total_users // 2))
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_user = {executor.submit(process_user, u): u for u in active_users}
            for future in as_completed(future_to_user):
                try:
                    feeds_cached += future.result()
                except Exception as exc:
                    errors += 1
                    logger.debug(f"User refresh task raised exception: {exc}")
    else:
        for u in active_users:
            feeds_cached += process_user(u)

    duration = time.perf_counter() - start_time
    rate = total_users / max(1e-6, duration)

    logger.info(
        f"Feed refresh completed: {total_users} users, {feeds_cached} feeds cached "
        f"in {duration:.2f}s ({rate:.1f} users/sec, errors={errors})"
    )

    return {
        "total_users": total_users,
        "feeds_cached": feeds_cached,
        "duration_seconds": duration,
        "users_per_second": rate,
        "errors": errors,
    }
