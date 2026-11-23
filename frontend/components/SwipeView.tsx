/**
 * NewsSnap AI - Vertical Swipe View Component
 * Provides 60 FPS full-screen paging swipe transitions between SnapCards.
 * Uses FlatList pagingEnabled with snapToInterval and viewability detection.
 */

import React, { useRef, useCallback, memo } from 'react';
import {
  FlatList,
  View,
  StyleSheet,
  useWindowDimensions,
  RefreshControl,
  ActivityIndicator,
  ViewToken,
  Platform,
} from 'react-native';

import { FeedItem } from '../api/feed';
import SnapCard from './SnapCard';
import { colors, spacing } from '../theme';

export interface SwipeViewProps {
  items: FeedItem[];
  onViewableSnapChanged?: (item: FeedItem, index: number) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  onEndReached: () => void;
  isLoadingMore: boolean;
  likedArticles: Record<string, boolean>;
  bookmarkedArticles: Record<string, boolean>;
  onToggleLike: (articleId: string) => void;
  onToggleBookmark: (articleId: string) => void;
  onShare: (item: FeedItem) => void;
  onReadMore: (item: FeedItem) => void;
  ListEmptyComponent?: React.ReactElement;
}

export const SwipeView: React.FC<SwipeViewProps> = memo(({
  items,
  onViewableSnapChanged,
  onRefresh,
  isRefreshing,
  onEndReached,
  isLoadingMore,
  likedArticles,
  bookmarkedArticles,
  onToggleLike,
  onToggleBookmark,
  onShare,
  onReadMore,
  ListEmptyComponent,
}) => {
  const { height } = useWindowDimensions();
  const flatListRef = useRef<FlatList<FeedItem>>(null);

  // Viewability configuration: Snap is considered "viewed" when 65% visible
  const viewabilityConfig = useRef({
    itemVisiblePercentThreshold: 65,
    minimumViewTime: 250,
  }).current;

  const onViewableItemsChanged = useCallback(
    ({ viewableItems }: { viewableItems: ViewToken[] }) => {
      if (viewableItems.length > 0 && viewableItems[0].isViewable) {
        const activeItem = viewableItems[0].item as FeedItem;
        const activeIndex = viewableItems[0].index ?? 0;
        if (onViewableSnapChanged && activeItem) {
          onViewableSnapChanged(activeItem, activeIndex);
        }
      }
    },
    [onViewableSnapChanged]
  );

  const getItemLayout = useCallback(
    (_: any, index: number) => ({
      length: height,
      offset: height * index,
      index,
    }),
    [height]
  );

  const renderItem = useCallback(
    ({ item }: { item: FeedItem }) => (
      <SnapCard
        item={item}
        height={height}
        isLiked={Boolean(likedArticles[item.article_id])}
        isBookmarked={Boolean(bookmarkedArticles[item.article_id])}
        onToggleLike={onToggleLike}
        onToggleBookmark={onToggleBookmark}
        onShare={onShare}
        onReadMore={onReadMore}
      />
    ),
    [height, likedArticles, bookmarkedArticles, onToggleLike, onToggleBookmark, onShare, onReadMore]
  );

  const keyExtractor = useCallback(
    (item: FeedItem, index: number) => item.snap_id || item.article_id || `snap-${index}`,
    []
  );

  const renderFooter = () => {
    if (!isLoadingMore) return null;
    return (
      <View style={styles.footerLoader}>
        <ActivityIndicator size="small" color={colors.primary} />
      </View>
    );
  };

  return (
    <FlatList
      ref={flatListRef}
      data={items}
      renderItem={renderItem}
      keyExtractor={keyExtractor}
      pagingEnabled={true}
      showsVerticalScrollIndicator={false}
      decelerationRate="fast"
      snapToInterval={height}
      snapToAlignment="start"
      getItemLayout={getItemLayout}
      initialNumToRender={2}
      maxToRenderPerBatch={3}
      windowSize={5}
      removeClippedSubviews={Platform.OS === 'android'}
      onViewableItemsChanged={onViewableItemsChanged}
      viewabilityConfig={viewabilityConfig}
      onEndReached={onEndReached}
      onEndReachedThreshold={0.5}
      refreshControl={
        <RefreshControl
          refreshing={isRefreshing}
          onRefresh={onRefresh}
          tintColor={colors.primary}
          colors={[colors.primary]}
        />
      }
      ListFooterComponent={renderFooter}
      ListEmptyComponent={ListEmptyComponent}
      contentContainerStyle={items.length === 0 ? styles.emptyContainer : undefined}
    />
  );
});

SwipeView.displayName = 'SwipeView';

const styles = StyleSheet.create({
  emptyContainer: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  footerLoader: {
    paddingVertical: spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default SwipeView;
