/**
 * NewsSnap AI - Category Badge Pill Component
 */

import React from 'react';
import { View, Text, StyleSheet, ViewStyle } from 'react-native';
import { getCategoryColor, typography, spacing, borderRadius } from '../theme';

export interface CategoryBadgeProps {
  category: string;
  style?: ViewStyle;
}

export const CategoryBadge: React.FC<CategoryBadgeProps> = ({ category, style }) => {
  const color = getCategoryColor(category);

  return (
    <View style={[styles.badge, { backgroundColor: `${color}18`, borderColor: `${color}40` }, style]}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={[styles.text, { color }]}>{category.toUpperCase()}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: spacing.xs,
  },
  text: {
    fontSize: typography.fontSizes.xs,
    fontWeight: typography.fontWeights.bold,
    letterSpacing: 0.5,
  },
});

export default CategoryBadge;

