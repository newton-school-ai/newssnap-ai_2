/**
 * NewsSnap AI - Interaction Bar Component
 * Anchored action bar featuring Like, Bookmark, Share, and Read Full Story buttons.
 */

import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, typography, spacing, borderRadius } from '../theme';

export interface InteractionBarProps {
  snapId: string;
  articleId: string;
  likes: number;
  comments: number;
  shares: number;
  bookmarks: number;
  isLiked: boolean;
  isBookmarked: boolean;
  onToggleLike: () => void;
  onToggleBookmark: () => void;
  onShare: () => void;
  onReadMore?: () => void;
}

const formatCount = (count: number): string => {
  if (!count || count <= 0) return '0';
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}k`;
  }
  return String(count);
};

export const InteractionBar: React.FC<InteractionBarProps> = ({
  likes,
  shares,
  bookmarks,
  isLiked,
  isBookmarked,
  onToggleLike,
  onToggleBookmark,
  onShare,
  onReadMore,
}) => {
  return (
    <View style={styles.container}>
      {/* Like Button */}
      <TouchableOpacity
        style={styles.actionButton}
        onPress={onToggleLike}
        activeOpacity={0.7}
        accessibilityLabel="Like snap"
      >
        <Ionicons
          name={isLiked ? 'heart' : 'heart-outline'}
          size={24}
          color={isLiked ? colors.error : colors.textSecondary}
        />
        <Text
          style={[
            styles.countText,
            isLiked && { color: colors.error, fontWeight: typography.fontWeights.semiBold },
          ]}
        >
          {formatCount(likes)}
        </Text>
      </TouchableOpacity>

      {/* Bookmark Button */}
      <TouchableOpacity
        style={styles.actionButton}
        onPress={onToggleBookmark}
        activeOpacity={0.7}
        accessibilityLabel="Bookmark snap"
      >
        <Ionicons
          name={isBookmarked ? 'bookmark' : 'bookmark-outline'}
          size={24}
          color={isBookmarked ? colors.primary : colors.textSecondary}
        />
        <Text
          style={[
            styles.countText,
            isBookmarked && { color: colors.primary, fontWeight: typography.fontWeights.semiBold },
          ]}
        >
          {formatCount(bookmarks)}
        </Text>
      </TouchableOpacity>

      {/* Share Button */}
      <TouchableOpacity
        style={styles.actionButton}
        onPress={onShare}
        activeOpacity={0.7}
        accessibilityLabel="Share snap"
      >
        <Ionicons name="share-social-outline" size={24} color={colors.textSecondary} />
        <Text style={styles.countText}>{formatCount(shares)}</Text>
      </TouchableOpacity>

      {/* Read More Button */}
      {onReadMore && (
        <TouchableOpacity
          style={styles.readMoreButton}
          onPress={onReadMore}
          activeOpacity={0.8}
          accessibilityLabel="Read full article"
        >
          <Text style={styles.readMoreText}>Full Story</Text>
          <Ionicons name="chevron-forward" size={16} color={colors.primary} />
        </TouchableOpacity>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
  },
  countText: {
    fontSize: typography.fontSizes.sm,
    color: colors.textSecondary,
    marginLeft: 6,
    fontWeight: typography.fontWeights.medium,
  },
  readMoreButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.cardAlt,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: colors.border,
  },
  readMoreText: {
    fontSize: typography.fontSizes.xs,
    color: colors.primary,
    fontWeight: typography.fontWeights.semiBold,
    marginRight: 2,
  },
});

export default InteractionBar;
