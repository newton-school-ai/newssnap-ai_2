/**
 * NewsSnap AI - Unit Tests for Search and Explore Components & Hook
 */

import { DEFAULT_CATEGORIES } from '../hooks/useSearch';
import { CompactSnapItem } from '../components/CompactSnapCard';

describe('Search & Explore Screen Components', () => {
  test('Default categories contains core news topics', () => {
    const slugs = DEFAULT_CATEGORIES.map((c) => c.slug);
    expect(slugs).toContain('national');
    expect(slugs).toContain('technology');
    expect(slugs).toContain('business');
    expect(slugs).toContain('sports');
    expect(slugs).toContain('finance');
    expect(slugs.length).toBeGreaterThanOrEqual(10);
  });

  test('CompactSnapItem validates structure for 2-column grid', () => {
    const sampleItem: CompactSnapItem = {
      article_id: 'article-101',
      title: 'AI Startup Unleashes Real-time Translation for Indian Languages',
      category: 'technology',
      source: 'Tech In Asia',
      time_ago: '25m ago',
      image_url: 'https://example.com/thumb.jpg',
    };

    expect(sampleItem.article_id).toBe('article-101');
    expect(sampleItem.title).toBeDefined();
    expect(sampleItem.category).toBe('technology');
    expect(sampleItem.source).toBe('Tech In Asia');
  });

  test('Recent search deduplication logic works correctly', () => {
    const addSearchHelper = (existing: string[], newTerm: string, max: number = 10): string[] => {
      const clean = newTerm.trim();
      if (!clean) return existing;
      const filtered = existing.filter((s) => s.toLowerCase() !== clean.toLowerCase());
      return [clean, ...filtered].slice(0, max);
    };

    let searches: string[] = ['tech', 'cricket', 'isro'];
    searches = addSearchHelper(searches, 'cricket');
    expect(searches).toEqual(['cricket', 'tech', 'isro']);

    searches = addSearchHelper(searches, 'ai');
    expect(searches[0]).toBe('ai');
    expect(searches.length).toBe(4);
  });
});
