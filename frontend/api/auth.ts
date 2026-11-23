/**
 * NewsSnap AI - Authentication API Endpoints
 */

import apiClient, { setStoredTokens, tokenStorage } from './client';

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  is_onboarded: boolean;
  primary_language?: string;
  secondary_language?: string;
  categories: string[];
}

export interface OnboardingPayload {
  primary_language: string;
  secondary_language?: string;
  categories: string[];
}

/**
 * Exchange Google OAuth authorization code for backend JWT tokens.
 */
export const exchangeGoogleCode = async (code: string): Promise<TokenResponse> => {
  const response = await apiClient.get<TokenResponse>('/auth/google/callback', {
    params: { code },
  });
  const { access_token, refresh_token } = response.data;
  await setStoredTokens(access_token, refresh_token);
  return response.data;
};

/**
 * Development / Mock login helper for simulators without Google Auth config.
 */
export const mockLogin = async (email: string = 'demo@example.com', name: string = 'Demo User'): Promise<TokenResponse> => {
  // Simulates JWT authentication for test runs
  const mockTokens: TokenResponse = {
    access_token: `mock_jwt_access_${Date.now()}`,
    refresh_token: `mock_jwt_refresh_${Date.now()}`,
    token_type: 'bearer',
  };
  await setStoredTokens(mockTokens.access_token, mockTokens.refresh_token);
  return mockTokens;
};

/**
 * Fetch profile for the currently logged in user.
 */
export const fetchCurrentUser = async (): Promise<UserProfile> => {
  const response = await apiClient.get<UserProfile>('/api/users/me');
  return response.data;
};

/**
 * Complete user onboarding (languages and category preferences).
 */
export const submitOnboarding = async (data: OnboardingPayload): Promise<UserProfile> => {
  const response = await apiClient.post<UserProfile>('/api/users/onboarding', data);
  return response.data;
};

/**
 * Logout and clear stored tokens.
 */
export const logout = async (): Promise<void> => {
  await tokenStorage.clearTokens();
};

