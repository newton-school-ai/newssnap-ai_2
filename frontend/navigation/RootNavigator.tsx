/**
 * NewsSnap AI - Root Navigation Gatekeeper
 * Selects between Login, Onboarding, and Main Application based on user auth state.
 */

import React from 'react';
import { ActivityIndicator, View, StyleSheet } from 'react-native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

import { useAuth } from '../context/AuthContext';
import StackNavigator from './StackNavigator';
import LoginScreen from '../screens/LoginScreen';
import OnboardingScreen from '../screens/OnboardingScreen';
import { colors } from '../theme';

const RootStack = createNativeStackNavigator();

export const RootNavigator: React.FC = () => {
  const { isAuthenticated, isOnboarded, isLoading } = useAuth();

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  return (
    <RootStack.Navigator screenOptions={{ headerShown: false }}>
      {!isAuthenticated ? (
        // Unauthenticated Flow
        <RootStack.Screen name="Login" component={LoginScreen} />
      ) : !isOnboarded ? (
        // First-Time Login: Onboarding Flow (Language + 3 Categories)
        <RootStack.Screen name="Onboarding" component={OnboardingScreen} />
      ) : (
        // Main App Experience
        <RootStack.Screen name="App" component={StackNavigator} />
      )}
    </RootStack.Navigator>
  );
};

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.background,
  },
});

export default RootNavigator;

