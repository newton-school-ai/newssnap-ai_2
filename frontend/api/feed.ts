/**
 * NewsSnap AI - News Feed & Interaction API Endpoints
 */

import apiClient from './client';

export interface FeedItem {
  snap_id: string;
  article_id: string;
  title: string;
  summary: string;
  image_url?: string;
  category: string;
  source: string;
  time_ago: string;
  interaction_counts: {
    likes: number;
    comments: number;
    shares: number;
    bookmarks: number;
  };
}

export interface FeedResponse {
  items: FeedItem[];
  snaps: FeedItem[];
  next_cursor?: string;
  has_more: boolean;
}

export interface FeedQueryParams {
  language: string;
  categories?: string;
  time_range?: string;
  cursor?: string;
  limit?: number;
}

/**
 * Fetch personalized feed snaps.
 */
export const getFeed = async (params: FeedQueryParams): Promise<FeedResponse> => {
  const response = await apiClient.get<FeedResponse>('/api/feed', { params });
  return response.data;
};

/**
 * Search articles by query.
 */
export const searchSnaps = async (query: string, language: string = 'en') => {
  const response = await apiClient.get('/api/search', {
    params: { q: query, language },
  });
  return response.data;
};

/**
 * Toggle like interaction on an article.
 */
export const toggleLikeArticle = async (articleId: string) => {
  const response = await apiClient.post(`/api/articles/${articleId}/like`);
  return response.data;
};

/**
 * Toggle bookmark on an article.
 */
export const toggleBookmarkArticle = async (articleId: string) => {
  const response = await apiClient.post(`/api/articles/${articleId}/bookmark`);
  return response.data;
};

/**
 * Track share event.
 */
export const trackShareArticle = async (articleId: string) => {
  const response = await apiClient.post(`/api/articles/${articleId}/share`);
  return response.data;
};

/**
 * Track read event and dwell time.
 */
export const trackReadArticle = async (articleId: string, timeSpentSeconds: number) => {
  const response = await apiClient.post(`/api/articles/${articleId}/read`, {
    time_spent_seconds: timeSpentSeconds,
  });
  return response.data;
};

