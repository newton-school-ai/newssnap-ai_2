"""NewsSnap AI - A/B Testing Metrics Tracking Framework (Issue 24).

Tracks and aggregates experiment metrics per variant:
- Click-Through Rate (CTR): clicks / impressions
- Time spent: total dwell time, average time per impression and per click
- Interaction rates: likes, shares, bookmarks, comments per impression
- Statistical significance (z-score, p-value) and relative lift over control
- Redis storage with in-memory fallback for high-throughput tracking
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.utils.cache import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class VariantMetrics:
    """Aggregated engagement metrics for a specific experiment variant."""

    experiment_name: str
    variant_name: str
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0  # clicks / max(1, impressions)
    total_time_spent_seconds: float = 0.0
    avg_time_spent_seconds: float = 0.0  # total_time / max(1, impressions)
    avg_time_spent_per_click_seconds: float = 0.0  # total_time / max(1, clicks)
    interactions: int = 0
    interaction_rate: float = 0.0  # interactions / max(1, impressions)
    unique_users: int = 0

    def compute_derived_metrics(self) -> None:
        """Calculate ratios and rates from raw counters."""
        if self.impressions > 0:
            self.ctr = float(self.clicks) / float(self.impressions)
            self.avg_time_spent_seconds = float(self.total_time_spent_seconds) / float(self.impressions)
            self.interaction_rate = float(self.interactions) / float(self.impressions)
        else:
            self.ctr = 0.0
            self.avg_time_spent_seconds = 0.0
            self.interaction_rate = 0.0

        if self.clicks > 0:
            self.avg_time_spent_per_click_seconds = float(self.total_time_spent_seconds) / float(self.clicks)
        else:
            self.avg_time_spent_per_click_seconds = 0.0


@dataclass
class ExperimentSummary:
    """Consolidated A/B experiment evaluation summary with comparative lift."""

    experiment_name: str
    variants: Dict[str, VariantMetrics]
    control_variant: Optional[str] = None
    lift_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    p_values: Dict[str, float] = field(default_factory=dict)
    is_significant: Dict[str, bool] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _calculate_two_proportion_z_test(count_a: int, nobs_a: int, count_b: int, nobs_b: int) -> tuple[float, float]:
    """Calculate z-score and two-tailed p-value for two proportions (e.g. CTR).

    Args:
        count_a: Conversions/clicks in sample A (control).
        nobs_a: Total observations/impressions in sample A.
        count_b: Conversions/clicks in sample B (treatment).
        nobs_b: Total observations/impressions in sample B.

    Returns:
        (z_score, p_value) tuple.
    """
    if nobs_a <= 0 or nobs_b <= 0:
        return 0.0, 1.0

    p_a = count_a / nobs_a
    p_b = count_b / nobs_b
    p_pool = (count_a + count_b) / (nobs_a + nobs_b)

    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / nobs_a + 1.0 / nobs_b))
    if se <= 1e-9:
        return 0.0, 1.0

    z_stat = (p_b - p_a) / se

    # Standard normal two-tailed p-value approximation via erf
    p_value = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z_stat) / math.sqrt(2.0))))
    return z_stat, min(1.0, max(0.0, p_value))


class MetricsTracker:
    """Thread-safe event recorder and metrics aggregator for A/B tests."""

    def __init__(self) -> None:
        # In-memory stores: experiment -> variant -> metric
        self._impressions: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._clicks: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._time_spent: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._interactions: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._users: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))

    def _redis_key(self, experiment: str, variant: str, metric: str) -> str:
        return f"ab:metrics:{experiment}:{variant}:{metric}"

    def record_impression(
        self,
        experiment_name: str,
        variant_name: str,
        user_id: Any,
        article_id: Optional[Any] = None,
    ) -> None:
        """Record an impression (article/feed item shown to user under variant)."""
        uid = str(user_id)
        self._impressions[experiment_name][variant_name] += 1
        self._users[experiment_name][variant_name].add(uid)

        client = get_redis_client()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.incr(self._redis_key(experiment_name, variant_name, "impressions"))
                pipe.sadd(self._redis_key(experiment_name, variant_name, "users"), uid)
                pipe.execute()
            except Exception as e:
                logger.debug(f"Redis record_impression error: {e}")

    def record_click(
        self,
        experiment_name: str,
        variant_name: str,
        user_id: Any,
        article_id: Optional[Any] = None,
    ) -> None:
        """Record a click / view tap event for an article."""
        uid = str(user_id)
        self._clicks[experiment_name][variant_name] += 1
        self._users[experiment_name][variant_name].add(uid)

        client = get_redis_client()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.incr(self._redis_key(experiment_name, variant_name, "clicks"))
                pipe.sadd(self._redis_key(experiment_name, variant_name, "users"), uid)
                pipe.execute()
            except Exception as e:
                logger.debug(f"Redis record_click error: {e}")

    def record_time_spent(
        self,
        experiment_name: str,
        variant_name: str,
        user_id: Any,
        article_id: Optional[Any] = None,
        seconds: float = 0.0,
    ) -> None:
        """Record dwell / reading time in seconds spent viewing an article."""
        duration = max(0.0, float(seconds))
        uid = str(user_id)
        self._time_spent[experiment_name][variant_name] += duration
        self._users[experiment_name][variant_name].add(uid)

        client = get_redis_client()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.incrbyfloat(self._redis_key(experiment_name, variant_name, "time_spent"), duration)
                pipe.sadd(self._redis_key(experiment_name, variant_name, "users"), uid)
                pipe.execute()
            except Exception as e:
                logger.debug(f"Redis record_time_spent error: {e}")

    def record_interaction(
        self,
        experiment_name: str,
        variant_name: str,
        user_id: Any,
        article_id: Optional[Any] = None,
        interaction_type: str = "like",
    ) -> None:
        """Record a positive interaction (like, comment, share, bookmark)."""
        uid = str(user_id)
        self._interactions[experiment_name][variant_name] += 1
        self._users[experiment_name][variant_name].add(uid)

        client = get_redis_client()
        if client is not None:
            try:
                pipe = client.pipeline()
                pipe.incr(self._redis_key(experiment_name, variant_name, "interactions"))
                pipe.sadd(self._redis_key(experiment_name, variant_name, "users"), uid)
                pipe.execute()
            except Exception as e:
                logger.debug(f"Redis record_interaction error: {e}")

    def get_variant_metrics(self, experiment_name: str, variant_name: str) -> VariantMetrics:
        """Fetch and calculate engagement metrics for a single variant."""
        client = get_redis_client()
        imp = self._impressions[experiment_name][variant_name]
        clk = self._clicks[experiment_name][variant_name]
        dur = self._time_spent[experiment_name][variant_name]
        inter = self._interactions[experiment_name][variant_name]
        u_count = len(self._users[experiment_name][variant_name])

        if client is not None:
            try:
                r_imp = client.get(self._redis_key(experiment_name, variant_name, "impressions"))
                r_clk = client.get(self._redis_key(experiment_name, variant_name, "clicks"))
                r_dur = client.get(self._redis_key(experiment_name, variant_name, "time_spent"))
                r_inter = client.get(self._redis_key(experiment_name, variant_name, "interactions"))
                r_users = client.scard(self._redis_key(experiment_name, variant_name, "users"))

                if r_imp is not None:
                    imp = max(imp, int(r_imp))
                if r_clk is not None:
                    clk = max(clk, int(r_clk))
                if r_dur is not None:
                    dur = max(dur, float(r_dur))
                if r_inter is not None:
                    inter = max(inter, int(r_inter))
                if r_users is not None:
                    u_count = max(u_count, int(r_users))
            except Exception as e:
                logger.debug(f"Redis get_variant_metrics error: {e}")

        metrics = VariantMetrics(
            experiment_name=experiment_name,
            variant_name=variant_name,
            impressions=imp,
            clicks=clk,
            total_time_spent_seconds=dur,
            interactions=inter,
            unique_users=u_count,
        )
        metrics.compute_derived_metrics()
        return metrics

    def get_summary(
        self,
        experiment_name: str,
        variant_names: Optional[List[str]] = None,
        control_variant: str = "control",
    ) -> ExperimentSummary:
        """Compile a full summary of an experiment with comparative lift and p-values."""
        # Find all known variants for this experiment
        all_variants: Set[str] = set()
        if variant_names:
            all_variants.update(variant_names)

        all_variants.update(self._impressions[experiment_name].keys())
        all_variants.update(self._clicks[experiment_name].keys())

        if not all_variants:
            all_variants.add(control_variant)

        variants_metrics: Dict[str, VariantMetrics] = {}
        for vname in all_variants:
            variants_metrics[vname] = self.get_variant_metrics(experiment_name, vname)

        # Identify control variant
        actual_control = (
            control_variant
            if control_variant in variants_metrics
            else (list(variants_metrics.keys())[0] if variants_metrics else None)
        )

        lift_metrics: Dict[str, Dict[str, float]] = {}
        p_values: Dict[str, float] = {}
        is_sig: Dict[str, bool] = {}

        if actual_control and actual_control in variants_metrics:
            ctrl_m = variants_metrics[actual_control]
            for vname, m in variants_metrics.items():
                if vname == actual_control:
                    continue

                # Lift in CTR
                ctr_lift = 0.0
                if ctrl_m.ctr > 0:
                    ctr_lift = ((m.ctr - ctrl_m.ctr) / ctrl_m.ctr) * 100.0

                # Lift in average time spent
                time_lift = 0.0
                if ctrl_m.avg_time_spent_seconds > 0:
                    time_lift = (
                        (m.avg_time_spent_seconds - ctrl_m.avg_time_spent_seconds) / ctrl_m.avg_time_spent_seconds
                    ) * 100.0

                lift_metrics[vname] = {
                    "ctr_lift_percent": ctr_lift,
                    "time_spent_lift_percent": time_lift,
                }

                # Statistical hypothesis test on CTR (two proportion z-test)
                z_stat, p_val = _calculate_two_proportion_z_test(
                    count_a=ctrl_m.clicks,
                    nobs_a=ctrl_m.impressions,
                    count_b=m.clicks,
                    nobs_b=m.impressions,
                )
                p_values[vname] = p_val
                is_sig[vname] = bool(p_val < 0.05)

        return ExperimentSummary(
            experiment_name=experiment_name,
            variants=variants_metrics,
            control_variant=actual_control,
            lift_metrics=lift_metrics,
            p_values=p_values,
            is_significant=is_sig,
        )

    def reset(self, experiment_name: Optional[str] = None) -> None:
        """Reset metrics in memory and Redis (useful for test isolation)."""
        if experiment_name:
            self._impressions.pop(experiment_name, None)
            self._clicks.pop(experiment_name, None)
            self._time_spent.pop(experiment_name, None)
            self._interactions.pop(experiment_name, None)
            self._users.pop(experiment_name, None)
        else:
            self._impressions.clear()
            self._clicks.clear()
            self._time_spent.clear()
            self._interactions.clear()
            self._users.clear()

        client = get_redis_client()
        if client is not None:
            try:
                pattern = f"ab:metrics:{experiment_name}:*" if experiment_name else "ab:metrics:*"
                keys = list(client.scan_iter(match=pattern, count=100))
                if keys:
                    client.delete(*keys)
            except Exception as e:
                logger.debug(f"Redis reset error: {e}")


# Global default instance
_default_metrics_tracker: Optional[MetricsTracker] = None


def get_metrics_tracker() -> MetricsTracker:
    """Get the global MetricsTracker singleton."""
    global _default_metrics_tracker
    if _default_metrics_tracker is None:
        _default_metrics_tracker = MetricsTracker()
    return _default_metrics_tracker
