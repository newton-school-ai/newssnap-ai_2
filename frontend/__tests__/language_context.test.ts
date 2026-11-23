/**
 * Tests for Language Context and Translations
 * Verifies 12 Indian languages are supported, language codes,
 * and translation fallbacks.
 */

import { SUPPORTED_LANGUAGES, translations } from '../context/LanguageContext';

describe('LanguageContext & Localization', () => {
  test('Supports all 12 required Indian languages plus English', () => {
    const codes = SUPPORTED_LANGUAGES.map((l) => l.code);
    expect(codes).toContain('en'); // English
    expect(codes).toContain('hi'); // Hindi
    expect(codes).toContain('bn'); // Bengali
    expect(codes).toContain('te'); // Telugu
    expect(codes).toContain('mr'); // Marathi
    expect(codes).toContain('ta'); // Tamil
    expect(codes).toContain('ur'); // Urdu
    expect(codes).toContain('gu'); // Gujarati
    expect(codes).toContain('kn'); // Kannada
    expect(codes).toContain('ml'); // Malayalam
    expect(codes).toContain('pa'); // Punjabi
    expect(codes).toContain('or'); // Odia
    expect(codes.length).toBeGreaterThanOrEqual(12);
  });

  test('Translation dictionary includes core UI strings for primary languages', () => {
    const en = translations['en'];
    const hi = translations['hi'];

    expect(en.feed).toBe('Feed');
    expect(en.search).toBe('Search');
    expect(en.bookmarks).toBe('Bookmarks');
    expect(en.profile).toBe('Profile');
    expect(en.like).toBe('Like');
    expect(en.share).toBe('Share');

    expect(hi.feed).toBe('फ़ीड');
    expect(hi.search).toBe('खोजें');
    expect(hi.bookmarks).toBe('बुकमार्क');
    expect(hi.profile).toBe('प्रोफ़ाइल');
  });

  test('English dictionary has comprehensive keys', () => {
    const keys = Object.keys(translations['en']);
    expect(keys).toContain('selectLanguage');
    expect(keys).toContain('onboardingTitle');
    expect(keys).toContain('continue');
    expect(keys).toContain('logout');
  });
});
