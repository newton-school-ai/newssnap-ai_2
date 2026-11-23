/**
 * NewsSnap AI - TrendingGrid Component
 * Displays a 2-column Instagram-style explore grid of top trending articles.
 */

import React from 'react';
import {
  FlatList,
  View,
  Text,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';

import CompactSnapCard, { CompactSnapItem } from './CompactSnapCard';
import { colors, typography, spacing } from '../theme';

export interface TrendingGridProps {
  items: CompactSnapItem[];
  onItemPress: (item: CompactSnapItem) => void;
  loading?: boolean;
  headerTitle?: string;
  emptyMessage?: string;
  ListHeaderComponent?: React.ReactElement;
}

export const TrendingGrid: React.FC<TrendingGridProps> = ({
  items,
  onItemPress,
  loading = false,
  headerTitle = '🔥 Trending Now',
  emptyMessage = 'No trending stories found',
  ListHeaderComponent,
}) => {
  if (loading && items.length === 0) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="small" color={colors.primary} />
        <Text style={styles.loadingText}>Loading trending stories...</Text>
      </View>
    );
  }

  const renderHeader = () => (
    <View>
      {ListHeaderComponent}
      {headerTitle ? (
        <View style={styles.headerRow}>
          <Text style={styles.headerTitle}>{headerTitle}</Text>
          <Text style={styles.itemCount}>{items.length} stories</Text>
        </View>
      ) : null}
    </View>
  );

  return (
    <FlatList
      data={items}
      numColumns={2}
      keyExtractor={(item, index) => item.article_id || item.snap_id || item.id || `grid-${index}`}
      renderItem={({ item }) => (
        <CompactSnapCard item={item} onPress={() => onItemPress(item)} />
      )}
      ListHeaderComponent={renderHeader()}
      contentContainerStyle={styles.gridContent}
      showsVerticalScrollIndicator={false}
      ListEmptyComponent={
        !loading ? (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>{emptyMessage}</Text>
          </View>
        ) : null
      }
    />
  );
};

const styles = StyleSheet.create({
  gridContent: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xl,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.xs,
    paddingVertical: spacing.md,
  },
  headerTitle: {
    fontSize: typography.fontSizes.md,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
  },
  itemCount: {
    fontSize: typography.fontSizes.xs,
    color: colors.textMuted,
  },
  loadingContainer: {
    padding: spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loadingText: {
    marginTop: spacing.sm,
    fontSize: typography.fontSizes.xs,
    color: colors.textMuted,
  },
  emptyContainer: {
    padding: spacing.xl,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: typography.fontSizes.sm,
    color: colors.textMuted,
  },
});

export default TrendingGrid;
