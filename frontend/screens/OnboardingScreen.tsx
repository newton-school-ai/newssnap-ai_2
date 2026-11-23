/**
 * NewsSnap AI - Onboarding Screen
 * Displayed on first login only:
 * - Preferred news language selection
 * - Multi-category selection (minimum 3 required)
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  ScrollView,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useAuth } from '../context/AuthContext';
import { useLanguage, SUPPORTED_LANGUAGES } from '../context/LanguageContext';
import Button from '../components/Button';
import { colors, typography, spacing, borderRadius } from '../theme';

const AVAILABLE_CATEGORIES = [
  { slug: 'national', name: 'National' },
  { slug: 'international', name: 'International' },
  { slug: 'politics', name: 'Politics' },
  { slug: 'business', name: 'Business' },
  { slug: 'finance', name: 'Finance' },
  { slug: 'sports', name: 'Sports' },
  { slug: 'technology', name: 'Technology' },
  { slug: 'science', name: 'Science' },
  { slug: 'automobile', name: 'Automobile' },
  { slug: 'education', name: 'Education' },
  { slug: 'health', name: 'Health' },
  { slug: 'entertainment', name: 'Entertainment' },
  { slug: 'lifestyle', name: 'Lifestyle' },
  { slug: 'crime', name: 'Crime' },
  { slug: 'environment', name: 'Environment' },
  { slug: 'jobs', name: 'Jobs' },
  { slug: 'defence', name: 'Defence' },
  { slug: 'real_estate', name: 'Real Estate' },
  { slug: 'opinion', name: 'Opinion' },
];

export const OnboardingScreen: React.FC = () => {
  const { completeOnboarding, isLoading } = useAuth();
  const { language, setLanguage, t } = useLanguage();

  const [selectedLanguage, setSelectedLanguage] = useState<string>(language || 'en');
  const [selectedCategories, setSelectedCategories] = useState<string[]>([
    'technology',
    'national',
    'business',
  ]);
  const [submitting, setSubmitting] = useState(false);

  const toggleCategory = (slug: string) => {
    if (selectedCategories.includes(slug)) {
      setSelectedCategories(selectedCategories.filter((c) => c !== slug));
    } else {
      setSelectedCategories([...selectedCategories, slug]);
    }
  };

  const handleLanguageChange = (code: string) => {
    setSelectedLanguage(code);
    setLanguage(code);
  };

  const handleSubmit = async () => {
    if (selectedCategories.length < 3) {
      Alert.alert(
        'Select More Categories',
        'Please select at least 3 categories so we can personalize your news feed.'
      );
      return;
    }

    setSubmitting(true);
    try {
      await completeOnboarding({
        primary_language: selectedLanguage,
        categories: selectedCategories,
      });
    } catch (e) {
      Alert.alert('Onboarding Failed', 'Could not save preferences. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>{t('onboardingTitle', 'Personalize Your News')}</Text>
          <Text style={styles.subtitle}>
            {t('onboardingSubtitle', 'Select your preferred language and at least 3 topics to start.')}
          </Text>
        </View>

        {/* Language Selection Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>
            <Ionicons name="language" size={18} color={colors.primary} /> Choose News Language
          </Text>
          <View style={styles.langGrid}>
            {SUPPORTED_LANGUAGES.map((lang) => {
              const isSelected = selectedLanguage === lang.code;
              return (
                <TouchableOpacity
                  key={lang.code}
                  style={[styles.langChip, isSelected && styles.langChipSelected]}
                  onPress={() => handleLanguageChange(lang.code)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.langNative, isSelected && styles.langTextSelected]}>
                    {lang.nativeName}
                  </Text>
                  <Text style={[styles.langEnglish, isSelected && styles.langTextSelected]}>
                    {lang.name}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        {/* Category Selection Section */}
        <View style={styles.section}>
          <View style={styles.categoryTitleRow}>
            <Text style={styles.sectionTitle}>
              <Ionicons name="grid" size={18} color={colors.primary} /> Choose Topics
            </Text>
            <Text style={styles.categoryCounter}>
              {selectedCategories.length}/3 selected
            </Text>
          </View>

          <View style={styles.catGrid}>
            {AVAILABLE_CATEGORIES.map((cat) => {
              const isSelected = selectedCategories.includes(cat.slug);
              return (
                <TouchableOpacity
                  key={cat.slug}
                  style={[styles.catChip, isSelected && styles.catChipSelected]}
                  onPress={() => toggleCategory(cat.slug)}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name={isSelected ? 'checkmark-circle' : 'add-circle-outline'}
                    size={16}
                    color={isSelected ? colors.textInverse : colors.primary}
                    style={{ marginRight: 4 }}
                  />
                  <Text style={[styles.catText, isSelected && styles.catTextSelected]}>
                    {cat.name}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      </ScrollView>

      {/* Bottom Action Bar */}
      <View style={styles.bottomBar}>
        <Button
          title={t('continue', 'Start Reading')}
          onPress={handleSubmit}
          loading={submitting || isLoading}
          disabled={selectedCategories.length < 3}
          style={styles.continueBtn}
        />
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContent: {
    padding: spacing.xl,
    paddingBottom: 100,
  },
  header: {
    marginBottom: spacing.xl,
  },
  title: {
    fontSize: typography.fontSizes.xl,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
  },
  subtitle: {
    fontSize: typography.fontSizes.base,
    color: colors.textSecondary,
    marginTop: spacing.xs,
    lineHeight: 22,
  },
  section: {
    marginBottom: spacing.xl,
  },
  sectionTitle: {
    fontSize: typography.fontSizes.md,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
    marginBottom: spacing.md,
  },
  langGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  langChip: {
    width: '31%',
    backgroundColor: colors.surface,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    borderRadius: borderRadius.md,
    borderWidth: 1,
    borderColor: colors.divider,
    alignItems: 'center',
  },
  langChipSelected: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  langNative: {
    fontSize: typography.fontSizes.sm,
    fontWeight: typography.fontWeights.bold,
    color: colors.textPrimary,
  },
  langEnglish: {
    fontSize: typography.fontSizes.xs,
    color: colors.textSecondary,
  },
  langTextSelected: {
    color: colors.textInverse,
  },
  categoryTitleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  categoryCounter: {
    fontSize: typography.fontSizes.xs,
    fontWeight: typography.fontWeights.semiBold,
    color: colors.primary,
  },
  catGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  catChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: borderRadius.full,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  catChipSelected: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  catText: {
    fontSize: typography.fontSizes.sm,
    color: colors.textPrimary,
    fontWeight: typography.fontWeights.medium,
  },
  catTextSelected: {
    color: colors.textInverse,
    fontWeight: typography.fontWeights.bold,
  },
  bottomBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: colors.background,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
    padding: spacing.base,
  },
  continueBtn: {
    width: '100%',
  },
});

export default OnboardingScreen;

