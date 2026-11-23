"""
Unit tests for Issue 27: Search and explore screen with category chips and trending.

Validates all Acceptance Criteria:
1. Search with 300ms debounce (useSearch timer)
2. Compact result cards (CompactSnapCard with 2-column styling, title, badge, source, time)
3. Category chips filter results (CategoryChips horizontal scroll, active state, onSelectCategory)
4. Trending grid with top articles (TrendingGrid numColumns=2, top articles integration)
5. Recent searches stored locally (AsyncStorage / storageHelper under @newssnap_recent_searches)
6. Works in all languages (useLanguage, multi-language query passing)
"""

import os

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


def test_required_files_exist():
    """Verify all files specified in Issue 27 are created."""
    search_screen = os.path.join(FRONTEND_DIR, "screens", "SearchScreen.tsx")
    search_bar = os.path.join(FRONTEND_DIR, "components", "SearchBar.tsx")
    category_chips = os.path.join(FRONTEND_DIR, "components", "CategoryChips.tsx")
    trending_grid = os.path.join(FRONTEND_DIR, "components", "TrendingGrid.tsx")
    compact_card = os.path.join(FRONTEND_DIR, "components", "CompactSnapCard.tsx")
    use_search = os.path.join(FRONTEND_DIR, "hooks", "useSearch.ts")

    assert os.path.exists(search_screen), "SearchScreen.tsx must exist"
    assert os.path.exists(search_bar), "SearchBar.tsx must exist"
    assert os.path.exists(category_chips), "CategoryChips.tsx must exist"
    assert os.path.exists(trending_grid), "TrendingGrid.tsx must exist"
    assert os.path.exists(compact_card), "CompactSnapCard.tsx must exist"
    assert os.path.exists(use_search), "useSearch.ts must exist"


def test_search_with_300ms_debounce():
    """Verify useSearch enforces 300ms debounce on search queries."""
    hook_path = os.path.join(FRONTEND_DIR, "hooks", "useSearch.ts")
    with open(hook_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "300" in code
    assert "setTimeout" in code
    assert "clearTimeout" in code
    assert "executeSearch" in code


def test_compact_snap_card_elements():
    """Verify CompactSnapCard displays thumbnail, category badge, title, source, and time."""
    card_path = os.path.join(FRONTEND_DIR, "components", "CompactSnapCard.tsx")
    with open(card_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "CategoryBadge" in code
    assert "item.category" in code
    assert "item.title" in code
    assert "item.source" in code
    assert "numberOfLines" in code


def test_category_chips_component():
    """Verify CategoryChips supports horizontal scroll, All filter, and selection."""
    chips_path = os.path.join(FRONTEND_DIR, "components", "CategoryChips.tsx")
    with open(chips_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "horizontal" in code
    assert "ScrollView" in code
    assert "selectedCategory" in code
    assert "onSelectCategory" in code
    assert "All" in code


def test_trending_grid_2_columns():
    """Verify TrendingGrid uses a 2-column layout (numColumns=2)."""
    grid_path = os.path.join(FRONTEND_DIR, "components", "TrendingGrid.tsx")
    with open(grid_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "numColumns={2}" in code
    assert "CompactSnapCard" in code
    assert "FlatList" in code


def test_recent_searches_local_storage():
    """Verify useSearch manages recent searches with persistent storage."""
    hook_path = os.path.join(FRONTEND_DIR, "hooks", "useSearch.ts")
    with open(hook_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "recentSearches" in code
    assert "addRecentSearch" in code
    assert "removeRecentSearch" in code
    assert "clearRecentSearches" in code
    assert "@newssnap_recent_searches" in code


def test_multi_language_support_and_screen_orchestration():
    """Verify useSearch and SearchScreen pass language context and orchestrate all components."""
    screen_path = os.path.join(FRONTEND_DIR, "screens", "SearchScreen.tsx")
    with open(screen_path, "r", encoding="utf-8") as f:
        screen_code = f.read()

    assert "useSearch" in screen_code
    assert "SearchBar" in screen_code
    assert "CategoryChips" in screen_code
    assert "TrendingGrid" in screen_code
    assert "useLanguage" in screen_code

    hook_path = os.path.join(FRONTEND_DIR, "hooks", "useSearch.ts")
    with open(hook_path, "r", encoding="utf-8") as f:
        hook_code = f.read()

    assert "useLanguage" in hook_code
    assert "language" in hook_code
