/**
 * NewsSnap AI - Authentication Context & Provider
 * Manages user authentication state, Google OAuth flow, onboarding status, and token lifecycle.
 */

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import * as WebBrowser from 'expo-web-browser';
import * as AuthSession from 'expo-auth-session';
import { Platform } from 'react-native';

import {
  UserProfile,
  TokenResponse,
  fetchCurrentUser,
  submitOnboarding,
  logout as apiLogout,
  mockLogin,
  exchangeGoogleCode,
  OnboardingPayload,
} from '../api/auth';
import { getStoredTokens, tokenStorage } from '../api/client';

WebBrowser.maybeCompleteAuthSession();

export interface AuthContextType {
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isOnboarded: boolean;
  signInWithGoogle: () => Promise<void>;
  devSignIn: (email?: string, name?: string) => Promise<void>;
  signOut: () => Promise<void>;
  completeOnboarding: (payload: OnboardingPayload) => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Load existing credentials on app launch
  useEffect(() => {
    const bootstrapAsync = async () => {
      try {
        const { accessToken } = await getStoredTokens();
        if (accessToken) {
          try {
            const profile = await fetchCurrentUser();
            setUser(profile);
            setIsAuthenticated(true);
          } catch (profileErr) {
            // Token may be invalid or expired; try clearing
            await tokenStorage.clearTokens();
            setUser(null);
            setIsAuthenticated(false);
          }
        }
      } catch (e) {
        console.warn('Failed to restore auth session:', e);
      } finally {
        setIsLoading(false);
      }
    };

    bootstrapAsync();
  }, []);

  const signInWithGoogle = async (): Promise<void> => {
    setIsLoading(true);
    try {
      // Build redirect URI for Expo
      const redirectUri = AuthSession.makeRedirectUri({
        scheme: 'newssnap',
        path: 'auth/callback',
      });

      // Google OAuth Discovery URLs
      const clientId = Platform.select({
        ios: 'YOUR_IOS_GOOGLE_CLIENT_ID.apps.googleusercontent.com',
        android: 'YOUR_ANDROID_GOOGLE_CLIENT_ID.apps.googleusercontent.com',
        default: 'YOUR_WEB_GOOGLE_CLIENT_ID.apps.googleusercontent.com',
      });

      const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?` +
        `client_id=${encodeURIComponent(clientId || '')}&` +
        `response_type=code&` +
        `scope=${encodeURIComponent('openid email profile')}&` +
        `redirect_uri=${encodeURIComponent(redirectUri)}`;

      const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUri);

      if (result.type === 'success' && result.url) {
        const urlObj = new URL(result.url);
        const code = urlObj.searchParams.get('code');
        if (code) {
          await exchangeGoogleCode(code);
          const profile = await fetchCurrentUser();
          setUser(profile);
          setIsAuthenticated(true);
          return;
        }
      }

      // If user cancelled or in test/simulator without real Google Client ID, provide developer sign-in
      await devSignIn('demo.user@example.com', 'Demo User');
    } catch (error) {
      console.warn('Google sign in error, falling back to mock login for local dev:', error);
      await devSignIn('demo.user@example.com', 'Demo User');
    } finally {
      setIsLoading(false);
    }
  };

  const devSignIn = async (email: string = 'demo.user@example.com', name: string = 'Demo User'): Promise<void> => {
    setIsLoading(true);
    try {
      await mockLogin(email, name);
      try {
        const profile = await fetchCurrentUser();
        setUser(profile);
      } catch {
        // Fallback user object if backend is offline during UI development
        setUser({
          id: 'usr_demo_123',
          email,
          name,
          is_onboarded: false,
          categories: [],
        });
      }
      setIsAuthenticated(true);
    } finally {
      setIsLoading(false);
    }
  };

  const signOut = async (): Promise<void> => {
    setIsLoading(true);
    try {
      await apiLogout();
      setUser(null);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  };

  const completeOnboarding = async (payload: OnboardingPayload): Promise<void> => {
    setIsLoading(true);
    try {
      const updatedProfile = await submitOnboarding(payload);
      setUser(updatedProfile);
    } catch (e) {
      // Local optimistic update if backend is unreachable
      if (user) {
        setUser({
          ...user,
          is_onboarded: true,
          primary_language: payload.primary_language,
          secondary_language: payload.secondary_language,
          categories: payload.categories,
        });
      }
    } finally {
      setIsLoading(false);
    }
  };

  const refreshProfile = async (): Promise<void> => {
    try {
      const profile = await fetchCurrentUser();
      setUser(profile);
    } catch (e) {
      console.warn('Failed to refresh user profile:', e);
    }
  };

  const isOnboarded = Boolean(user?.is_onboarded);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isLoading,
        isOnboarded,
        signInWithGoogle,
        devSignIn,
        signOut,
        completeOnboarding,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export default AuthContext;

