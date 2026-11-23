/**
 * NewsSnap AI - User Profile & Settings Screen
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { RootNavigationProp } from '../navigation/types';
import Button from '../components/Button';
import { colors, typography, spacing, borderRadius } from '../theme';

export const ProfileScreen: React.FC = () => {
  const navigation = useNavigation<RootNavigationProp>();
  const { user, signOut } = useAuth();
  const { languageOption, t } = useLanguage();

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Profile Card */}
      <View style={styles.profileCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {user?.name ? user.name.charAt(0).toUpperCase() : 'U'}
          </Text>
        </View>
        <Text style={styles.name}>{user?.name || 'NewsSnap Reader'}</Text>
        <Text style={styles.email}>{user?.email || 'user@example.com'}</Text>
      </View>

      {/* Preferences Section */}
      <View style={styles.section}>
        <Text style={styles.sectionHeader}>Preferences</Text>

        {/* Language Selection Tile */}
        <TouchableOpacity
          style={styles.menuItem}
          onPress={() => navigation.navigate('LanguagePicker')}
          activeOpacity={0.7}
        >
          <View style={styles.menuLeft}>
            <Ionicons name="language" size={20} color={colors.primary} />
            <Text style={styles.menuText}>{t('changeLanguage', 'Change Language')}</Text>
          </View>
          <View style={styles.menuRight}>
            <Text style={styles.currentLang}>{languageOption.nativeName}</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
          </View>
        </TouchableOpacity>

        {/* Selected Categories */}
        <View style={styles.categoryItem}>
          <View style={styles.categoryHeader}>
            <Ionicons name="grid" size={20} color={colors.accent} />
            <Text style={styles.menuText}>Subscribed Topics</Text>
          </View>
          <View style={styles.pillsRow}>
            {(user?.categories || ['technology', 'national', 'business']).map((cat) => (
              <View key={cat} style={styles.categoryPill}>
                <Text style={styles.categoryPillText}>{cat}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      {/* App Info & Logout */}
      <View style={styles.section}>
        <Text style={styles.sectionHeader}>About</Text>
        <View style={styles.menuItem}>
          <Text style={styles.menuText}>App Version</Text>
          <Text style={styles.menuDetail}>1.0.0 (Expo SDK 51)</Text>
        </View>
      </View>

      <Button
        title={t('logout', 'Log Out')}
        variant="outline"
        onPress={signOut}
        style={styles.logoutBtn}
      />
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  content: {
    padding: spacing.base,
    paddingBottom: spacing.xxl,
  },
  profileCard: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    marginBottom: spacing.base,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  avatarText: {
    color: colors.textInverse,
    fontSize: typography.fontSizes.xl,
    fontWeight: typography.fontWeights.bold,
  },
  name: {
    fontSize: typography.fontSizes.lg,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
  },
  email: {
    fontSize: typography.fontSizes.sm,
    color: colors.textSecondary,
    marginTop: 2,
  },
  section: {
    backgroundColor: colors.card,
    borderRadius: borderRadius.md,
    marginBottom: spacing.base,
    borderWidth: 1,
    borderColor: colors.divider,
    overflow: 'hidden',
  },
  sectionHeader: {
    fontSize: typography.fontSizes.xs,
    fontWeight: typography.fontWeights.bold,
    color: colors.textMuted,
    textTransform: 'uppercase',
    padding: spacing.base,
    paddingBottom: spacing.xs,
    backgroundColor: colors.surface,
  },
  menuItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.base,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  menuLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  menuRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  menuText: {
    fontSize: typography.fontSizes.base,
    color: colors.textPrimary,
  },
  currentLang: {
    fontSize: typography.fontSizes.sm,
    color: colors.primary,
    fontWeight: typography.fontWeights.semiBold,
  },
  menuDetail: {
    fontSize: typography.fontSizes.sm,
    color: colors.textMuted,
  },
  categoryItem: {
    padding: spacing.base,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  categoryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  pillsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  categoryPill: {
    backgroundColor: `${colors.primary}12`,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    borderRadius: borderRadius.sm,
  },
  categoryPillText: {
    fontSize: typography.fontSizes.xs,
    color: colors.primary,
    fontWeight: typography.fontWeights.medium,
  },
  logoutBtn: {
    borderColor: colors.error,
    marginTop: spacing.sm,
  },
});

export default ProfileScreen;

