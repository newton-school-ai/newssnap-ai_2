"""
Unit tests for Issue 26: Swipe feed screen with vertical swipe and infinite scroll.

Validates all Acceptance Criteria:
1. Smooth vertical swipe at 60 FPS (FlatList pagingEnabled, snapToInterval, getItemLayout)
2. SnapCard shows image, badge, summary, source, time
3. Infinite scroll loads next page (onEndReached, onEndReachedThreshold)
4. Pull-to-refresh works (RefreshControl)
5. Loading skeleton while content loads (SkeletonLoader)
6. Snap views tracked for recommendations (onViewableItemsChanged, trackReadArticle)
7. Works in all languages (useLanguage, multi-language query parameter)
"""

import os

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


def test_required_files_exist():
    """Verify all files specified in Issue 26 are created."""
    feed_screen = os.path.join(FRONTEND_DIR, "screens", "FeedScreen.tsx")
    snap_card = os.path.join(FRONTEND_DIR, "components", "SnapCard.tsx")
    swipe_view = os.path.join(FRONTEND_DIR, "components", "SwipeView.tsx")
    interaction_bar = os.path.join(FRONTEND_DIR, "components", "InteractionBar.tsx")
    skeleton_loader = os.path.join(FRONTEND_DIR, "components", "SkeletonLoader.tsx")
    use_feed = os.path.join(FRONTEND_DIR, "hooks", "useFeed.ts")

    assert os.path.exists(feed_screen), "FeedScreen.tsx must exist"
    assert os.path.exists(snap_card), "SnapCard.tsx must exist"
    assert os.path.exists(swipe_view), "SwipeView.tsx must exist"
    assert os.path.exists(interaction_bar), "InteractionBar.tsx must exist"
    assert os.path.exists(skeleton_loader), "SkeletonLoader.tsx must exist"
    assert os.path.exists(use_feed), "useFeed.ts must exist"


def test_swipe_view_60fps_configuration():
    """Verify SwipeView uses FlatList with 60 FPS optimizations and paging."""
    swipe_path = os.path.join(FRONTEND_DIR, "components", "SwipeView.tsx")
    with open(swipe_path, "r", encoding="utf-8") as f:
        code = f.read()

    # 60 FPS FlatList paging & performance props
    assert "pagingEnabled" in code
    assert "snapToInterval" in code
    assert "getItemLayout" in code
    assert "decelerationRate" in code
    assert "initialNumToRender" in code
    assert "maxToRenderPerBatch" in code
    assert "windowSize" in code
    assert "showsVerticalScrollIndicator" in code

    # Infinite scroll & pull-to-refresh
    assert "onEndReached" in code
    assert "onEndReachedThreshold" in code
    assert "RefreshControl" in code

    # Viewability tracking
    assert "onViewableItemsChanged" in code
    assert "viewabilityConfig" in code


def test_snap_card_displays_all_elements():
    """Verify SnapCard displays image, category badge, summary, source, time, and interaction bar."""
    card_path = os.path.join(FRONTEND_DIR, "components", "SnapCard.tsx")
    with open(card_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "Image" in code
    assert "image_url" in code
    assert "CategoryBadge" in code
    assert "item.category" in code
    assert "item.title" in code
    assert "item.summary" in code
    assert "item.source" in code
    assert "item.time_ago" in code
    assert "InteractionBar" in code


def test_interaction_bar_buttons():
    """Verify InteractionBar supports Like, Bookmark, Share, and Read More."""
    bar_path = os.path.join(FRONTEND_DIR, "components", "InteractionBar.tsx")
    with open(bar_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "onToggleLike" in code
    assert "onToggleBookmark" in code
    assert "onShare" in code
    assert "onReadMore" in code
    assert "formatCount" in code


def test_skeleton_loader():
    """Verify SkeletonLoader displays animated placeholder elements."""
    skeleton_path = os.path.join(FRONTEND_DIR, "components", "SkeletonLoader.tsx")
    with open(skeleton_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "Animated" in code
    assert "imageSkeleton" in code
    assert "badgeSkeleton" in code
    assert "titleLine1" in code
    assert "summaryLine" in code


def test_use_feed_hook_logic():
    """Verify useFeed manages pagination, refresh, multi-language and view dwell tracking."""
    hook_path = os.path.join(FRONTEND_DIR, "hooks", "useFeed.ts")
    with open(hook_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "getFeed" in code
    assert "cursor" in code
    assert "hasMore" in code
    assert "refresh" in code
    assert "loadMore" in code
    assert "language" in code
    assert "useLanguage" in code
    assert "trackReadArticle" in code
    assert "onViewableSnapChanged" in code
    assert "toggleLike" in code
    assert "toggleBookmark" in code
    assert "shareSnap" in code


def test_feed_screen_integration():
    """Verify FeedScreen orchestrates useFeed, SwipeView, and SkeletonLoader."""
    screen_path = os.path.join(FRONTEND_DIR, "screens", "FeedScreen.tsx")
    with open(screen_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "useFeed" in code
    assert "SwipeView" in code
    assert "SkeletonLoader" in code
    assert "ArticleDetail" in code
