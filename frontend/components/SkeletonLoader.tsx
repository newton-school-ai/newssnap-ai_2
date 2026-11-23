/**
 * NewsSnap AI - Skeleton Loader Component
 * Displays an animated shimmering placeholder matching the full-screen SnapCard layout.
 */

import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated, useWindowDimensions } from 'react-native';
import { colors, spacing, borderRadius } from '../theme';

interface SkeletonLoaderProps {
  count?: number;
}

export const SkeletonLoader: React.FC<SkeletonLoaderProps> = () => {
  const { height } = useWindowDimensions();
  const animatedValue = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(animatedValue, {
          toValue: 0.8,
          duration: 800,
          useNativeDriver: true,
        }),
        Animated.timing(animatedValue, {
          toValue: 0.3,
          duration: 800,
          useNativeDriver: true,
        }),
      ])
    );
    animation.start();

    return () => animation.stop();
  }, [animatedValue]);

  return (
    <View style={[styles.container, { height }]}>
      {/* Hero Image Skeleton */}
      <Animated.View
        style={[
          styles.imageSkeleton,
          { opacity: animatedValue, backgroundColor: colors.border },
        ]}
      />

      {/* Content Skeleton */}
      <View style={styles.contentContainer}>
        {/* Badge & Source Bar */}
        <View style={styles.topBar}>
          <Animated.View
            style={[
              styles.badgeSkeleton,
              { opacity: animatedValue, backgroundColor: colors.border },
            ]}
          />
          <Animated.View
            style={[
              styles.sourceSkeleton,
              { opacity: animatedValue, backgroundColor: colors.border },
            ]}
          />
        </View>

        {/* Title Skeleton (2 lines) */}
        <Animated.View
          style={[
            styles.titleLine1,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />
        <Animated.View
          style={[
            styles.titleLine2,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />

        {/* Divider */}
        <View style={styles.divider} />

        {/* Summary Skeleton (4 lines) */}
        <Animated.View
          style={[
            styles.summaryLine,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />
        <Animated.View
          style={[
            styles.summaryLine,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />
        <Animated.View
          style={[
            styles.summaryLine,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />
        <Animated.View
          style={[
            styles.summaryLineShort,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />
      </View>

      {/* Interaction Bar Skeleton */}
      <View style={styles.bottomBar}>
        <Animated.View
          style={[
            styles.actionSkeleton,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />
        <Animated.View
          style={[
            styles.actionSkeleton,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />
        <Animated.View
          style={[
            styles.actionSkeleton,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />
        <Animated.View
          style={[
            styles.actionSkeletonWide,
            { opacity: animatedValue, backgroundColor: colors.border },
          ]}
        />
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    backgroundColor: colors.background,
    justifyContent: 'space-between',
    paddingBottom: 24,
  },
  imageSkeleton: {
    width: '100%',
    height: '42%',
    borderBottomLeftRadius: borderRadius.lg,
    borderBottomRightRadius: borderRadius.lg,
  },
  contentContainer: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    flex: 1,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  badgeSkeleton: {
    width: 90,
    height: 24,
    borderRadius: borderRadius.full,
  },
  sourceSkeleton: {
    width: 80,
    height: 16,
    borderRadius: borderRadius.sm,
  },
  titleLine1: {
    width: '100%',
    height: 22,
    borderRadius: borderRadius.sm,
    marginBottom: spacing.xs,
  },
  titleLine2: {
    width: '70%',
    height: 22,
    borderRadius: borderRadius.sm,
    marginBottom: spacing.md,
  },
  divider: {
    height: 1,
    backgroundColor: colors.divider,
    marginVertical: spacing.sm,
  },
  summaryLine: {
    width: '100%',
    height: 14,
    borderRadius: borderRadius.xs,
    marginBottom: spacing.sm,
  },
  summaryLineShort: {
    width: '60%',
    height: 14,
    borderRadius: borderRadius.xs,
    marginBottom: spacing.sm,
  },
  bottomBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  actionSkeleton: {
    width: 50,
    height: 32,
    borderRadius: borderRadius.md,
  },
  actionSkeletonWide: {
    width: 110,
    height: 32,
    borderRadius: borderRadius.md,
  },
});

export default SkeletonLoader;
