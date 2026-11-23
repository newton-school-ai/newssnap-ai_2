/**
 * NewsSnap AI - CategoryChips Component
 * Horizontal scrolling category pills for filtering news and explore feeds.
 */

import React from 'react';
import {
  ScrollView,
  Text,
  TouchableOpacity,
  StyleSheet,
  View,
} from 'react-native';
import { colors, typography, spacing, borderRadius } from '../theme';

export interface CategoryOption {
  slug: string;
  name: string;
}

export interface CategoryChipsProps {
  categories: CategoryOption[];
  selectedCategory: string | null;
  onSelectCategory: (categorySlug: string | null) => void;
}

export const CategoryChips: React.FC<CategoryChipsProps> = ({
  categories,
  selectedCategory,
  onSelectCategory,
}) => {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.scrollContent}
    >
      {/* "All" Filter Chip */}
      <TouchableOpacity
        style={[
          styles.chip,
          selectedCategory === null ? styles.activeChip : styles.inactiveChip,
        ]}
        onPress={() => onSelectCategory(null)}
        activeOpacity={0.7}
      >
        <Text
          style={[
            styles.chipText,
            selectedCategory === null ? styles.activeChipText : styles.inactiveChipText,
          ]}
        >
          All
        </Text>
      </TouchableOpacity>

      {/* Dynamic Category Chips */}
      {categories.map((cat) => {
        const isSelected = selectedCategory === cat.slug;
        const categoryColor = colors.categories[cat.slug] || colors.primary;

        return (
          <TouchableOpacity
            key={cat.slug}
            style={[
              styles.chip,
              isSelected
                ? [styles.activeChip, { backgroundColor: categoryColor, borderColor: categoryColor }]
                : styles.inactiveChip,
            ]}
            onPress={() => onSelectCategory(isSelected ? null : cat.slug)}
            activeOpacity={0.7}
          >
            {/* Color indicator dot when inactive */}
            {!isSelected && (
              <View style={[styles.colorDot, { backgroundColor: categoryColor }]} />
            )}
            <Text
              style={[
                styles.chipText,
                isSelected ? styles.activeChipText : styles.inactiveChipText,
              ]}
            >
              {cat.name}
            </Text>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 7,
    paddingHorizontal: 14,
    borderRadius: borderRadius.full,
    marginRight: spacing.sm,
    borderWidth: 1,
  },
  activeChip: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  inactiveChip: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
  },
  colorDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  chipText: {
    fontSize: typography.fontSizes.xs,
    fontWeight: typography.fontWeights.medium,
  },
  activeChipText: {
    color: colors.textInverse,
    fontWeight: typography.fontWeights.semiBold,
  },
  inactiveChipText: {
    color: colors.textSecondary,
  },
});

export default CategoryChips;
