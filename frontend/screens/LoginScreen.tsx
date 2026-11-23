/**
 * NewsSnap AI - Login Screen
 * Google OAuth sign-in flow and instant developer login bypass.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  StatusBar,
  Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useAuth } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import Button from '../components/Button';
import { colors, typography, spacing, borderRadius } from '../theme';

export const LoginScreen: React.FC = () => {
  const { signInWithGoogle, devSignIn, isLoading } = useAuth();
  const { t } = useLanguage();
  const [googleLoading, setGoogleLoading] = useState(false);
  const [devLoading, setDevLoading] = useState(false);

  const handleGoogleSignIn = async () => {
    setGoogleLoading(true);
    try {
      await signInWithGoogle();
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleDevSignIn = async () => {
    setDevLoading(true);
    try {
      await devSignIn('demo.reader@newssnap.ai', 'Yash Raghubanshi');
    } finally {
      setDevLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
      <View style={styles.content}>
        {/* Branding & Logo */}
        <View style={styles.brandContainer}>
          <View style={styles.logoBadge}>
            <Ionicons name="flash" size={42} color={colors.primary} />
          </View>
          <Text style={styles.appName}>NewsSnap AI</Text>
          <Text style={styles.tagline}>
            60-second bite-sized news snaps in 12 Indian languages powered by AI
          </Text>
        </View>

        {/* Feature Highlights */}
        <View style={styles.featureList}>
          <View style={styles.featureItem}>
            <Ionicons name="sparkles-outline" size={20} color={colors.primary} />
            <Text style={styles.featureText}>Personalized hybrid recommendations</Text>
          </View>
          <View style={styles.featureItem}>
            <Ionicons name="language-outline" size={20} color={colors.accent} />
            <Text style={styles.featureText}>Instant translation in your native language</Text>
          </View>
          <View style={styles.featureItem}>
            <Ionicons name="swap-vertical-outline" size={20} color={colors.success} />
            <Text style={styles.featureText}>Native swipe feed for effortless reading</Text>
          </View>
        </View>

        {/* Action Buttons */}
        <View style={styles.actionsContainer}>
          <Button
            title={t('signInWithGoogle', 'Sign in with Google')}
            variant="google"
            onPress={handleGoogleSignIn}
            loading={googleLoading}
            disabled={isLoading}
            icon={<Ionicons name="logo-google" size={20} color="#EA4335" style={{ marginRight: spacing.sm }} />}
            style={styles.googleBtn}
          />

          <View style={styles.dividerRow}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or for testing</Text>
            <View style={styles.dividerLine} />
          </View>

          <Button
            title={t('devSignIn', 'Quick Demo Sign In')}
            variant="outline"
            onPress={handleDevSignIn}
            loading={devLoading}
            disabled={isLoading}
          />
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    flex: 1,
    paddingHorizontal: spacing.xl,
    justifyContent: 'space-between',
    paddingVertical: spacing.xxl,
  },
  brandContainer: {
    alignItems: 'center',
    marginTop: spacing.xl,
  },
  logoBadge: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: `${colors.primary}12`,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.base,
  },
  appName: {
    fontSize: typography.fontSizes.xxl,
    fontWeight: typography.fontWeights.extraBold,
    color: colors.primary,
    letterSpacing: -0.5,
  },
  tagline: {
    fontSize: typography.fontSizes.base,
    color: colors.textSecondary,
    textAlign: 'center',
    marginTop: spacing.sm,
    lineHeight: 22,
    paddingHorizontal: spacing.md,
  },
  featureList: {
    backgroundColor: colors.surface,
    padding: spacing.base,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  featureText: {
    fontSize: typography.fontSizes.sm,
    color: colors.textPrimary,
    fontWeight: typography.fontWeights.medium,
    marginLeft: spacing.sm,
  },
  actionsContainer: {
    marginBottom: spacing.base,
  },
  googleBtn: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 2,
  },
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: spacing.base,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: colors.divider,
  },
  dividerText: {
    fontSize: typography.fontSizes.xs,
    color: colors.textMuted,
    marginHorizontal: spacing.sm,
    textTransform: 'uppercase',
  },
});

export default LoginScreen;

