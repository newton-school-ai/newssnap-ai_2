/**
 * NewsSnap AI - API Client with JWT Interceptors & Automatic Token Refresh
 */

import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const STORAGE_KEYS = {
  ACCESS_TOKEN: 'newssnap_access_token',
  REFRESH_TOKEN: 'newssnap_refresh_token',
};

// Fallback in-memory storage for non-native / test environments
let memoryStorage: Record<string, string> = {};

export const tokenStorage = {
  async getItem(key: string): Promise<string | null> {
    try {
      if (Platform.OS === 'web') {
        return memoryStorage[key] || (typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null);
      }
      return await SecureStore.getItemAsync(key);
    } catch {
      return memoryStorage[key] || null;
    }
  },
  async setItem(key: string, value: string): Promise<void> {
    memoryStorage[key] = value;
    try {
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') localStorage.setItem(key, value);
      } else {
        await SecureStore.setItemAsync(key, value);
      }
    } catch {
      // Memory storage fallback already set
    }
  },
  async removeItem(key: string): Promise<void> {
    delete memoryStorage[key];
    try {
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') localStorage.removeItem(key);
      } else {
        await SecureStore.deleteItemAsync(key);
      }
    } catch {
      // Memory storage fallback cleared
    }
  },
  async clearTokens(): Promise<void> {
    await this.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
    await this.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
  },
};

export const getStoredTokens = async () => {
  const accessToken = await tokenStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
  const refreshToken = await tokenStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
  return { accessToken, refreshToken };
};

export const setStoredTokens = async (accessToken: string, refreshToken: string) => {
  await tokenStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, accessToken);
  await tokenStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
};

// Determine default backend API base URL
const DEFAULT_API_URL = Platform.select({
  android: 'http://10.0.2.2:8000', // Android emulator loopback
  ios: 'http://localhost:8000',     // iOS simulator
  default: 'http://localhost:8000',
});

export const apiClient: AxiosInstance = axios.create({
  baseURL: DEFAULT_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: any) => void;
}> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error);
    } else if (token) {
      promise.resolve(token);
    }
  });
  failedQueue = [];
};

// Request Interceptor: Attach JWT Bearer Token
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const accessToken = await tokenStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    if (accessToken && config.headers) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Automatic 401 Refresh Handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (!originalRequest || !error.response || error.response.status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    // Avoid infinite loop if refresh endpoint itself returns 401
    if (originalRequest.url?.includes('/auth/refresh')) {
      await tokenStorage.clearTokens();
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      })
        .then((token) => {
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          return apiClient(originalRequest);
        })
        .catch((err) => Promise.reject(err));
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      const refreshToken = await tokenStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
      if (!refreshToken) {
        throw new Error('No refresh token available');
      }

      // Call refresh endpoint directly using clean axios instance to avoid interceptor recursion
      const refreshResponse = await axios.post(
        `${apiClient.defaults.baseURL}/auth/refresh`,
        { refresh_token: refreshToken },
        { headers: { 'Content-Type': 'application/json' } }
      );

      const { access_token, refresh_token: new_refresh_token } = refreshResponse.data;
      await setStoredTokens(access_token, new_refresh_token || refreshToken);

      processQueue(null, access_token);

      if (originalRequest.headers) {
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
      }
      return apiClient(originalRequest);
    } catch (refreshErr) {
      processQueue(refreshErr, null);
      await tokenStorage.clearTokens();
      return Promise.reject(refreshErr);
    } finally {
      isRefreshing = false;
    }
  }
);

export default apiClient;

