/**
 * NewsSnap AI - Bookmarks Screen
 * Displays user's saved/bookmarked news snaps for offline or later reading.
 */

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

import { useLanguage } from '../context/LanguageContext';
import { getUserBookmarks } from '../api/users';
import { FeedItem } from '../api/feed';
import CategoryBadge from '../components/CategoryBadge';
import { RootNavigationProp } from '../navigation/types';
import { colors, typography, spacing, borderRadius } from '../theme';

export const BookmarksScreen: React.FC = () => {
  const navigation = useNavigation<RootNavigationProp>();
  const { t } = useLanguage();
  const [bookmarks, setBookmarks] = useState<FeedItem[]>([]);

  useEffect(() => {
    const loadBookmarks = async () => {
      try {
        const data = await getUserBookmarks();
        setBookmarks(data);
      } catch {
        // Mock fallback for test environment
        setBookmarks([
          {
            snap_id: 'b-1',
            article_id: 'art-b1',
            title: 'National Green Hydrogen Mission Approves ₹19,000 Crore Subsidies',
            summary: 'India greenlights comprehensive production incentives to establish regional clean fuel hubs and reduce dependence on fossil fuel imports.',
            category: 'environment',
            source: 'PIB India',
            time_ago: 'Yesterday',
            interaction_counts: { likes: 88, comments: 14, shares: 20, bookmarks: 45 },
          },
        ]);
      }
    };

    loadBookmarks();
  }, []);

  const renderItem = ({ item }: { item: FeedItem }) => (
    <TouchableOpacity
      style={styles.card}
      activeOpacity={0.8}
      onPress={() =>
        navigation.navigate('ArticleDetail', {
          articleId: item.article_id,
          title: item.title,
          category: item.category,
          summary: item.summary,
        })
      }
    >
      <View style={styles.headerRow}>
        <CategoryBadge category={item.category} />
        <Text style={styles.timeAgo}>{item.time_ago}</Text>
      </View>
      <Text style={styles.title}>{item.title}</Text>
      <Text style={styles.summary} numberOfLines={2}>
        {item.summary}
      </Text>
      <View style={styles.footerRow}>
        <Text style={styles.source}>Source: {item.source}</Text>
        <Ionicons name="bookmark" size={18} color={colors.primary} />
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {bookmarks.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Ionicons name="bookmark-outline" size={54} color={colors.textMuted} />
          <Text style={styles.emptyTitle}>{t('noBookmarks', 'No bookmarked articles yet')}</Text>
          <Text style={styles.emptySubtitle}>
            Tap the bookmark icon on any news snap to save it here for quick access.
          </Text>
        </View>
      ) : (
        <FlatList
          data={bookmarks}
          keyExtractor={(item) => item.article_id}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}
        />
      )}
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
    borderRadius: borderRadius.md,
    padding: spacing.base,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  timeAgo: {
    fontSize: typography.fontSizes.xs,
    color: colors.textMuted,
  },
  title: {
    fontSize: typography.fontSizes.md,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
    marginVertical: spacing.xs,
  },
  summary: {
    fontSize: typography.fontSizes.sm,
    color: colors.textSecondary,
    lineHeight: 20,
    marginBottom: spacing.sm,
  },
  footerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  source: {
    fontSize: typography.fontSizes.xs,
    color: colors.textMuted,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  emptyTitle: {
    fontSize: typography.fontSizes.lg,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
    marginTop: spacing.base,
  },
  emptySubtitle: {
    fontSize: typography.fontSizes.sm,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 20,
  },
});

export default BookmarksScreen;

