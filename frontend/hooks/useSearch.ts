/**
 * NewsSnap AI - useSearch Hook
 * Manages search state with 300ms debounce, recent searches local storage,
 * category filtering, trending grid articles, and multi-language support.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

import apiClient from '../api/client';
import { CompactSnapItem } from '../components/CompactSnapCard';
import { CategoryOption } from '../components/CategoryChips';
import { useLanguage } from '../context/LanguageContext';

const RECENT_SEARCHES_KEY = '@newssnap_recent_searches';
const MAX_RECENT_SEARCHES = 10;

// Memory storage fallback for node / testing environments
const memoryStorage: Record<string, string> = {};

const storageHelper = {
  async getItem(key: string): Promise<string | null> {
    try {
      if (Platform.OS === 'web' && typeof localStorage !== 'undefined') {
        return localStorage.getItem(key);
      }
      return await AsyncStorage.getItem(key);
    } catch {
      return memoryStorage[key] || null;
    }
  },
  async setItem(key: string, value: string): Promise<void> {
    memoryStorage[key] = value;
    try {
      if (Platform.OS === 'web' && typeof localStorage !== 'undefined') {
        localStorage.setItem(key, value);
      } else {
        await AsyncStorage.setItem(key, value);
      }
    } catch {
      // In-memory fallback
    }
  },
};

export const DEFAULT_CATEGORIES: CategoryOption[] = [
  { slug: 'national', name: 'National' },
  { slug: 'international', name: 'World' },
  { slug: 'technology', name: 'Tech' },
  { slug: 'business', name: 'Business' },
  { slug: 'finance', name: 'Finance' },
  { slug: 'sports', name: 'Sports' },
  { slug: 'entertainment', name: 'Entertainment' },
  { slug: 'science', name: 'Science' },
  { slug: 'health', name: 'Health' },
  { slug: 'politics', name: 'Politics' },
  { slug: 'lifestyle', name: 'Lifestyle' },
  { slug: 'automobile', name: 'Automobile' },
];

export interface UseSearchResult {
  query: string;
  setQuery: (q: string) => void;
  results: CompactSnapItem[];
  trendingItems: CompactSnapItem[];
  categories: CategoryOption[];
  selectedCategory: string | null;
  setSelectedCategory: (cat: string | null) => void;
  recentSearches: string[];
  addRecentSearch: (search: string) => Promise<void>;
  removeRecentSearch: (search: string) => Promise<void>;
  clearRecentSearches: () => Promise<void>;
  isSearching: boolean;
  isLoadingTrending: boolean;
  error: string | null;
  refreshTrending: () => Promise<void>;
}

export const useSearch = (): UseSearchResult => {
  const { language } = useLanguage();

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CompactSnapItem[]>([]);
  const [trendingItems, setTrendingItems] = useState<CompactSnapItem[]>([]);
  const [categories, setCategories] = useState<CategoryOption[]>(DEFAULT_CATEGORIES);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingTrending, setIsLoadingTrending] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const debounceTimer = useRef<NodeJS.Timeout | null>(null);

  /**
   * 1. Load recent searches from local storage on mount.
   */
  useEffect(() => {
    const loadRecentSearches = async () => {
      try {
        const stored = await storageHelper.getItem(RECENT_SEARCHES_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (Array.isArray(parsed)) {
            setRecentSearches(parsed);
          }
        }
      } catch (err) {
        console.warn('Failed to load recent searches:', err);
      }
    };
    loadRecentSearches();
  }, []);

  /**
   * Save recent searches to local storage.
   */
  const saveRecentSearches = async (searches: string[]) => {
    setRecentSearches(searches);
    try {
      await storageHelper.setItem(RECENT_SEARCHES_KEY, JSON.stringify(searches));
    } catch (err) {
      console.warn('Failed to save recent searches:', err);
    }
  };

  const addRecentSearch = useCallback(
    async (newQuery: string) => {
      const clean = newQuery.trim();
      if (!clean) return;

      const filtered = recentSearches.filter((s) => s.toLowerCase() !== clean.toLowerCase());
      const updated = [clean, ...filtered].slice(0, MAX_RECENT_SEARCHES);
      await saveRecentSearches(updated);
    },
    [recentSearches]
  );

  const removeRecentSearch = useCallback(
    async (queryToRemove: string) => {
      const updated = recentSearches.filter((s) => s !== queryToRemove);
      await saveRecentSearches(updated);
    },
    [recentSearches]
  );

  const clearRecentSearches = useCallback(async () => {
    await saveRecentSearches([]);
  }, []);

  /**
   * 2. Fetch categories and trending articles.
   */
  const fetchTrendingAndCategories = useCallback(async () => {
    setIsLoadingTrending(true);
    try {
      // Fetch dynamic categories
      try {
        const catRes = await apiClient.get('/api/categories', {
          params: { language: language || 'en' },
        });
        if (catRes.data && Array.isArray(catRes.data.categories)) {
          setCategories(
            catRes.data.categories.map((c: any) => ({ slug: c.slug, name: c.name }))
          );
        }
      } catch {
        // Fallback to default categories
      }

      // Fetch trending articles
      if (selectedCategory) {
        const topRes = await apiClient.get(`/api/categories/${selectedCategory}/top`, {
          params: { language: language || 'en', limit: 20 },
        });
        const items = topRes.data?.articles || topRes.data?.items || [];
        setTrendingItems(items);
      } else {
        const searchRes = await apiClient.get('/api/search', {
          params: { q: '', language: language || 'en', limit: 20 },
        });
        const items = searchRes.data?.results || [];
        if (items.length > 0) {
          setTrendingItems(items);
        } else {
          // Fallback mock trending
          setTrendingItems([
            {
              article_id: 'trend-1',
              title: 'Global Tech Leaders Convene in Bengaluru for AI Innovation Summit',
              category: 'technology',
              source: 'Tech Wire',
              time_ago: '1h ago',
              image_url: 'https://picsum.photos/400/250?random=1',
            },
            {
              article_id: 'trend-2',
              title: 'India Wins Series Opener with Record-Breaking Fourth Wicket Stand',
              category: 'sports',
              source: 'CricSnap',
              time_ago: '2h ago',
              image_url: 'https://picsum.photos/400/250?random=2',
            },
            {
              article_id: 'trend-3',
              title: 'RBI Keeps Repo Rate Steady Amid Sustained Economic Growth',
              category: 'finance',
              source: 'Financial Express',
              time_ago: '3h ago',
              image_url: 'https://picsum.photos/400/250?random=3',
            },
            {
              article_id: 'trend-4',
              title: 'New Eco-Corridor in Western Ghats Discovers Rare Orchid Flora',
              category: 'science',
              source: 'Green Planet',
              time_ago: '5h ago',
              image_url: 'https://picsum.photos/400/250?random=4',
            },
          ]);
        }
      }
    } catch {
      // Fallback trending items
      setTrendingItems([
        {
          article_id: 'trend-1',
          title: 'Global Tech Leaders Convene in Bengaluru for AI Innovation Summit',
          category: 'technology',
          source: 'Tech Wire',
          time_ago: '1h ago',
        },
        {
          article_id: 'trend-2',
          title: 'India Wins Series Opener with Record-Breaking Fourth Wicket Stand',
          category: 'sports',
          source: 'CricSnap',
          time_ago: '2h ago',
        },
      ]);
    } finally {
      setIsLoadingTrending(false);
    }
  }, [language, selectedCategory]);

  useEffect(() => {
    fetchTrendingAndCategories();
  }, [fetchTrendingAndCategories]);

  /**
   * 3. Real-time Search with 300ms Debounce.
   */
  const executeSearch = useCallback(
    async (searchQuery: string, catFilter: string | null) => {
      setIsSearching(true);
      setError(null);
      try {
        const response = await apiClient.get('/api/search', {
          params: {
            q: searchQuery,
            language: language || 'en',
            category: catFilter || undefined,
            limit: 20,
          },
        });
        const hits = response.data?.results || [];
        setResults(hits);
      } catch (err: any) {
        setError(err.message || 'Search failed');
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    },
    [language]
  );

  useEffect(() => {
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
    }

    const cleanQuery = query.trim();
    if (!cleanQuery) {
      setResults([]);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    // 300ms debounce
    debounceTimer.current = setTimeout(() => {
      executeSearch(cleanQuery, selectedCategory);
      addRecentSearch(cleanQuery);
    }, 300);

    return () => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, [query, selectedCategory, executeSearch, addRecentSearch]);

  return {
    query,
    setQuery,
    results,
    trendingItems,
    categories,
    selectedCategory,
    setSelectedCategory,
    recentSearches,
    addRecentSearch,
    removeRecentSearch,
    clearRecentSearches,
    isSearching,
    isLoadingTrending,
    error,
    refreshTrending: fetchTrendingAndCategories,
  };
};

export default useSearch;
