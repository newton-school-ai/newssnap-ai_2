/**
 * NewsSnap AI - Navigation Types & Route Parameters
 */

import { NavigatorScreenParams } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';

export type MainTabParamList = {
  Feed: undefined;
  Search: undefined;
  Bookmarks: undefined;
  Profile: undefined;
};

export type RootStackParamList = {
  MainTabs: NavigatorScreenParams<MainTabParamList> | undefined;
  ArticleDetail: { articleId: string; title: string; category?: string; summary?: string };
  LanguagePicker: undefined;
  Login: undefined;
  Onboarding: undefined;
};

export type RootNavigationProp = NativeStackNavigationProp<RootStackParamList>;
export type MainTabNavProp = BottomTabNavigationProp<MainTabParamList>;

