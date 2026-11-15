"""NewsSnap AI - Recommendation Signals and Interaction Event Processing.

Processes user engagement events (reads, likes, bookmarks, shares, comments)
and computes time-decayed weights using an exponential decay with a 3-day half-life.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence


class InteractionType(str, Enum):
    """Supported interaction types for recommendation signals."""

    LIKE = "like"
    BOOKMARK = "bookmark"
    SHARE = "share"
    READ = "read"
    VIEW = "view"
    COMMENT = "comment"


# Default engagement weights reflecting user intent and effort
DEFAULT_SIGNAL_WEIGHTS: dict[str, float] = {
    InteractionType.SHARE.value: 4.0,  # Highest active endorsement & distribution intent
    InteractionType.BOOKMARK.value: 3.0,  # High personal curation & save intent
    InteractionType.COMMENT.value: 2.5,  # Active engagement and discussion
    InteractionType.LIKE.value: 2.0,  # Explicit positive sentiment
    InteractionType.READ.value: 1.0,  # Standard consumption signal
    InteractionType.VIEW.value: 0.5,  # Passive open / impression
}

# 3-day half-life in seconds: (3 * 24 * 3600) = 259,200 seconds
DEFAULT_HALF_LIFE_DAYS: float = 3.0
SECONDS_PER_DAY: float = 86400.0


def _normalize_datetime(dt: datetime | None) -> datetime:
    """Normalize datetime to UTC timezone-aware datetime."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_recency_weight(
    timestamp: datetime | None,
    reference_time: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """Compute exponential decay recency factor with a specified half-life.

    Formula:
        decay = 2 ** (-delta_t / half_life)
        where delta_t is the elapsed time in days between timestamp and reference_time.

    Properties:
        - At delta_t = 0 days: decay = 1.0
        - At delta_t = 3 days (half_life): decay = 0.5
        - At delta_t = 6 days (2 * half_life): decay = 0.25
        - Clock skew / future timestamps cap at 1.0.
    """
    if timestamp is None:
        return 1.0

    ref = _normalize_datetime(reference_time)
    ts = _normalize_datetime(timestamp)

    delta_seconds = (ref - ts).total_seconds()
    if delta_seconds <= 0:
        return 1.0

    half_life_seconds = max(half_life_days * SECONDS_PER_DAY, 1.0)
    decay = math.pow(0.5, delta_seconds / half_life_seconds)
    return float(max(0.0, min(1.0, decay)))


def compute_dwell_time_multiplier(time_spent_seconds: int | float | None) -> float:
    """Compute engagement multiplier based on dwell time (reading duration).

    Scale:
        - None or <= 0: 1.0 (default for explicit actions like like/bookmark)
        - < 5s: 0.3 (quick bounce / misclick)
        - 5s - 15s: 0.7 (skimming)
        - 15s - 60s: 1.0 (standard read)
        - > 60s: smoothly scales up to 1.5 (deep reading)
    """
    if time_spent_seconds is None or time_spent_seconds <= 0:
        return 1.0

    seconds = float(time_spent_seconds)
    if seconds < 5.0:
        return 0.3
    if seconds < 15.0:
        return 0.7
    if seconds <= 60.0:
        return 1.0

    # For dwell > 60s, scale up to 1.5 maximum
    bonus = min(0.5, (seconds - 60.0) / 120.0 * 0.5)
    return 1.0 + bonus


def compute_interaction_weight(
    interaction_type: str | InteractionType,
    time_spent_seconds: int | float | None = None,
    weights: dict[str, float] | None = None,
    adjust_for_dwell: bool = True,
) -> float:
    """Compute raw interaction weight combining base signal weight and dwell time."""
    type_key = str(getattr(interaction_type, "value", interaction_type)).lower()
    signal_weights = weights if weights is not None else DEFAULT_SIGNAL_WEIGHTS
    base_weight = signal_weights.get(type_key, 1.0)

    if adjust_for_dwell and time_spent_seconds is not None:
        multiplier = compute_dwell_time_multiplier(time_spent_seconds)
        return float(base_weight * multiplier)

    return float(base_weight)


@dataclass
class InteractionSignal:
    """Processed interaction signal with raw, recency, and effective weights."""

    user_id: Any
    article_id: Any
    signal_type: str
    raw_weight: float
    recency_weight: float
    effective_weight: float
    timestamp: datetime
    time_spent_seconds: int | None = None
    category: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SignalProcessor:
    """Processes raw interaction events into weighted signals with exponential recency decay."""

    def __init__(
        self,
        signal_weights: dict[str, float] | None = None,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
        adjust_for_dwell: bool = True,
    ):
        self.signal_weights = dict(signal_weights if signal_weights is not None else DEFAULT_SIGNAL_WEIGHTS)
        self.half_life_days = float(half_life_days)
        self.adjust_for_dwell = adjust_for_dwell

    def process(
        self,
        interaction: Any,
        reference_time: datetime | None = None,
        category: str | None = None,
    ) -> InteractionSignal:
        """Process a single interaction event into an InteractionSignal.

        Accepts:
            - SQLAlchemy Interaction instance
            - Dict with interaction fields
            - Custom object with user_id, article_id, type, created_at, time_spent_seconds
        """
        # If already an InteractionSignal, recalculate recency if reference_time provided
        if isinstance(interaction, InteractionSignal):
            recency = compute_recency_weight(
                interaction.timestamp,
                reference_time=reference_time,
                half_life_days=self.half_life_days,
            )
            return InteractionSignal(
                user_id=interaction.user_id,
                article_id=interaction.article_id,
                signal_type=interaction.signal_type,
                raw_weight=interaction.raw_weight,
                recency_weight=recency,
                effective_weight=interaction.raw_weight * recency,
                timestamp=interaction.timestamp,
                time_spent_seconds=interaction.time_spent_seconds,
                category=category or interaction.category,
                metadata=interaction.metadata,
            )

        # Extract fields from dict or object
        if isinstance(interaction, dict):
            user_id = interaction.get("user_id")
            article_id = interaction.get("article_id")
            signal_type = interaction.get("type") or interaction.get("signal_type") or "read"
            timestamp = interaction.get("created_at") or interaction.get("timestamp")
            time_spent = interaction.get("time_spent_seconds")
            extracted_cat = interaction.get("category") or category
            metadata = interaction.get("metadata") or {}
        else:
            user_id = getattr(interaction, "user_id", None)
            article_id = getattr(interaction, "article_id", None)
            signal_type = getattr(interaction, "type", None) or getattr(interaction, "signal_type", "read")
            timestamp = getattr(interaction, "created_at", None) or getattr(interaction, "timestamp", None)
            time_spent = getattr(interaction, "time_spent_seconds", None)
            extracted_cat = (
                getattr(interaction, "category", None)
                or getattr(getattr(interaction, "article", None), "category", None)
                or category
            )
            raw_meta = getattr(interaction, "metadata_dict", None)
            if raw_meta is None and hasattr(interaction, "__dict__") and "metadata" in interaction.__dict__:
                raw_meta = interaction.__dict__["metadata"]
            metadata = raw_meta if isinstance(raw_meta, dict) else {}

        # Normalize timestamp
        ts = _normalize_datetime(timestamp)

        # Compute weights
        raw_weight = compute_interaction_weight(
            interaction_type=signal_type,
            time_spent_seconds=time_spent,
            weights=self.signal_weights,
            adjust_for_dwell=self.adjust_for_dwell,
        )
        recency = compute_recency_weight(
            ts,
            reference_time=reference_time,
            half_life_days=self.half_life_days,
        )
        effective_weight = raw_weight * recency

        type_str = str(getattr(signal_type, "value", signal_type)).lower()
        cat_str = (
            str(getattr(extracted_cat, "value", getattr(extracted_cat, "slug", extracted_cat))).lower()
            if extracted_cat
            else None
        )

        return InteractionSignal(
            user_id=user_id,
            article_id=article_id,
            signal_type=type_str,
            raw_weight=raw_weight,
            recency_weight=recency,
            effective_weight=effective_weight,
            timestamp=ts,
            time_spent_seconds=time_spent,
            category=cat_str,
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    def process_batch(
        self,
        interactions: Sequence[Any],
        reference_time: datetime | None = None,
        article_categories: dict[Any, str] | None = None,
    ) -> list[InteractionSignal]:
        """Process a collection of interaction records into InteractionSignals."""
        signals: list[InteractionSignal] = []
        cat_map = article_categories or {}
        for item in interactions:
            art_id = item.get("article_id") if isinstance(item, dict) else getattr(item, "article_id", None)
            cat = cat_map.get(art_id)
            signals.append(self.process(item, reference_time=reference_time, category=cat))
        return signals

    def aggregate_by_article(self, signals: Sequence[InteractionSignal]) -> dict[Any, float]:
        """Aggregate effective signal weights grouped by article ID."""
        article_weights: dict[Any, float] = {}
        for s in signals:
            if s.article_id is not None:
                article_weights[s.article_id] = article_weights.get(s.article_id, 0.0) + s.effective_weight
        return article_weights

    def aggregate_by_category(
        self,
        signals: Sequence[InteractionSignal],
        article_categories: dict[Any, str] | None = None,
    ) -> dict[str, float]:
        """Aggregate effective signal weights grouped by category."""
        category_weights: dict[str, float] = {}
        cat_map = article_categories or {}
        for s in signals:
            cat = s.category or cat_map.get(s.article_id)
            if cat:
                normalized_cat = str(getattr(cat, "value", getattr(cat, "slug", cat))).lower()
                category_weights[normalized_cat] = category_weights.get(normalized_cat, 0.0) + s.effective_weight
        return category_weights
