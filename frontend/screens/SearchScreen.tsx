/**
 * NewsSnap AI - Search & Explore Screen (Issue 27)
 * Instagram-style search with 300ms debounce, horizontal category chips,
 * 2-column trending explore grid, and persistent recent searches.
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  SafeAreaView,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';

import { useSearch } from '../hooks/useSearch';
import { useLanguage } from '../context/LanguageContext';
import SearchBar from '../components/SearchBar';
import CategoryChips from '../components/CategoryChips';
import TrendingGrid from '../components/TrendingGrid';
import { CompactSnapItem } from '../components/CompactSnapCard';
import { RootNavigationProp } from '../navigation/types';
import { colors, typography, spacing, borderRadius } from '../theme';

export const SearchScreen: React.FC = () => {
  const navigation = useNavigation<RootNavigationProp>();
  const { t } = useLanguage();

  const {
    query,
    setQuery,
    results,
    trendingItems,
    categories,
    selectedCategory,
    setSelectedCategory,
    recentSearches,
    removeRecentSearch,
    clearRecentSearches,
    isSearching,
    isLoadingTrending,
  } = useSearch();

  const handleCardPress = (item: CompactSnapItem) => {
    navigation.navigate('ArticleDetail', {
      articleId: item.article_id || item.snap_id || item.id || '',
      title: item.title,
      category: item.category,
      summary: item.summary,
    });
  };

  const isQueryActive = query.trim().length > 0;

  // Header Component rendered inside FlatList / TrendingGrid
  const renderHeader = () => (
    <View style={styles.headerWrapper}>
      {/* Search Input Bar with 300ms debounce */}
      <View style={styles.searchBarWrapper}>
        <SearchBar
          value={query}
          onChangeText={setQuery}
          loading={isSearching}
          placeholder={t('searchPlaceholder', 'Search news, topics, keywords...')}
        />
      </View>

      {/* Category Filter Chips */}
      <View style={styles.chipsWrapper}>
        <CategoryChips
          categories={categories}
          selectedCategory={selectedCategory}
          onSelectCategory={setSelectedCategory}
        />
      </View>

      {/* Recent Searches Section (shown only when query is empty and recent searches exist) */}
      {!isQueryActive && recentSearches.length > 0 && (
        <View style={styles.recentSearchesSection}>
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.sectionTitle}>{t('recentSearches', 'Recent Searches')}</Text>
            <TouchableOpacity onPress={clearRecentSearches} activeOpacity={0.7}>
              <Text style={styles.clearAllText}>Clear All</Text>
            </TouchableOpacity>
          </View>

          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.recentTagsScroll}
          >
            {recentSearches.map((searchTerm) => (
              <View key={searchTerm} style={styles.recentTagPill}>
                <TouchableOpacity
                  onPress={() => setQuery(searchTerm)}
                  activeOpacity={0.7}
                  style={styles.recentTagClickable}
                >
                  <Ionicons name="time-outline" size={14} color={colors.textMuted} />
                  <Text style={styles.recentTagText}>{searchTerm}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => removeRecentSearch(searchTerm)}
                  style={styles.removeTagButton}
                  accessibilityLabel={`Remove ${searchTerm}`}
                >
                  <Ionicons name="close" size={14} color={colors.textMuted} />
                </TouchableOpacity>
              </View>
            ))}
          </ScrollView>
        </View>
      )}
    </View>
  );

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        {isQueryActive ? (
          // Search Results View
          <TrendingGrid
            items={results}
            onItemPress={handleCardPress}
            loading={isSearching}
            headerTitle={
              isSearching
                ? 'Searching...'
                : `Search Results (${results.length})`
            }
            emptyMessage={
              isSearching
                ? 'Searching stories...'
                : `No results found for "${query}"`
            }
            ListHeaderComponent={renderHeader()}
          />
        ) : (
          // Trending Explore 2-Column Grid
          <TrendingGrid
            items={trendingItems}
            onItemPress={handleCardPress}
            loading={isLoadingTrending}
            headerTitle={
              selectedCategory
                ? `Top in ${selectedCategory.toUpperCase()}`
                : '🔥 Trending Stories'
            }
            emptyMessage="No trending stories found"
            ListHeaderComponent={renderHeader()}
          />
        )}
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  headerWrapper: {
    paddingBottom: spacing.xs,
  },
  searchBarWrapper: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xs,
  },
  chipsWrapper: {
    marginBottom: spacing.xs,
  },
  recentSearchesSection: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
    marginBottom: spacing.xs,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  sectionTitle: {
    fontSize: typography.fontSizes.sm,
    fontWeight: typography.fontWeights.semiBold,
    color: colors.textSecondary,
  },
  clearAllText: {
    fontSize: typography.fontSizes.xs,
    color: colors.primary,
    fontWeight: typography.fontWeights.medium,
  },
  recentTagsScroll: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  recentTagPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.borderLight,
    borderWidth: 1,
    borderRadius: borderRadius.full,
    paddingLeft: 10,
    paddingRight: 6,
    paddingVertical: 4,
    marginRight: spacing.sm,
  },
  recentTagClickable: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  recentTagText: {
    fontSize: typography.fontSizes.xs,
    color: colors.textPrimary,
    marginLeft: 4,
    marginRight: 6,
  },
  removeTagButton: {
    padding: 2,
  },
});

export default SearchScreen;
