"""Seed database with initial data (sources, categories, test user)."""

import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings, Language, ScrapeType, UserRole, Category as CategoryEnum
from src.models.base import Base
from src.models.user import User, UserPreference
from src.models.category import Category
from src.models.source import Source


def seed_database():
    """Seed categories, sources, and a test user with preferences."""
    print("Connecting to database...")
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # 1. Seed Categories (19 total)
        print("Seeding categories...")
        existing_categories = {c.slug for c in session.query(Category).all()}
        categories_to_seed = []
        for cat in CategoryEnum:
            if cat.value not in existing_categories:
                # Capitalize slug words for display name (e.g. real_estate -> Real Estate)
                display_name = " ".join(word.capitalize() for word in cat.value.split("_"))
                categories_to_seed.append(Category(slug=cat.value, name=display_name, is_active=True))

        if categories_to_seed:
            session.add_all(categories_to_seed)
            session.commit()
            print(f"Added {len(categories_to_seed)} new categories.")
        else:
            print("Categories already seeded.")

        # 2. Seed Sources (20+ across 5 languages)
        print("Seeding sources...")
        existing_sources = {s.slug for s in session.query(Source).all()}

        # 25 sources: 5 sources per language * 5 languages
        sources_data = [
            # English (en)
            {
                "slug": "ndtv_en",
                "name": "NDTV News (English)",
                "base_url": "https://www.ndtv.com",
                "article_list_url": "https://www.ndtv.com/india-news",
                "language": Language.ENGLISH,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "timesofindia_en",
                "name": "Times of India",
                "base_url": "https://timesofindia.indiatimes.com",
                "article_list_url": "https://timesofindia.indiatimes.com/india",
                "language": Language.ENGLISH,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "hindustantimes_en",
                "name": "Hindustan Times",
                "base_url": "https://www.hindustantimes.com",
                "article_list_url": "https://www.hindustantimes.com/india-news",
                "language": Language.ENGLISH,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "indianexpress_en",
                "name": "Indian Express",
                "base_url": "https://indianexpress.com",
                "article_list_url": "https://indianexpress.com/section/india/",
                "language": Language.ENGLISH,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "thehindu_en",
                "name": "The Hindu",
                "base_url": "https://www.thehindu.com",
                "article_list_url": "https://www.thehindu.com/news/national/",
                "language": Language.ENGLISH,
                "scrape_type": ScrapeType.RSS,
            },
            # Hindi (hi)
            {
                "slug": "ndtv_hindi",
                "name": "NDTV India (Hindi)",
                "base_url": "https://ndtv.in",
                "article_list_url": "https://ndtv.in/india",
                "language": Language.HINDI,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "aajtak_hindi",
                "name": "Aaj Tak",
                "base_url": "https://www.aajtak.in",
                "article_list_url": "https://www.aajtak.in/national",
                "language": Language.HINDI,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "dainikbhaskar_hindi",
                "name": "Dainik Bhaskar",
                "base_url": "https://www.bhaskar.com",
                "article_list_url": "https://www.bhaskar.com/national/",
                "language": Language.HINDI,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "zeenews_hindi",
                "name": "Zee News Hindi",
                "base_url": "https://zeenews.india.com/hindi",
                "article_list_url": "https://zeenews.india.com/hindi/india",
                "language": Language.HINDI,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "jagran_hindi",
                "name": "Dainik Jagran",
                "base_url": "https://www.jagran.com",
                "article_list_url": "https://www.jagran.com/news/national-news-apn.html",
                "language": Language.HINDI,
                "scrape_type": ScrapeType.STATIC,
            },
            # Tamil (ta)
            {
                "slug": "dailythanthi_ta",
                "name": "Daily Thanthi",
                "base_url": "https://www.dailythanthi.com",
                "article_list_url": "https://www.dailythanthi.com/News/State",
                "language": Language.TAMIL,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "dinamalar_ta",
                "name": "Dinamalar",
                "base_url": "https://www.dinamalar.com",
                "article_list_url": "https://www.dinamalar.com/tamil-news.asp",
                "language": Language.TAMIL,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "oneindia_ta",
                "name": "Oneindia Tamil",
                "base_url": "https://tamil.oneindia.com",
                "article_list_url": "https://tamil.oneindia.com/news/tamilnadu/",
                "language": Language.TAMIL,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "puthiyathalaimurai_ta",
                "name": "Puthiya Thalaimurai",
                "base_url": "https://www.puthiyathalaimurai.com",
                "article_list_url": "https://www.puthiyathalaimurai.com/tamilnadu",
                "language": Language.TAMIL,
                "scrape_type": ScrapeType.RSS,
            },
            {
                "slug": "vikatan_ta",
                "name": "Ananda Vikatan",
                "base_url": "https://www.vikatan.com",
                "article_list_url": "https://www.vikatan.com/news",
                "language": Language.TAMIL,
                "scrape_type": ScrapeType.STATIC,
            },
            # Telugu (te)
            {
                "slug": "sakshi_te",
                "name": "Sakshi",
                "base_url": "https://www.sakshi.com",
                "article_list_url": "https://www.sakshi.com/news/national",
                "language": Language.TELUGU,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "eenadu_te",
                "name": "Eenadu",
                "base_url": "https://www.eenadu.net",
                "article_list_url": "https://www.eenadu.net/national",
                "language": Language.TELUGU,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "andhrajyothy_te",
                "name": "Andhra Jyothy",
                "base_url": "https://www.andhrajyothy.com",
                "article_list_url": "https://www.andhrajyothy.com/national",
                "language": Language.TELUGU,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "namasthetelangaana_te",
                "name": "Namasthe Telangaana",
                "base_url": "https://www.ntnews.com",
                "article_list_url": "https://www.ntnews.com/national",
                "language": Language.TELUGU,
                "scrape_type": ScrapeType.RSS,
            },
            {
                "slug": "tv9_te",
                "name": "TV9 Telugu",
                "base_url": "https://tv9telugu.com",
                "article_list_url": "https://tv9telugu.com/national",
                "language": Language.TELUGU,
                "scrape_type": ScrapeType.STATIC,
            },
            # Kannada (kn)
            {
                "slug": "prajavani_kn",
                "name": "Prajavani",
                "base_url": "https://www.prajavani.net",
                "article_list_url": "https://www.prajavani.net/national",
                "language": Language.KANNADA,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "kannadaprabha_kn",
                "name": "Kannada Prabha",
                "base_url": "https://www.kannadaprabha.com",
                "article_list_url": "https://www.kannadaprabha.com/nation",
                "language": Language.KANNADA,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "vijaykarnataka_kn",
                "name": "Vijay Karnataka",
                "base_url": "https://vijaykarnataka.com",
                "article_list_url": "https://vijaykarnataka.com/news/india",
                "language": Language.KANNADA,
                "scrape_type": ScrapeType.PLAYWRIGHT,
            },
            {
                "slug": "udayavani_kn",
                "name": "Udayavani",
                "base_url": "https://www.udayavani.com",
                "article_list_url": "https://www.udayavani.com/national-news",
                "language": Language.KANNADA,
                "scrape_type": ScrapeType.RSS,
            },
            {
                "slug": "suvarnanews_kn",
                "name": "Suvarna News",
                "base_url": "https://kannada.asianetnews.com",
                "article_list_url": "https://kannada.asianetnews.com/india-news",
                "language": Language.KANNADA,
                "scrape_type": ScrapeType.STATIC,
            },
        ]

        sources_to_seed = []
        for s_info in sources_data:
            if s_info["slug"] not in existing_sources:
                sources_to_seed.append(
                    Source(
                        id=uuid.uuid4(),
                        slug=s_info["slug"],
                        name=s_info["name"],
                        base_url=s_info["base_url"],
                        article_list_url=s_info["article_list_url"],
                        language=s_info["language"],
                        scrape_type=s_info["scrape_type"],
                        rate_limit_seconds=2,
                        is_active=True,
                        is_healthy=True,
                    )
                )

        if sources_to_seed:
            session.add_all(sources_to_seed)
            session.commit()
            print(f"Added {len(sources_to_seed)} new news sources.")
        else:
            print("Sources already seeded.")

        # 3. Seed Test User
        print("Seeding test user...")
        test_email = "testuser@newssnap.ai"
        user = session.query(User).filter_by(email=test_email).first()
        if not user:
            user = User(
                id=uuid.uuid4(),
                email=test_email,
                name="Test User",
                hashed_password=None,  # Google OAuth representation
                role=UserRole.READER,
                is_active=True,
                is_onboarded=False,
            )
            session.add(user)
            session.flush()  # populate user.id

            # Create default preferences
            preferences = UserPreference(
                user_id=user.id,
                primary_language=Language.ENGLISH,
                secondary_language=Language.HINDI,
                categories=["politics", "sports", "technology"],
            )
            session.add(preferences)
            session.commit()
            print(f"Test user '{test_email}' created with preferences.")
        else:
            print("Test user already exists.")

        print("Database seeded successfully!")

    except Exception as e:
        session.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_database()
