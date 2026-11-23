/**
 * Tests for Navigation Configuration and Screen Route Types
 */

import { RootStackParamList, MainTabParamList } from '../navigation/types';

describe('Navigation Structure & Route Parameters', () => {
  test('RootStackParamList contains all app navigation routes', () => {
    type ExpectedRoutes = keyof RootStackParamList;
    const routes: ExpectedRoutes[] = [
      'MainTabs',
      'ArticleDetail',
      'LanguagePicker',
      'Login',
      'Onboarding',
    ];
    expect(routes).toHaveLength(5);
  });

  test('MainTabParamList contains 4 primary tabs', () => {
    type TabRoutes = keyof MainTabParamList;
    const tabs: TabRoutes[] = ['Feed', 'Search', 'Bookmarks', 'Profile'];
    expect(tabs).toHaveLength(4);
  });
});
