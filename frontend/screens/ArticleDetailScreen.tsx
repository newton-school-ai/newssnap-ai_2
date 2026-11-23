/**
 * NewsSnap AI - Article Detail Screen
 * Shows full article summary, category, source attribution, and interactive actions.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Share,
  Linking,
  Alert,
} from 'react-native';
import { RouteProp, useRoute, useNavigation } from '@react-navigation/native';
import { RootStackParamList } from '../navigation/types';
import { useTheme } from '../context/ThemeContext';
import { useLanguage } from '../context/LanguageContext';
import { CategoryBadge } from '../components/CategoryBadge';
import { feedApi } from '../api/feed';

type ArticleDetailRouteProp = RouteProp<RootStackParamList, 'ArticleDetail'>;

export const ArticleDetailScreen: React.FC = () => {
  const { colors, typography, spacing } = useTheme();
  const { t } = useLanguage();
  const route = useRoute<ArticleDetailRouteProp>();
  const navigation = useNavigation();

  const { articleId, title, category, summary } = route.params;

  const [isLiked, setIsLiked] = useState(false);
  const [isBookmarked, setIsBookmarked] = useState(false);

  const handleToggleLike = async () => {
    try {
      setIsLiked(!isLiked);
      await feedApi.trackInteraction(articleId, 'like');
    } catch {
      // Revert if failed
      setIsLiked(isLiked);
    }
  };

  const handleToggleBookmark = async () => {
    try {
      setIsBookmarked(!isBookmarked);
      await feedApi.bookmarkArticle(articleId);
    } catch {
      setIsBookmarked(isBookmarked);
    }
  };

  const handleShare = async () => {
    try {
      await Share.share({
        message: `${title}\n\n${summary || ''}\n\nRead more on NewsSnap AI`,
      });
      await feedApi.trackInteraction(articleId, 'share');
    } catch (err: any) {
      Alert.alert('Share error', err.message);
    }
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <ScrollView
        contentContainerStyle={[styles.contentContainer, { padding: spacing.lg }]}
        showsVerticalScrollIndicator={false}
      >
        {category ? (
          <View style={styles.badgeWrapper}>
            <CategoryBadge category={category} size="md" />
          </View>
        ) : null}

        <Text style={[styles.title, { color: colors.textPrimary, marginBottom: spacing.md }]}>
          {title}
        </Text>

        <View style={[styles.divider, { backgroundColor: colors.borderLight, marginBottom: spacing.lg }]} />

        <Text style={[styles.summary, { color: colors.textSecondary, marginBottom: spacing.xl }]}>
          {summary || 'Detailed summary not available for this snap.'}
        </Text>

        {/* Action Bar */}
        <View style={[styles.actionBar, { borderColor: colors.borderLight, backgroundColor: colors.surface }]}>
          <TouchableOpacity
            style={styles.actionButton}
            onPress={handleToggleLike}
            activeOpacity={0.7}
          >
            <Text style={styles.actionIcon}>{isLiked ? '❤️' : '🤍'}</Text>
            <Text style={[styles.actionLabel, { color: isLiked ? colors.error : colors.textMuted }]}>
              {t('like')}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionButton}
            onPress={handleToggleBookmark}
            activeOpacity={0.7}
          >
            <Text style={styles.actionIcon}>{isBookmarked ? '🔖' : '📑'}</Text>
            <Text style={[styles.actionLabel, { color: isBookmarked ? colors.primary : colors.textMuted }]}>
              {t('bookmark')}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionButton}
            onPress={handleShare}
            activeOpacity={0.7}
          >
            <Text style={styles.actionIcon}>↗️</Text>
            <Text style={[styles.actionLabel, { color: colors.textMuted }]}>
              {t('share')}
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  contentContainer: {
    paddingBottom: 40,
  },
  badgeWrapper: {
    marginBottom: 12,
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    lineHeight: 30,
  },
  divider: {
    height: 1,
  },
  summary: {
    fontSize: 16,
    lineHeight: 26,
  },
  actionBar: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: 14,
    borderRadius: 16,
    borderWidth: 1,
  },
  actionButton: {
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  actionIcon: {
    fontSize: 24,
    marginBottom: 4,
  },
  actionLabel: {
    fontSize: 12,
    fontWeight: '500',
  },
});

export default ArticleDetailScreen;

