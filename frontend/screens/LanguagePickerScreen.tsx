/**
 * NewsSnap AI - Language Picker Screen
 * Modal screen allowing the user to switch their primary news language.
 */

import React from 'react';
import { View, StyleSheet, TouchableOpacity, Text } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { LanguagePicker } from '../components/LanguagePicker';
import { useTheme } from '../context/ThemeContext';
import { useLanguage } from '../context/LanguageContext';

export const LanguagePickerScreen: React.FC = () => {
  const { colors, spacing, typography } = useTheme();
  const { currentLanguage, setLanguage, t } = useLanguage();
  const navigation = useNavigation();

  const handleSelectLanguage = async (code: string) => {
    await setLanguage(code);
    navigation.goBack();
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.background, padding: spacing.lg }]}>
      <Text style={[styles.subtitle, { color: colors.textSecondary, marginBottom: spacing.md }]}>
        Select your preferred language. All feed content and headlines will update dynamically.
      </Text>

      <LanguagePicker
        selectedLanguage={currentLanguage}
        onSelectLanguage={handleSelectLanguage}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  subtitle: {
    fontSize: 14,
    lineHeight: 20,
  },
});

export default LanguagePickerScreen;

