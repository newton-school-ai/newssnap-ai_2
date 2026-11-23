/**
 * NewsSnap AI - Multi-Language Context & Localization System
 * Supports 12 Indian languages and updates UI translations dynamically.
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

export interface LanguageOption {
  code: string;
  name: string;
  nativeName: string;
}

export const SUPPORTED_LANGUAGES: LanguageOption[] = [
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు' },
  { code: 'mr', name: 'Marathi', nativeName: 'मराठी' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்' },
  { code: 'ur', name: 'Urdu', nativeName: 'اردو' },
  { code: 'gu', name: 'Gujarati', nativeName: 'ગુજરાતી' },
  { code: 'kn', name: 'Kannada', nativeName: 'ಕನ್ನಡ' },
  { code: 'ml', name: 'Malayalam', nativeName: 'മലയാളം' },
  { code: 'or', name: 'Odia', nativeName: 'ଓଡ଼ିଆ' },
  { code: 'pa', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ' },
];

const TRANSLATIONS: Record<string, Record<string, string>> = {
  en: {
    feed: 'Feed',
    search: 'Search',
    bookmarks: 'Bookmarks',
    profile: 'Profile',
    trending: 'Trending',
    readMore: 'Read Full Story',
    share: 'Share',
    like: 'Like',
    bookmark: 'Bookmark',
    signInWithGoogle: 'Sign in with Google',
    devSignIn: 'Quick Demo Login',
    onboardingTitle: 'Personalize Your News',
    onboardingSubtitle: 'Select your preferred language and at least 3 categories',
    continue: 'Continue',
    categories: 'Categories',
    language: 'Language',
    changeLanguage: 'Change Language',
    logout: 'Log Out',
    myBookmarks: 'Saved Articles',
    noBookmarks: 'No bookmarked articles yet',
    searchPlaceholder: 'Search topics, sources, or keywords...',
    noResults: 'No news found matching your query',
  },
  hi: {
    feed: 'फ़ीड',
    search: 'खोजें',
    bookmarks: 'बुकमार्क',
    profile: 'प्रोफ़ाइल',
    trending: 'ट्रेंडिंग',
    readMore: 'पूरी खबर पढ़ें',
    share: 'शेयर करें',
    like: 'पसंद करें',
    bookmark: 'सेव करें',
    signInWithGoogle: 'Google से साइन इन करें',
    devSignIn: 'डेमो लॉगिन करें',
    onboardingTitle: 'अपनी पसंद चुनें',
    onboardingSubtitle: 'अपनी पसंदीदा भाषा और कम से कम 3 श्रेणियां चुनें',
    continue: 'आगे बढ़ें',
    categories: 'श्रेणियां',
    language: 'भाषा',
    changeLanguage: 'भाषा बदलें',
    logout: 'लॉग आउट',
    myBookmarks: 'सहेजे गए लेख',
    noBookmarks: 'अभी तक कोई बुकमार्क नहीं है',
    searchPlaceholder: 'विषय, स्रोत या कीवर्ड खोजें...',
    noResults: 'कोई समाचार नहीं मिला',
  },
  bn: {
    feed: 'ফিড',
    search: 'অনুসন্ধান',
    bookmarks: 'বুকমার্ক',
    profile: 'প্রোফাইল',
    trending: 'ট্রেন্ডিং',
    readMore: 'সম্পূর্ণ খবর পড়ুন',
    share: 'শেয়ার করুন',
    like: 'লাইক',
    bookmark: 'বুকমার্ক',
    signInWithGoogle: 'গুগল দিয়ে সাইন ইন করুন',
    devSignIn: 'ডেমো লগইন',
    onboardingTitle: 'পছন্দ নির্বাচন করুন',
    onboardingSubtitle: 'ভাষা এবং কমপক্ষে ৩টি বিভাগ নির্বাচন করুন',
    continue: 'এগিয়ে যান',
    categories: 'বিভাগসমূহ',
    language: 'ভাষা',
    changeLanguage: 'ভাষা পরিবর্তন করুন',
    logout: 'লগআউট',
    myBookmarks: 'সংরক্ষিত খবর',
    noBookmarks: 'কোনো সংরক্ষিত খবর নেই',
    searchPlaceholder: 'অনুসন্ধান করুন...',
    noResults: 'কোনো ফলাফল পাওয়া যায়নি',
  },
};

const LANGUAGE_STORAGE_KEY = 'newssnap_app_language';

export interface LanguageContextType {
  language: string;
  languageOption: LanguageOption;
  availableLanguages: LanguageOption[];
  setLanguage: (langCode: string) => Promise<void>;
  t: (key: string, defaultText?: string) => string;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

interface LanguageProviderProps {
  children: ReactNode;
}

export const LanguageProvider: React.FC<LanguageProviderProps> = ({ children }) => {
  const [language, setLanguageState] = useState<string>('en');

  useEffect(() => {
    const loadSavedLanguage = async () => {
      try {
        let savedLang: string | null = null;
        if (Platform.OS === 'web') {
          savedLang = typeof localStorage !== 'undefined' ? localStorage.getItem(LANGUAGE_STORAGE_KEY) : null;
        } else {
          savedLang = await SecureStore.getItemAsync(LANGUAGE_STORAGE_KEY);
        }
        if (savedLang && SUPPORTED_LANGUAGES.some((l) => l.code === savedLang)) {
          setLanguageState(savedLang);
        }
      } catch (e) {
        console.warn('Could not load saved language:', e);
      }
    };

    loadSavedLanguage();
  }, []);

  const setLanguage = async (langCode: string): Promise<void> => {
    const valid = SUPPORTED_LANGUAGES.some((l) => l.code === langCode);
    if (!valid) return;

    setLanguageState(langCode);
    try {
      if (Platform.OS === 'web') {
        if (typeof localStorage !== 'undefined') localStorage.setItem(LANGUAGE_STORAGE_KEY, langCode);
      } else {
        await SecureStore.setItemAsync(LANGUAGE_STORAGE_KEY, langCode);
      }
    } catch (e) {
      console.warn('Could not save language to storage:', e);
    }
  };

  const t = (key: string, defaultText?: string): string => {
    const langDict = TRANSLATIONS[language] || TRANSLATIONS['en'];
    if (langDict && langDict[key]) {
      return langDict[key];
    }
    // Fallback to English
    if (TRANSLATIONS['en'][key]) {
      return TRANSLATIONS['en'][key];
    }
    return defaultText || key;
  };

  const languageOption =
    SUPPORTED_LANGUAGES.find((l) => l.code === language) || SUPPORTED_LANGUAGES[0];

  return (
    <LanguageContext.Provider
      value={{
        language,
        languageOption,
        availableLanguages: SUPPORTED_LANGUAGES,
        setLanguage,
        t,
      }}
    >
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = (): LanguageContextType => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};

export default LanguageContext;

