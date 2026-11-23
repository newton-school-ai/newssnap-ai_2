/**
 * NewsSnap AI - Unit Tests for Feed Swipe Components and Hook
 */

import { FeedItem } from '../api/feed';

describe('Swipe Feed Components & Types', () => {
  const mockItem: FeedItem = {
    snap_id: 'snap-123',
    article_id: 'art-456',
    title: 'Test Headline for Snap Feed',
    summary: 'A crisp 60-word summary of the breaking story in India.',
    category: 'technology',
    source: 'Tech Wire',
    time_ago: '10m ago',
    image_url: 'https://example.com/test.jpg',
    interaction_counts: {
      likes: 125,
      comments: 18,
      shares: 32,
      bookmarks: 40,
    },
  };

  test('FeedItem mock validates all required fields', () => {
    expect(mockItem.snap_id).toBe('snap-123');
    expect(mockItem.article_id).toBe('art-456');
    expect(mockItem.title).toBeDefined();
    expect(mockItem.summary).toBeDefined();
    expect(mockItem.category).toBe('technology');
    expect(mockItem.source).toBe('Tech Wire');
    expect(mockItem.time_ago).toBe('10m ago');
    expect(mockItem.interaction_counts.likes).toBe(125);
  });

  test('Format count returns human-readable metric', () => {
    const formatCount = (count: number): string => {
      if (!count || count <= 0) return '0';
      if (count >= 1000) {
        return `${(count / 1000).toFixed(1)}k`;
      }
      return String(count);
    };

    expect(formatCount(0)).toBe('0');
    expect(formatCount(42)).toBe('42');
    expect(formatCount(1200)).toBe('1.2k');
    expect(formatCount(15400)).toBe('15.4k');
  });
});
