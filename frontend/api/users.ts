/**
 * NewsSnap AI - User Profile, Bookmarks & Categories API
 */

import apiClient from './client';
import { FeedItem } from './feed';

export interface CategoryItem {
  id: number;
  slug: string;
  name: string;
  is_active: boolean;
}

/**
 * Retrieve user's bookmarked snaps/articles.
 */
export const getUserBookmarks = async (): Promise<FeedItem[]> => {
  const response = await apiClient.get<FeedItem[]>('/api/articles/bookmarks');
  return response.data;
};

/**
 * Retrieve list of all available categories.
 */
export const getCategories = async (): Promise<CategoryItem[]> => {
  const response = await apiClient.get<CategoryItem[]>('/api/categories');
  return response.data;
};

