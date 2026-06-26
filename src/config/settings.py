"""NewsSnap AI - Application settings and configuration."""

import os
from enum import Enum
from urllib.parse import urlparse, urlunparse

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Language(str, Enum):
    ENGLISH = "en"
    HINDI = "hi"
    TAMIL = "ta"
    TELUGU = "te"
    KANNADA = "kn"


class Category(str, Enum):
    # Core news
    NATIONAL = "national"  # India domestic news, governance, policy
    INTERNATIONAL = "international"  # Global news, foreign affairs, geopolitics
    POLITICS = "politics"  # Elections, parties, parliament, state politics
    BUSINESS = "business"  # Corporate, startups, economy, GDP, trade
    FINANCE = "finance"  # Markets, stocks, mutual funds, crypto, RBI, banking
    SPORTS = "sports"  # Cricket, football, Olympics, IPL, kabaddi

    # Tech and science
    TECHNOLOGY = "technology"  # AI, gadgets, apps, internet, social media
    SCIENCE = "science"  # Space, research, discoveries, ISRO
    AUTOMOBILE = "automobile"  # Cars, bikes, EVs, launches, reviews

    # Society
    EDUCATION = "education"  # Exams, results, universities, NEP, scholarships
    HEALTH = "health"  # Medical, fitness, diseases, pharma, Ayushman Bharat
    ENTERTAINMENT = "entertainment"  # Bollywood, OTT, music, celebrities, TV
    LIFESTYLE = "lifestyle"  # Food, travel, fashion, relationships, wellness

    # India specific
    CRIME = "crime"  # Law, court verdicts, scams, cybercrime
    ENVIRONMENT = "environment"  # Climate, pollution, wildlife, disasters, weather
    JOBS = "jobs"  # Government jobs, sarkari naukri, recruitment, placements
    DEFENCE = "defence"  # Military, armed forces, defence deals, border security
    REAL_ESTATE = "real_estate"  # Property, housing, RERA, smart cities
    OPINION = "opinion"  # Editorials, columns, analysis, debates


class ScrapeType(str, Enum):
    PLAYWRIGHT = "playwright"
    RSS = "rss"
    STATIC = "static"


class UserRole(str, Enum):
    READER = "reader"
    ADMIN = "admin"





class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://newssnap:newssnap@localhost:5432/newssnap"
    DATABASE_POOL_SIZE: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Configs
    JWT_SECRET_KEY: str = "generate_with_python_secrets_token_hex_32"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Google OAuth
    GOOGLE_CLIENT_ID: str = "your_google_client_id_here"
    GOOGLE_CLIENT_SECRET: str = "your_google_client_secret_here"
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @model_validator(mode="after")
    def adjust_docker_urls(self) -> "Settings":
        # Check if we are running outside a Docker container (locally on host macOS)
        if not os.path.exists("/.dockerenv") and not os.environ.get("DOCKER_CONTAINER"):
            for field in ("DATABASE_URL", "REDIS_URL"):
                val = getattr(self, field, None)
                if val:
                    try:
                        parsed = urlparse(val)
                        if parsed.hostname in ("db", "redis", "meilisearch"):
                            netloc = parsed.netloc.replace(parsed.hostname, "localhost")
                            setattr(self, field, urlunparse(parsed._replace(netloc=netloc)))
                    except Exception:
                        pass
        return self


settings = Settings()


