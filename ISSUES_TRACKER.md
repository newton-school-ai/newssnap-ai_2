# Issues Tracker - NewsSnap AI

33 issues across 8 milestones. See GITHUB_ISSUES.md for full detailed descriptions.

## M1: Project Scaffold, DB, and Auth (4 issues)

| # | Title | Labels | Status |
|---|-------|--------|--------|
| 1 | Initialize repo scaffold, CI workflow, Docker setup | m1, infra | Todo |
| 2 | Design database schema, Alembic migrations, and seed data | m1, infra | Todo |
| 3 | Build news source configuration and registry system | m1, scraper | Todo |
| 4 | Build user auth API with Google OAuth and JWT | m1, infra | Todo |

## M2: News Scraping Pipeline (4 issues)

| # | Title | Labels | Status |
|---|-------|--------|--------|
| 5 | Build Playwright-based web scraper for JS-rendered news sites | m2, scraper | Todo |
| 6 | Build RSS and API scraper for feed-based news sources | m2, scraper | Todo |
| 7 | Build article parser and content normalizer | m2, scraper | Todo |
| 8 | Build scrape scheduler with monitoring and error handling | m2, scraper, infra | Todo |

## M3: AI Content Pipeline (4 issues)

| # | Title | Labels | Status |
|---|-------|--------|--------|
| 9 | Build embedding-based deduplication agent | m3, agent | Todo |
| 10 | Build story clustering agent for related articles | m3, agent | Todo |
| 11 | Build LLM summarizer agent for crisp 1-paragraph summaries | m3, agent | Todo |
| 12 | Build content quality filter to reject clickbait and spam | m3, agent | Todo |

## M4: Translation and Snap Generation (4 issues)

| # | Title | Labels | Status |
|---|-------|--------|--------|
| 13 | Build multi-language translator agent for 5 Indian languages | m4, agent | Todo |
| 14 | Build snap image generator with white background layout | m4, snaps | Todo |
| 15 | Build image extraction and processing pipeline | m4, snaps | Todo |
| 16 | Build snap template system for different content categories | m4, snaps | Todo |

## M5: Feed API, Search, and Interactions (4 issues)

| # | Title | Labels | Status |
|---|-------|--------|--------|
| 17 | Build personalized feed API with pagination and filtering | m5, infra | Todo |
| 18 | Build Meilisearch integration for multi-language search | m5, search | Todo |
| 19 | Build interaction system for like, comment, share, and bookmark | m5, infra | Todo |
| 20 | Build trending and category APIs with breaking news support | m5, recommendation | Done |

## M6: Recommendation Engine (4 issues)

| # | Title | Labels | Status |
|---|-------|--------|--------|
| 21 | Build content-based recommender using topic and category similarity | m6, recommendation | Todo |
| 22 | Build collaborative filtering with implicit feedback signals | m6, recommendation | Todo |
| 23 | Build hybrid recommendation scorer with diversity injection | m6, recommendation | Todo |
| 24 | Build recommendation refresh scheduler and A/B test framework | m6, recommendation, infra | Todo |

## M7: Mobile App (5 issues)

| # | Title | Labels | Status |
|---|-------|--------|--------|
| 25 | Build React Native app scaffold with Expo and navigation | m7, frontend | Todo |
| 26 | Build swipe feed screen with vertical swipe and infinite scroll | m7, frontend | Todo |
| 27 | Build search and explore screen with category chips and trending | m7, frontend | Todo |
| 28 | Build social features UI with like animation and comment sheet | m7, frontend | Todo |
| 29 | Build profile, settings, and onboarding screens | m7, frontend | Todo |

## M8: Production Readiness (4 issues)

| # | Title | Labels | Status |
|---|-------|--------|--------|
| 30 | Build push notification system for breaking news and digests | m8, infra | Todo |
| 31 | Build data cleanup scheduler with 2-week retention policy | m8, infra | Todo |
| 32 | Build admin monitoring dashboard for pipeline health | m8, frontend, infra | Todo |
| 33 | E2E testing, Redis caching, performance optimization, and deployment | m8, infra | Todo |
