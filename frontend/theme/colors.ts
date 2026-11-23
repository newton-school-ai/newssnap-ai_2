/**
 * NewsSnap AI - Theme Color Palette
 * Light-mode primary palette with distinct badges for all 19 news categories.
 */

export const colors = {
  // Brand colors
  primary: '#1E40AF', // Deep Brand Blue
  primaryLight: '#3B82F6',
  primaryDark: '#1E3A8A',
  accent: '#F97316', // Energetic Orange

  // Neutrals / Surface
  background: '#FFFFFF',
  surface: '#F8FAFC',
  card: '#FFFFFF',
  cardAlt: '#F1F5F9',
  divider: '#E2E8F0',
  border: '#CBD5E1',

  // Typography
  textPrimary: '#0F172A', // Slate 900
  textSecondary: '#475569', // Slate 600
  textMuted: '#94A3B8', // Slate 400
  textInverse: '#FFFFFF',

  // Feedback & Status
  success: '#10B981',
  warning: '#F59E0B',
  error: '#EF4444',
  info: '#3B82F6',

  // 19 News Content Categories
  categories: {
    national: '#2563EB', // Blue
    international: '#4F46E5', // Indigo
    politics: '#DC2626', // Red
    business: '#059669', // Emerald
    finance: '#10B981', // Green
    sports: '#EA580C', // Orange
    technology: '#7C3AED', // Purple
    science: '#0891B2', // Cyan
    automobile: '#D97706', // Amber
    education: '#3B82F6', // Royal Blue
    health: '#0D9488', // Teal
    entertainment: '#DB2777', // Pink
    lifestyle: '#E11D48', // Rose
    crime: '#475569', // Slate
    environment: '#15803D', // Forest Green
    jobs: '#6366F1', // Violet
    defence: '#334155', // Dark Slate
    real_estate: '#B45309', // Warm Brown
    opinion: '#8B5CF6', // Light Violet
  } as Record<string, string>,
};

export const getCategoryColor = (categorySlug?: string): string => {
  if (!categorySlug) return colors.primary;
  const slug = categorySlug.toLowerCase().trim();
  return colors.categories[slug] || colors.primary;
};

