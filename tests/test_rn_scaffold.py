"""
Unit tests for Issue 25: React Native app scaffold with Expo and navigation.
Validates:
1. Expo project configuration (app.json) for iOS & Android
2. TypeScript configuration (tsconfig.json)
3. Package dependencies (React Native, Expo, React Navigation, Axios)
4. Navigation structure (TabNavigator, StackNavigator, RootNavigator)
5. Auth flow & onboarding gating (LoginScreen, OnboardingScreen, AuthContext)
6. API client with JWT attachment & refresh logic (client.ts, auth.ts, feed.ts, users.ts)
7. Language and theme contexts (LanguageContext, ThemeContext, theme tokens)
"""

import json
import os

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


def test_app_json_expo_config():
    """Verify app.json contains valid Expo config with iOS bundleId and Android package."""
    app_json_path = os.path.join(FRONTEND_DIR, "app.json")
    assert os.path.exists(app_json_path), "app.json must exist in frontend/"

    with open(app_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    expo = data.get("expo", {})
    assert expo.get("name") == "NewsSnap AI"
    assert expo.get("slug") == "newssnap-ai"
    assert expo.get("scheme") == "newssnap"
    assert "ios" in expo
    assert expo["ios"].get("bundleIdentifier") == "com.newssnap.ai"
    assert "android" in expo
    assert expo["android"].get("package") == "com.newssnap.ai"


def test_package_json_dependencies():
    """Verify package.json specifies Expo, React Navigation, Axios, and scripts."""
    pkg_path = os.path.join(FRONTEND_DIR, "package.json")
    assert os.path.exists(pkg_path), "frontend/package.json must exist"

    with open(pkg_path, "r", encoding="utf-8") as f:
        pkg = json.load(f)

    deps = pkg.get("dependencies", {})
    assert "expo" in deps
    assert "react" in deps
    assert "react-native" in deps
    assert "@react-navigation/native" in deps
    assert "@react-navigation/native-stack" in deps
    assert "@react-navigation/bottom-tabs" in deps
    assert "axios" in deps

    scripts = pkg.get("scripts", {})
    assert "start" in scripts
    assert "android" in scripts
    assert "ios" in scripts
    assert "test" in scripts


def test_tsconfig_json():
    """Verify tsconfig.json has strict typing and react-native config."""
    tsconfig_path = os.path.join(FRONTEND_DIR, "tsconfig.json")
    assert os.path.exists(tsconfig_path), "frontend/tsconfig.json must exist"

    with open(tsconfig_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    opts = data.get("compilerOptions", {})
    assert opts.get("strict") is True


def test_navigation_files_exist():
    """Verify navigation components and route types exist."""
    nav_dir = os.path.join(FRONTEND_DIR, "navigation")
    assert os.path.exists(os.path.join(nav_dir, "types.ts"))
    assert os.path.exists(os.path.join(nav_dir, "TabNavigator.tsx"))
    assert os.path.exists(os.path.join(nav_dir, "StackNavigator.tsx"))
    assert os.path.exists(os.path.join(nav_dir, "RootNavigator.tsx"))

    with open(os.path.join(nav_dir, "TabNavigator.tsx"), "r", encoding="utf-8") as f:
        tab_code = f.read()
    assert "Feed" in tab_code
    assert "Search" in tab_code
    assert "Bookmarks" in tab_code
    assert "Profile" in tab_code


def test_auth_and_onboarding_screens_and_context():
    """Verify AuthContext handles Google OAuth, dev bypass, onboarding gating."""
    screens_dir = os.path.join(FRONTEND_DIR, "screens")
    assert os.path.exists(os.path.join(screens_dir, "LoginScreen.tsx"))
    assert os.path.exists(os.path.join(screens_dir, "OnboardingScreen.tsx"))
    assert os.path.exists(os.path.join(screens_dir, "FeedScreen.tsx"))
    assert os.path.exists(os.path.join(screens_dir, "SearchScreen.tsx"))
    assert os.path.exists(os.path.join(screens_dir, "BookmarksScreen.tsx"))
    assert os.path.exists(os.path.join(screens_dir, "ProfileScreen.tsx"))
    assert os.path.exists(os.path.join(screens_dir, "ArticleDetailScreen.tsx"))
    assert os.path.exists(os.path.join(screens_dir, "LanguagePickerScreen.tsx"))

    auth_ctx_path = os.path.join(FRONTEND_DIR, "context", "AuthContext.tsx")
    with open(auth_ctx_path, "r", encoding="utf-8") as f:
        auth_code = f.read()

    # Onboarding gating
    assert "is_onboarded" in auth_code
    assert "completeOnboarding" in auth_code
    assert "signInWithGoogle" in auth_code
    assert "devSignIn" in auth_code
    assert "signOut" in auth_code

    # Root Navigator gating
    with open(os.path.join(FRONTEND_DIR, "navigation", "RootNavigator.tsx"), "r", encoding="utf-8") as f:
        root_code = f.read()
    assert "isAuthenticated" in root_code
    assert "isOnboarded" in root_code
    assert "LoginScreen" in root_code
    assert "OnboardingScreen" in root_code


def test_api_client_and_jwt_handling():
    """Verify Axios client attaches JWT and handles refresh on 401."""
    client_path = os.path.join(FRONTEND_DIR, "api", "client.ts")
    assert os.path.exists(client_path)

    with open(client_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "Authorization" in code
    assert "Bearer" in code
    assert "/auth/refresh" in code
    assert "response.use" in code
    assert "401" in code
    assert "setStoredTokens" in code


def test_language_and_theme_context():
    """Verify LanguageContext supports 12 Indian languages and ThemeContext provides tokens."""
    lang_path = os.path.join(FRONTEND_DIR, "context", "LanguageContext.tsx")
    assert os.path.exists(lang_path)

    with open(lang_path, "r", encoding="utf-8") as f:
        code = f.read()

    for lang in ["en", "hi", "bn", "te", "mr", "ta", "ur", "gu", "kn", "ml", "pa", "or"]:
        assert f"code: '{lang}'" in code or f'code: "{lang}"' in code

    theme_path = os.path.join(FRONTEND_DIR, "theme", "colors.ts")
    assert os.path.exists(theme_path)

    with open(theme_path, "r", encoding="utf-8") as f:
        colors_code = f.read()
    assert "primary" in colors_code
    assert "background" in colors_code
    assert "categories" in colors_code
    assert "getCategoryColor" in colors_code
