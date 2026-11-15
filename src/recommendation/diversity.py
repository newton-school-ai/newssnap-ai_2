"""NewsSnap AI - Recommendation Diversity and Filter Bubble Prevention (Issue 23).

Ensures recommendation feeds remain diverse and prevents filter bubbles:
- 20% diversity injection from underrepresented categories
- Filter bubble prevention (feed never > 50% single category)
- Balanced distribution and category affinity tracking
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.recommendation.content_based import extract_article_category, extract_article_id

logger = logging.getLogger(__name__)

DEFAULT_DIVERSITY_RATIO: float = 0.20  # 20% diversity picks
DEFAULT_MAX_CATEGORY_SHARE: float = 0.50  # Feed never > 50% single category


def _is_sequence_pair(obj: Any) -> bool:
    """Check if object is a sequence pair (tuple, list, SQLAlchemy Row, etc.)."""
    return isinstance(obj, (list, tuple, Sequence)) and not isinstance(obj, (str, bytes, dict))


def extract_item_category(item: Any) -> str:
    """Extract and normalize category slug from an item (dict, model, or tuple)."""
    if _is_sequence_pair(item) and len(item) >= 2:
        for sub in item:
            cat = extract_article_category(sub)
            if cat:
                return cat

    cat = extract_article_category(item)
    if cat:
        return cat

    if isinstance(item, dict):
        val = item.get("category") or item.get("category_slug") or item.get("category_name")
        if val:
            return str(val).lower().strip()

    if hasattr(item, "category"):
        c = getattr(item, "category")
        slug = getattr(c, "slug", None) or getattr(c, "name", None)
        if slug:
            return str(slug).lower().strip()

    return "general"


def extract_item_id(item: Any) -> Any:
    """Extract item or article identifier from an item."""
    if _is_sequence_pair(item) and len(item) >= 2:
        for sub in reversed(item):
            aid = extract_article_id(sub)
            if aid is not None:
                return aid

    aid = extract_article_id(item)
    if aid is not None:
        return aid

    if isinstance(item, dict):
        return item.get("id") or item.get("article_id") or item.get("snap_id")

    return getattr(item, "id", None) or getattr(item, "article_id", None)


@dataclass
class DiversityMetrics:
    """Evaluation metrics for a recommendation feed's diversity."""

    total_items: int
    category_counts: dict[str, int]
    category_shares: dict[str, float]
    max_category: str
    max_category_share: float
    num_unique_categories: int
    num_diverse_items: int
    diverse_ratio: float
    is_bubble_safe: bool


def calculate_category_distribution(items: Sequence[Any]) -> DiversityMetrics:
    """Calculate the category distribution and filter-bubble compliance metrics.

    Args:
        items: Sequence of recommendation items.

    Returns:
        DiversityMetrics dataclass with per-category shares and compliance flags.
    """
    total = len(items)
    if total == 0:
        return DiversityMetrics(
            total_items=0,
            category_counts={},
            category_shares={},
            max_category="",
            max_category_share=0.0,
            num_unique_categories=0,
            num_diverse_items=0,
            diverse_ratio=0.0,
            is_bubble_safe=True,
        )

    counts: dict[str, int] = Counter()
    for it in items:
        cat = extract_item_category(it)
        counts[cat] += 1

    shares = {cat: count / total for cat, count in counts.items()}
    max_cat, max_count = counts.most_common(1)[0]
    max_share = max_count / total

    # Bubble safe if no single category exceeds 50% (allow 100% only if total == 1)
    is_safe = max_share <= DEFAULT_MAX_CATEGORY_SHARE if total > 1 else True

    return DiversityMetrics(
        total_items=total,
        category_counts=dict(counts),
        category_shares=shares,
        max_category=max_cat,
        max_category_share=max_share,
        num_unique_categories=len(counts),
        num_diverse_items=total - max_count,
        diverse_ratio=(total - max_count) / total,
        is_bubble_safe=is_safe,
    )


class DiversityInjector:
    """Enforces diversity injection and prevents recommendation filter bubbles (Issue 23).

    Rules enforced:
    1. Filter Bubble Prevention: No single category may exceed 50% of the feed (max_category_share = 0.50).
    2. Diversity Injection: 20% of the feed (diversity_ratio = 0.20) is reserved for
       underrepresented categories (categories with lowest user affinity or zero interaction history).
    """

    def __init__(
        self,
        diversity_ratio: float = DEFAULT_DIVERSITY_RATIO,
        max_category_share: float = DEFAULT_MAX_CATEGORY_SHARE,
    ) -> None:
        """Initialize DiversityInjector.

        Args:
            diversity_ratio: Fraction of feed reserved for diverse picks (default: 0.20 / 20%).
            max_category_share: Maximum allowable share for any single category (default: 0.50 / 50%).
        """
        self.diversity_ratio = diversity_ratio
        self.max_category_share = max_category_share

    def inject_diversity(
        self,
        scored_candidates: Sequence[Tuple[float, Any]],
        user_category_affinity: Optional[Dict[str, float]] = None,
        limit: int = 20,
        interleave: bool = True,
    ) -> List[Any]:
        """Inject diverse items into the candidate ranking while enforcing filter bubble limits.

        Args:
            scored_candidates: Sequence of (score, item) tuples, assumed pre-sorted by score desc.
            user_category_affinity: Optional mapping of category -> user engagement affinity in [0, 1].
            limit: Maximum number of items to return in final feed.
            interleave: Whether to distribute diverse items smoothly through the feed.

        Returns:
            List of selected items obeying the 20% diversity and <= 50% category share constraints.
        """
        if not scored_candidates or limit <= 0:
            return []

        # 1. Determine target count and category ceiling
        available_total = len(scored_candidates)
        target_count = min(limit, available_total)
        if target_count == 0:
            return []

        # 2. Group candidates by category
        candidates_by_cat: dict[str, list[tuple[float, Any]]] = defaultdict(list)
        for score, item in scored_candidates:
            cat = extract_item_category(item)
            candidates_by_cat[cat].append((score, item))

        all_categories = list(candidates_by_cat.keys())

        # If only 1 category exists across all candidates, filter bubble enforcement is constrained by data
        if len(all_categories) <= 1:
            return [item for _, item in scored_candidates[:target_count]]

        # Max items allowed per category: floor(target_count * max_category_share)
        if target_count <= 1:
            max_per_category = 1
            diversity_count = 0
            core_count = target_count
        else:
            max_per_category = max(1, int(target_count * self.max_category_share))
            diversity_count = max(1, int(round(target_count * self.diversity_ratio)))
            core_count = target_count - diversity_count

        # 3. Identify dominant vs underrepresented categories
        affinity_map = user_category_affinity or {}

        # Dominant categories: high user affinity or high frequency in top candidates
        dominant_categories: set[str] = set()
        if affinity_map:
            # Categories with affinity > median or max affinity
            max_aff = max(affinity_map.values()) if affinity_map else 0.0
            dominant_categories = {c for c, aff in affinity_map.items() if aff >= (max_aff * 0.5) and aff > 0}
        else:
            # Infer dominant categories from top scored candidates
            top_sample = scored_candidates[: max(3, target_count // 2)]
            top_cats = [extract_item_category(it) for _, it in top_sample]
            dominant_categories = {c for c, count in Counter(top_cats).items() if count >= 2}

        # Underrepresented categories sorted by user affinity ascending (0 affinity first)
        underrepresented_categories = [c for c in all_categories if c not in dominant_categories]
        underrepresented_categories.sort(key=lambda c: affinity_map.get(c, 0.0))

        # Fallback if no category was deemed underrepresented
        if not underrepresented_categories:
            underrepresented_categories = sorted(all_categories, key=lambda c: affinity_map.get(c, 0.0))

        selected_ids: set[Any] = set()
        category_counts: Counter[str] = Counter()

        # 4. Select Diversity Items FIRST from underrepresented categories
        diversity_items: list[Any] = []
        for diverse_cat in underrepresented_categories:
            if len(diversity_items) >= diversity_count:
                break
            for score, item in candidates_by_cat[diverse_cat]:
                iid = extract_item_id(item)
                if iid is not None and iid in selected_ids:
                    continue
                if category_counts[diverse_cat] < max_per_category:
                    diversity_items.append(item)
                    if iid is not None:
                        selected_ids.add(iid)
                    category_counts[diverse_cat] += 1
                    break

        # If diversity quota not filled (e.g. only 1 diverse category), pick additional diverse candidates
        if len(diversity_items) < diversity_count:
            for diverse_cat in underrepresented_categories:
                if len(diversity_items) >= diversity_count:
                    break
                for score, item in candidates_by_cat[diverse_cat]:
                    if len(diversity_items) >= diversity_count:
                        break
                    iid = extract_item_id(item)
                    if iid is not None and iid in selected_ids:
                        continue
                    if category_counts[diverse_cat] < max_per_category:
                        diversity_items.append(item)
                        if iid is not None:
                            selected_ids.add(iid)
                        category_counts[diverse_cat] += 1

        # 5. Select Core Items from top hybrid-scored candidates respecting max_per_category
        core_items: list[Any] = []
        for score, item in scored_candidates:
            if len(core_items) >= core_count:
                break
            iid = extract_item_id(item)
            if iid is not None and iid in selected_ids:
                continue
            cat = extract_item_category(item)
            if category_counts[cat] < max_per_category:
                core_items.append(item)
                if iid is not None:
                    selected_ids.add(iid)
                category_counts[cat] += 1

        # 6. Backfill if total selected < target_count
        combined_selected = core_items + diversity_items
        if len(combined_selected) < target_count:
            for score, item in scored_candidates:
                if len(combined_selected) >= target_count:
                    break
                iid = extract_item_id(item)
                if iid is not None and iid in selected_ids:
                    continue
                cat = extract_item_category(item)
                if category_counts[cat] < max_per_category:
                    combined_selected.append(item)
                    if iid is not None:
                        selected_ids.add(iid)
                    category_counts[cat] += 1

        # Fallback if still short (relax category ceiling only to satisfy target count)
        if len(combined_selected) < target_count:
            for score, item in scored_candidates:
                if len(combined_selected) >= target_count:
                    break
                iid = extract_item_id(item)
                if iid is not None and iid in selected_ids:
                    continue
                combined_selected.append(item)
                if iid is not None:
                    selected_ids.add(iid)

        # 7. Interleave diversity picks smoothly through the feed
        if not interleave or not diversity_items:
            return combined_selected[:target_count]

        final_feed: list[Any] = []
        c_i = 0
        d_i = 0
        n_c = len(core_items)
        n_d = len(diversity_items)
        spacing = max(2, (n_c + n_d) // (n_d + 1))

        for idx in range(n_c + n_d):
            if (idx + 1) % (spacing + 1) == 0 and d_i < n_d:
                final_feed.append(diversity_items[d_i])
                d_i += 1
            elif c_i < n_c:
                final_feed.append(core_items[c_i])
                c_i += 1
            elif d_i < n_d:
                final_feed.append(diversity_items[d_i])
                d_i += 1

        # Append any remaining backfill items
        backfill_items = combined_selected[n_c + n_d :]
        final_feed.extend(backfill_items)

        return final_feed[:target_count]
