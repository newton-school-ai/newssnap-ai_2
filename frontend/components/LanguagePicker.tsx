/**
 * NewsSnap AI - Language Picker Component
 * Displays language options with native names and handles instant selection.
 */

import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, FlatList } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useLanguage, LanguageOption } from '../context/LanguageContext';
import { colors, typography, spacing, borderRadius } from '../theme';

interface LanguagePickerProps {
  onLanguageSelected?: (code: string) => void;
}

export const LanguagePicker: React.FC<LanguagePickerProps> = ({ onLanguageSelected }) => {
  const { language, availableLanguages, setLanguage } = useLanguage();

  const handleSelect = async (code: string) => {
    await setLanguage(code);
    if (onLanguageSelected) {
      onLanguageSelected(code);
    }
  };

  const renderItem = ({ item }: { item: LanguageOption }) => {
    const isSelected = item.code === language;

    return (
      <TouchableOpacity
        style={[styles.itemCard, isSelected && styles.itemCardSelected]}
        onPress={() => handleSelect(item.code)}
        activeOpacity={0.7}
      >
        <View style={styles.textContainer}>
          <Text style={[styles.nativeName, isSelected && styles.textSelected]}>
            {item.nativeName}
          </Text>
          <Text style={[styles.englishName, isSelected && styles.textSelectedMuted]}>
            {item.name}
          </Text>
        </View>

        {isSelected && (
          <Ionicons name="checkmark-circle" size={24} color={colors.primary} />
        )}
      </TouchableOpacity>
    );
  };

  return (
    <FlatList
      data={availableLanguages}
      keyExtractor={(item) => item.code}
      renderItem={renderItem}
      contentContainerStyle={styles.listContainer}
      showsVerticalScrollIndicator={false}
    />
  );
};

const styles = StyleSheet.create({
  listContainer: {
    padding: spacing.base,
  },
  itemCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surface,
    padding: spacing.base,
    borderRadius: borderRadius.md,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  itemCardSelected: {
    backgroundColor: `${colors.primary}10`,
    borderColor: colors.primary,
  },
  textContainer: {
    flex: 1,
  },
  nativeName: {
    fontSize: typography.fontSizes.md,
    fontWeight: typography.fontWeights.semiBold,
    color: colors.textPrimary,
  },
  englishName: {
    fontSize: typography.fontSizes.sm,
    color: colors.textSecondary,
    marginTop: 2,
  },
  textSelected: {
    color: colors.primaryDark,
    fontWeight: typography.fontWeights.bold,
  },
  textSelectedMuted: {
    color: colors.primary,
  },
});

export default LanguagePicker;

