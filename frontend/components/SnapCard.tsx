/**
 * NewsSnap AI - SnapCard Component
 * Full-screen Instagram/Inshorts-style news card with image, category badge,
 * source attribution, concise bullet-point summary, and interaction bar.
 */

import React, { memo } from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { FeedItem } from '../api/feed';
import CategoryBadge from './CategoryBadge';
import InteractionBar from './InteractionBar';
import { colors, typography, spacing, borderRadius } from '../theme';

export interface SnapCardProps {
  item: FeedItem;
  height: number;
  isLiked: boolean;
  isBookmarked: boolean;
  onToggleLike: (articleId: string) => void;
  onToggleBookmark: (articleId: string) => void;
  onShare: (item: FeedItem) => void;
  onReadMore: (item: FeedItem) => void;
}

export const SnapCard: React.FC<SnapCardProps> = memo(({
  item,
  height,
  isLiked,
  isBookmarked,
  onToggleLike,
  onToggleBookmark,
  onShare,
  onReadMore,
}) => {
  const dynamicLikes = item.interaction_counts?.likes || 0;
  const dynamicBookmarks = item.interaction_counts?.bookmarks || 0;

  return (
    <View style={[styles.cardContainer, { height }]}>
      {/* Top Image Banner */}
      <View style={styles.imageContainer}>
        {item.image_url ? (
          <Image
            source={{ uri: item.image_url }}
            style={styles.image}
            resizeMode="cover"
          />
        ) : (
          <View style={styles.placeholderImage}>
            <Ionicons name="newspaper-outline" size={48} color={colors.textMuted} />
          </View>
        )}
      </View>

      {/* Main Content Area */}
      <View style={styles.contentWrapper}>
        {/* Category Badge & Metadata */}
        <View style={styles.metaRow}>
          <CategoryBadge category={item.category} size="sm" />
          <View style={styles.sourceMeta}>
            <Text style={styles.sourceText} numberOfLines={1}>
              {item.source}
            </Text>
            <Text style={styles.dotSeparator}>•</Text>
            <Text style={styles.timeText}>{item.time_ago}</Text>
          </View>
        </View>

        {/* Title */}
        <Text style={styles.titleText} numberOfLines={3}>
          {item.title}
        </Text>

        <View style={styles.divider} />

        {/* Summary (Concise 60-word news snap) */}
        <ScrollView
          style={styles.summaryScrollView}
          contentContainerStyle={styles.summaryContent}
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.summaryText}>
            {item.summary}
          </Text>
        </ScrollView>
      </View>

      {/* Bottom Interaction Bar */}
      <InteractionBar
        snapId={item.snap_id}
        articleId={item.article_id}
        likes={isLiked ? dynamicLikes + 1 : dynamicLikes}
        comments={item.interaction_counts?.comments || 0}
        shares={item.interaction_counts?.shares || 0}
        bookmarks={isBookmarked ? dynamicBookmarks + 1 : dynamicBookmarks}
        isLiked={isLiked}
        isBookmarked={isBookmarked}
        onToggleLike={() => onToggleLike(item.article_id)}
        onToggleBookmark={() => onToggleBookmark(item.article_id)}
        onShare={() => onShare(item)}
        onReadMore={() => onReadMore(item)}
      />
    </View>
  );
});

SnapCard.displayName = 'SnapCard';

const styles = StyleSheet.create({
  cardContainer: {
    width: '100%',
    backgroundColor: colors.background,
    justifyContent: 'space-between',
  },
  imageContainer: {
    width: '100%',
    height: '38%',
    backgroundColor: colors.cardAlt,
    overflow: 'hidden',
  },
  image: {
    width: '100%',
    height: '100%',
  },
  placeholderImage: {
    width: '100%',
    height: '100%',
    backgroundColor: colors.cardAlt,
    justifyContent: 'center',
    alignItems: 'center',
  },
  contentWrapper: {
    flex: 1,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  sourceMeta: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  sourceText: {
    fontSize: typography.fontSizes.xs,
    fontWeight: typography.fontWeights.medium,
    color: colors.textSecondary,
    maxWidth: 130,
  },
  dotSeparator: {
    fontSize: typography.fontSizes.xs,
    color: colors.textMuted,
    marginHorizontal: 4,
  },
  timeText: {
    fontSize: typography.fontSizes.xs,
    color: colors.textMuted,
  },
  titleText: {
    fontSize: typography.fontSizes.lg,
    fontWeight: typography.fontWeights.bold,
    lineHeight: 24,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  divider: {
    height: 1,
    backgroundColor: colors.divider,
    marginVertical: spacing.xs,
  },
  summaryScrollView: {
    flex: 1,
  },
  summaryContent: {
    paddingVertical: spacing.xs,
  },
  summaryText: {
    fontSize: typography.fontSizes.sm,
    lineHeight: 22,
    color: colors.textSecondary,
  },
});

export default SnapCard;
