/**
 * NewsSnap AI - Native Stack Navigator
 * Manages push/pop transitions for Tab Navigator, Detail screens, and Modals.
 */

import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { RootStackParamList } from './types';
import TabNavigator from './TabNavigator';
import ArticleDetailScreen from '../screens/ArticleDetailScreen';
import LanguagePickerScreen from '../screens/LanguagePickerScreen';
import { colors, typography } from '../theme';

const Stack = createNativeStackNavigator<RootStackParamList>();

export const StackNavigator: React.FC = () => {
  return (
    <Stack.Navigator
      initialRouteName="MainTabs"
      screenOptions={{
        headerStyle: {
          backgroundColor: colors.background,
        },
        headerTitleStyle: {
          fontSize: typography.fontSizes.md,
          fontWeight: typography.fontWeights.semiBold,
          color: colors.textPrimary,
        },
        headerTintColor: colors.primary,
        contentStyle: {
          backgroundColor: colors.background,
        },
      }}
    >
      <Stack.Screen
        name="MainTabs"
        component={TabNavigator}
        options={{ headerShown: false }}
      />
      <Stack.Screen
        name="ArticleDetail"
        component={ArticleDetailScreen}
        options={({ route }) => ({
          title: route.params.title || 'Article Detail',
          headerBackTitle: 'Back',
        })}
      />
      <Stack.Screen
        name="LanguagePicker"
        component={LanguagePickerScreen}
        options={{
          title: 'Choose Language',
          presentation: 'modal',
        }}
      />
    </Stack.Navigator>
  );
};

export default StackNavigator;

