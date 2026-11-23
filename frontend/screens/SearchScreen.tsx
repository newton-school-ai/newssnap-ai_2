/**
 * NewsSnap AI - Search & Discovery Screen
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  FlatList,
  TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

import { useLanguage } from '../context/LanguageContext';
import { RootNavigationProp } from '../navigation/types';
import CategoryBadge from '../components/CategoryBadge';
import { colors, typography, spacing, borderRadius } from '../theme';

const TRENDING_TOPICS = [
  '#Chandrayaan',
  '#Budget2026',
  '#TechNews',
  '#CricketWorldCup',
  '#Startups',
  '#AIRevolution',
];

export const SearchScreen: React.FC = () => {
  const navigation = useNavigation<RootNavigationProp>();
  const { t } = useLanguage();
  const [query, setQuery] = useState('');

  return (
    <View style={styles.container}>
      {/* Search Input Bar */}
      <View style={styles.searchBarContainer}>
        <Ionicons name="search" size={20} color={colors.textMuted} style={styles.searchIcon} />
        <TextInput
          style={styles.searchInput}
          placeholder={t('searchPlaceholder', 'Search topics, sources, or keywords...')}
          placeholderTextColor={colors.textMuted}
          value={query}
          onChangeText={setQuery}
          clearButtonMode="while-editing"
        />
        {query.length > 0 && (
          <TouchableOpacity onPress={() => setQuery('')}>
            <Ionicons name="close-circle" size={18} color={colors.textMuted} />
          </TouchableOpacity>
        )}
      </View>

      {/* Trending Topics Carousel */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>{t('trending', 'Trending Topics')}</Text>
        <View style={styles.tagsRow}>
          {TRENDING_TOPICS.map((tag) => (
            <TouchableOpacity
              key={tag}
              style={styles.tagPill}
              onPress={() => setQuery(tag.replace('#', ''))}
            >
              <Text style={styles.tagText}>{tag}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Empty / Result State */}
      <View style={styles.emptyContainer}>
        <Ionicons name="newspaper-outline" size={48} color={colors.textMuted} />
        <Text style={styles.emptyText}>
          {query ? `Search results for "${query}" will appear here` : 'Type a query above to explore multi-language snaps'}
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    padding: spacing.base,
  },
  searchBarContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.divider,
    height: 48,
    marginBottom: spacing.base,
  },
  searchIcon: {
    marginRight: spacing.sm,
  },
  searchInput: {
    flex: 1,
    fontSize: typography.fontSizes.base,
    color: colors.textPrimary,
  },
  section: {
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    fontSize: typography.fontSizes.md,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
    marginBottom: spacing.sm,
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  tagPill: {
    backgroundColor: `${colors.primary}10`,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: `${colors.primary}30`,
  },
  tagText: {
    fontSize: typography.fontSizes.sm,
    color: colors.primary,
    fontWeight: typography.fontWeights.medium,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  emptyText: {
    fontSize: typography.fontSizes.base,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.md,
  },
});

export default SearchScreen;

