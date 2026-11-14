"""NewsSnap AI - Recommendation Engine Module."""

from src.recommendation.content_based import (
    ALL_CATEGORIES,
    COLD_START_THRESHOLD,
    NUM_CATEGORIES,
    CategoryAffinityTracker,
    ContentBasedRecommender,
    UserProfile,
    build_category_vector,
    cosine_similarity,
    normalize_category_name,
)
from src.recommendation.signals import (
    DEFAULT_HALF_LIFE_DAYS,
    DEFAULT_SIGNAL_WEIGHTS,
    InteractionSignal,
    InteractionType,
    SignalProcessor,
    compute_dwell_time_multiplier,
    compute_interaction_weight,
    compute_recency_weight,
)

__all__ = [
    "ContentBasedRecommender",
    "UserProfile",
    "CategoryAffinityTracker",
    "SignalProcessor",
    "InteractionSignal",
    "InteractionType",
    "DEFAULT_SIGNAL_WEIGHTS",
    "DEFAULT_HALF_LIFE_DAYS",
    "COLD_START_THRESHOLD",
    "NUM_CATEGORIES",
    "ALL_CATEGORIES",
    "compute_recency_weight",
    "compute_interaction_weight",
    "compute_dwell_time_multiplier",
    "build_category_vector",
    "cosine_similarity",
    "normalize_category_name",
]
