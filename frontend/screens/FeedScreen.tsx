/**
 * NewsSnap AI - Swipe Feed Screen
 * Native swipe feed layout displaying news snaps with category badges and interaction bars.
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  Share,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

import { FeedItem, getFeed, toggleLikeArticle, toggleBookmarkArticle, trackShareArticle } from '../api/feed';
import { useLanguage } from '../context/LanguageContext';
import CategoryBadge from '../components/CategoryBadge';
import { RootNavigationProp } from '../navigation/types';
import { colors, typography, spacing, borderRadius } from '../theme';

export const FeedScreen: React.FC = () => {
  const navigation = useNavigation<RootNavigationProp>();
  const { language, t } = useLanguage();

  const [feedItems, setFeedItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [likedArticles, setLikedArticles] = useState<Record<string, boolean>>({});
  const [bookmarkedArticles, setBookmarkedArticles] = useState<Record<string, boolean>>({});

  const loadFeed = async () => {
    setLoading(true);
    try {
      const response = await getFeed({ language, limit: 20 });
      setFeedItems(response.items || response.snaps || []);
    } catch (e) {
      // Mock fallback data for offline/test environments
      setFeedItems([
        {
          snap_id: 'snap-1',
          article_id: 'art-1',
          title: 'ISRO Gears Up for Next Major Lunar Exploration Mission',
          summary: 'India’s space agency ISRO announces its upcoming lunar rover launch scheduled for late 2026, targeting polar crater exploration with indigenous sensors and deep space communication.',
          category: 'science',
          source: 'The Hindu',
          time_ago: '2h ago',
          interaction_counts: { likes: 142, comments: 24, shares: 18, bookmarks: 52 },
        },
        {
          snap_id: 'snap-2',
          article_id: 'art-2',
          title: 'India UPI Global Expansion Reaches 15 New Nations',
          summary: 'Unified Payments Interface expands international footprint across Southeast Asia and Europe, enabling instant cross-border payments with zero surcharge for travelers.',
          category: 'finance',
          source: 'Economic Times',
          time_ago: '4h ago',
          interaction_counts: { likes: 215, comments: 38, shares: 45, bookmarks: 89 },
        },
        {
          snap_id: 'snap-3',
          article_id: 'art-3',
          title: 'Next-Gen Electric Vehicle Battery Plant Breaks Ground in Tamil Nadu',
          summary: 'A 20 GWh lithium iron phosphate gigafactory commences construction, expected to generate 10,000 local manufacturing jobs and accelerate domestic EV adoption.',
          category: 'technology',
          source: 'LiveMint',
          time_ago: '6h ago',
          interaction_counts: { likes: 98, comments: 12, shares: 9, bookmarks: 34 },
        },
      ]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadFeed();
  }, [language]);

  const onRefresh = () => {
    setRefreshing(true);
    loadFeed();
  };

  const handleLike = async (articleId: string) => {
    setLikedArticles((prev) => ({ ...prev, [articleId]: !prev[articleId] }));
    try {
      await toggleLikeArticle(articleId);
    } catch {
      // Optimistic state kept
    }
  };

  const handleBookmark = async (articleId: string) => {
    setBookmarkedArticles((prev) => ({ ...prev, [articleId]: !prev[articleId] }));
    try {
      await toggleBookmarkArticle(articleId);
    } catch {
      // Optimistic state kept
    }
  };

  const handleShare = async (item: FeedItem) => {
    try {
      await Share.share({
        message: `${item.title}\n\nRead more on NewsSnap AI: https://newssnap.ai/article/${item.article_id}`,
      });
      await trackShareArticle(item.article_id);
    } catch {
      // Share dialog closed
    }
  };

  const renderCard = ({ item }: { item: FeedItem }) => {
    const isLiked = likedArticles[item.article_id];
    const isBookmarked = bookmarkedArticles[item.article_id];

    return (
      <TouchableOpacity
        style={styles.card}
        activeOpacity={0.9}
        onPress={() =>
          navigation.navigate('ArticleDetail', {
            articleId: item.article_id,
            title: item.title,
            category: item.category,
            summary: item.summary,
          })
        }
      >
        {/* Category & Time */}
        <View style={styles.cardHeader}>
          <CategoryBadge category={item.category} />
          <Text style={styles.timeAgo}>{item.time_ago}</Text>
        </View>

        {/* Headline */}
        <Text style={styles.headline}>{item.title}</Text>

        {/* 60-Word Snap Summary */}
        <Text style={styles.summary} numberOfLines={4}>
          {item.summary}
        </Text>

        {/* Source & Actions Footer */}
        <View style={styles.cardFooter}>
          <Text style={styles.sourceText}>By {item.source}</Text>

          <View style={styles.actionsRow}>
            {/* Like */}
            <TouchableOpacity
              style={styles.actionBtn}
              onPress={() => handleLike(item.article_id)}
            >
              <Ionicons
                name={isLiked ? 'heart' : 'heart-outline'}
                size={22}
                color={isLiked ? colors.error : colors.textSecondary}
              />
              <Text style={styles.actionCount}>
                {(item.interaction_counts?.likes || 0) + (isLiked ? 1 : 0)}
              </Text>
            </TouchableOpacity>

            {/* Bookmark */}
            <TouchableOpacity
              style={styles.actionBtn}
              onPress={() => handleBookmark(item.article_id)}
            >
              <Ionicons
                name={isBookmarked ? 'bookmark' : 'bookmark-outline'}
                size={22}
                color={isBookmarked ? colors.primary : colors.textSecondary}
              />
            </TouchableOpacity>

            {/* Share */}
            <TouchableOpacity
              style={styles.actionBtn}
              onPress={() => handleShare(item)}
            >
              <Ionicons name="share-social-outline" size={22} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <FlatList
        data={feedItems}
        keyExtractor={(item) => item.snap_id || item.article_id}
        renderItem={renderCard}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[colors.primary]} />}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  listContent: {
    padding: spacing.base,
    gap: spacing.base,
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.lg,
    padding: spacing.base,
    borderWidth: 1,
    borderColor: colors.divider,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  timeAgo: {
    fontSize: typography.fontSizes.xs,
    color: colors.textMuted,
  },
  headline: {
    fontSize: typography.fontSizes.lg,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
    lineHeight: 26,
    marginBottom: spacing.sm,
  },
  summary: {
    fontSize: typography.fontSizes.base,
    color: colors.textSecondary,
    lineHeight: 22,
    marginBottom: spacing.md,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: colors.divider,
    paddingTop: spacing.sm,
  },
  sourceText: {
    fontSize: typography.fontSizes.xs,
    fontWeight: typography.fontWeights.semiBold,
    color: colors.textSecondary,
  },
  actionsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.xs,
  },
  actionCount: {
    fontSize: typography.fontSizes.xs,
    color: colors.textSecondary,
    marginLeft: 4,
  },
});

export default FeedScreen;

