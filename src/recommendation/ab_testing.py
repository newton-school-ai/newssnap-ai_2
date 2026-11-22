"""NewsSnap AI - A/B Testing Framework for Recommendations (Issue 24).

Enables experimentation and variant testing for recommendation strategies:
- Consistent deterministic variant assignment using hashing (salt + experiment + user_id)
- Configurable experiment variants, traffic fractions, and parameter overrides
- Safe fallback to control group for inactive experiments or out-of-traffic users
- Integration with RecommendationEngine scoring weights and diversity settings
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class ExperimentStatus(str, Enum):
    """Lifecycle status of an A/B experiment."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    CONCLUDED = "concluded"


@dataclass
class Variant:
    """An individual treatment or control variant within an experiment."""

    name: str
    traffic_ratio: float = 0.5  # Relative weight among variants in experiment
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None
    is_control: bool = False


@dataclass
class Experiment:
    """Definition of an A/B experimentation test."""

    name: str
    description: str
    variants: List[Variant]
    status: ExperimentStatus = ExperimentStatus.RUNNING
    traffic_fraction: float = 1.0  # Overall fraction of users included (0.0 to 1.0)
    salt: str = "newssnap_ab"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.variants:
            raise ValueError(f"Experiment '{self.name}' must have at least one variant")

        # Normalize traffic ratios so they sum to 1.0
        total_ratio = sum(v.traffic_ratio for v in self.variants)
        if total_ratio <= 0:
            raise ValueError(f"Total traffic ratio for experiment '{self.name}' must be positive")

        for v in self.variants:
            v.traffic_ratio = v.traffic_ratio / total_ratio

        # Ensure at least one control variant is identified
        has_control = any(v.is_control for v in self.variants)
        if not has_control and self.variants:
            self.variants[0].is_control = True


@dataclass
class VariantAssignment:
    """Result of evaluating a user for an experiment."""

    experiment_name: str
    user_id: str
    variant_name: str
    parameters: Dict[str, Any]
    is_control: bool
    is_in_experiment: bool
    assigned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ABTestManager:
    """Central manager for registering experiments and assigning users consistently."""

    def __init__(self) -> None:
        self._experiments: Dict[str, Experiment] = {}

    def register_experiment(self, experiment: Experiment) -> None:
        """Register or update an experiment definition."""
        self._experiments[experiment.name] = experiment
        logger.info(
            f"Registered A/B experiment '{experiment.name}' with "
            f"{len(experiment.variants)} variants (status={experiment.status.value})"
        )

    def get_experiment(self, name: str) -> Optional[Experiment]:
        """Retrieve an experiment definition by name."""
        return self._experiments.get(name)

    def list_experiments(self, status: Optional[ExperimentStatus] = None) -> List[Experiment]:
        """List registered experiments, optionally filtered by status."""
        if status is None:
            return list(self._experiments.values())
        return [exp for exp in self._experiments.values() if exp.status == status]

    def remove_experiment(self, name: str) -> bool:
        """Remove an experiment by name."""
        return self._experiments.pop(name, None) is not None

    def clear(self) -> None:
        """Clear all registered experiments (useful for testing)."""
        self._experiments.clear()

    def _normalize_user_id(self, user_id: Any) -> str:
        """Convert various user identifier types to a stable string."""
        if isinstance(user_id, UUID):
            return str(user_id)
        if hasattr(user_id, "id"):
            return str(getattr(user_id, "id"))
        return str(user_id).strip()

    def assign_variant(
        self,
        experiment_name: str,
        user_id: Any,
    ) -> VariantAssignment:
        """Deterministically assign a user to an experiment variant using SHA-256 hashing.

        Guarantee:
            The same (experiment_name, user_id) input will ALWAYS return the exact
            same variant, guaranteeing experiment group consistency across sessions.
        """
        uid_str = self._normalize_user_id(user_id)
        experiment = self._experiments.get(experiment_name)

        if not experiment or not experiment.variants:
            # Fallback when experiment is not found
            return VariantAssignment(
                experiment_name=experiment_name,
                user_id=uid_str,
                variant_name="control",
                parameters={},
                is_control=True,
                is_in_experiment=False,
            )

        control_variant = next(
            (v for v in experiment.variants if v.is_control),
            experiment.variants[0],
        )

        # Check if experiment is actively running
        now = datetime.now(timezone.utc)
        if experiment.status != ExperimentStatus.RUNNING:
            return VariantAssignment(
                experiment_name=experiment.name,
                user_id=uid_str,
                variant_name=control_variant.name,
                parameters=control_variant.parameters,
                is_control=True,
                is_in_experiment=False,
            )

        if experiment.start_time and now < experiment.start_time:
            return VariantAssignment(
                experiment_name=experiment.name,
                user_id=uid_str,
                variant_name=control_variant.name,
                parameters=control_variant.parameters,
                is_control=True,
                is_in_experiment=False,
            )

        if experiment.end_time and now > experiment.end_time:
            return VariantAssignment(
                experiment_name=experiment.name,
                user_id=uid_str,
                variant_name=control_variant.name,
                parameters=control_variant.parameters,
                is_control=True,
                is_in_experiment=False,
            )

        # Deterministic hashing: hash(experiment_name + salt + user_id)
        hash_input = f"{experiment.name}:{experiment.salt}:{uid_str}"
        digest = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        # Use first 8 hex characters (32 bits) for bucket mapping in range [0.0, 1.0)
        hash_val = int(digest[:8], 16)
        bucket = (hash_val % 10000) / 10000.0

        # Check if user falls within overall experiment traffic allocation
        if bucket >= experiment.traffic_fraction:
            return VariantAssignment(
                experiment_name=experiment.name,
                user_id=uid_str,
                variant_name=control_variant.name,
                parameters=control_variant.parameters,
                is_control=True,
                is_in_experiment=False,
            )

        # Scale bucket to [0.0, 1.0) for variant distribution
        scaled_bucket = bucket / max(1e-6, experiment.traffic_fraction)

        # Walk through normalized variant traffic ratios
        cumulative_ratio = 0.0
        selected_variant = experiment.variants[-1]
        for variant in experiment.variants:
            cumulative_ratio += variant.traffic_ratio
            if scaled_bucket < cumulative_ratio:
                selected_variant = variant
                break

        return VariantAssignment(
            experiment_name=experiment.name,
            user_id=uid_str,
            variant_name=selected_variant.name,
            parameters=selected_variant.parameters,
            is_control=selected_variant.is_control,
            is_in_experiment=True,
        )

    def get_variant_parameters(
        self,
        experiment_name: str,
        user_id: Any,
        default_parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convenience method to retrieve the variant parameters for a user."""
        assignment = self.assign_variant(experiment_name, user_id)
        defaults = dict(default_parameters or {})
        defaults.update(assignment.parameters)
        return defaults


# Global default instance
_default_ab_manager: Optional[ABTestManager] = None


def get_ab_test_manager() -> ABTestManager:
    """Get the global ABTestManager singleton."""
    global _default_ab_manager
    if _default_ab_manager is None:
        _default_ab_manager = ABTestManager()
    return _default_ab_manager
