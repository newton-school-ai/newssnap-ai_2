/**
 * NewsSnap AI - Feed Screen (Issue 26)
 * Full-screen vertical swipe news feed with infinite scroll, pull-to-refresh,
 * skeleton loading, snap view tracking, and multi-language support.
 */

import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

import { useFeed } from '../hooks/useFeed';
import { useLanguage } from '../context/LanguageContext';
import SwipeView from '../components/SwipeView';
import SkeletonLoader from '../components/SkeletonLoader';
import { FeedItem } from '../api/feed';
import { RootNavigationProp } from '../navigation/types';
import { colors, typography, spacing, borderRadius } from '../theme';

export const FeedScreen: React.FC = () => {
  const navigation = useNavigation<RootNavigationProp>();
  const { t } = useLanguage();

  const {
    items,
    isLoading,
    isRefreshing,
    isLoadingMore,
    error,
    likedArticles,
    bookmarkedArticles,
    refresh,
    loadMore,
    toggleLike,
    toggleBookmark,
    shareSnap,
    onViewableSnapChanged,
  } = useFeed();

  const handleReadMore = (item: FeedItem) => {
    navigation.navigate('ArticleDetail', {
      articleId: item.article_id,
      title: item.title,
      category: item.category,
      summary: item.summary,
    });
  };

  // 1. Initial Loading State: Render SkeletonLoader
  if (isLoading && items.length === 0) {
    return <SkeletonLoader />;
  }

  // 2. Error State with Retry Button
  if (error && items.length === 0) {
    return (
      <View style={styles.centerContainer}>
        <Ionicons name="cloud-offline-outline" size={54} color={colors.textMuted} />
        <Text style={styles.errorTitle}>Could not load feed</Text>
        <Text style={styles.errorSubtitle}>{error}</Text>
        <TouchableOpacity style={styles.retryButton} onPress={refresh} activeOpacity={0.8}>
          <Text style={styles.retryText}>Retry</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // 3. Empty Feed Fallback
  const renderEmptyComponent = () => (
    <View style={styles.centerContainer}>
      <Ionicons name="newspaper-outline" size={54} color={colors.textMuted} />
      <Text style={styles.emptyTitle}>No snaps available right now</Text>
      <Text style={styles.emptySubtitle}>Pull down to check for breaking news stories</Text>
      <TouchableOpacity style={styles.retryButton} onPress={refresh} activeOpacity={0.8}>
        <Text style={styles.retryText}>{t('refresh', 'Refresh')}</Text>
      </TouchableOpacity>
    </View>
  );

  // 4. Main 60 FPS Vertical Swipe View
  return (
    <View style={styles.container}>
      <SwipeView
        items={items}
        onViewableSnapChanged={onViewableSnapChanged}
        onRefresh={refresh}
        isRefreshing={isRefreshing}
        onEndReached={loadMore}
        isLoadingMore={isLoadingMore}
        likedArticles={likedArticles}
        bookmarkedArticles={bookmarkedArticles}
        onToggleLike={toggleLike}
        onToggleBookmark={toggleBookmark}
        onShare={shareSnap}
        onReadMore={handleReadMore}
        ListEmptyComponent={renderEmptyComponent()}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
    backgroundColor: colors.background,
  },
  errorTitle: {
    fontSize: typography.fontSizes.lg,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  errorSubtitle: {
    fontSize: typography.fontSizes.sm,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.lg,
  },
  emptyTitle: {
    fontSize: typography.fontSizes.lg,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  emptySubtitle: {
    fontSize: typography.fontSizes.sm,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.lg,
  },
  retryButton: {
    backgroundColor: colors.primary,
    paddingVertical: 10,
    paddingHorizontal: 24,
    borderRadius: borderRadius.full,
  },
  retryText: {
    color: colors.textInverse,
    fontSize: typography.fontSizes.sm,
    fontWeight: typography.fontWeights.semiBold,
  },
});

export default FeedScreen;
