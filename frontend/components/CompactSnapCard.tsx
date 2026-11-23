/**
 * NewsSnap AI - CompactSnapCard Component
 * Compact news card designed for 2-column explore/trending grid and search results.
 */

import React from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import CategoryBadge from './CategoryBadge';
import { colors, typography, spacing, borderRadius } from '../theme';

export interface CompactSnapItem {
  id?: string;
  article_id?: string;
  snap_id?: string;
  title: string;
  summary?: string;
  image_url?: string;
  category: string;
  source: string;
  time_ago?: string;
  views?: number;
  likes?: number;
}

export interface CompactSnapCardProps {
  item: CompactSnapItem;
  onPress: () => void;
  width?: number;
}

export const CompactSnapCard: React.FC<CompactSnapCardProps> = ({
  item,
  onPress,
}) => {
  return (
    <TouchableOpacity
      style={styles.card}
      onPress={onPress}
      activeOpacity={0.8}
    >
      {/* Thumbnail Image */}
      <View style={styles.imageContainer}>
        {item.image_url ? (
          <Image
            source={{ uri: item.image_url }}
            style={styles.image}
            resizeMode="cover"
          />
        ) : (
          <View style={styles.placeholderContainer}>
            <Ionicons name="newspaper-outline" size={28} color={colors.textMuted} />
          </View>
        )}
        <View style={styles.badgeOverlay}>
          <CategoryBadge category={item.category} size="sm" />
        </View>
      </View>

      {/* Card Body */}
      <View style={styles.body}>
        <Text style={styles.title} numberOfLines={3}>
          {item.title}
        </Text>

        <View style={styles.metaRow}>
          <Text style={styles.sourceText} numberOfLines={1}>
            {item.source}
          </Text>
          {item.time_ago ? (
            <>
              <Text style={styles.dot}>•</Text>
              <Text style={styles.timeText}>{item.time_ago}</Text>
            </>
          ) : null}
        </View>
      </View>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  card: {
    flex: 1,
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.borderLight,
    overflow: 'hidden',
    margin: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  imageContainer: {
    width: '100%',
    height: 110,
    backgroundColor: colors.cardAlt,
    position: 'relative',
  },
  image: {
    width: '100%',
    height: '100%',
  },
  placeholderContainer: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.cardAlt,
  },
  badgeOverlay: {
    position: 'absolute',
    top: 6,
    left: 6,
  },
  body: {
    padding: spacing.sm,
    justifyContent: 'space-between',
    minHeight: 80,
  },
  title: {
    fontSize: typography.fontSizes.xs,
    fontWeight: typography.fontWeights.semiBold,
    color: colors.textPrimary,
    lineHeight: 18,
    marginBottom: spacing.xs,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 'auto',
  },
  sourceText: {
    fontSize: 10,
    color: colors.textSecondary,
    fontWeight: typography.fontWeights.medium,
    flexShrink: 1,
  },
  dot: {
    fontSize: 10,
    color: colors.textMuted,
    marginHorizontal: 3,
  },
  timeText: {
    fontSize: 10,
    color: colors.textMuted,
  },
});

export default CompactSnapCard;
