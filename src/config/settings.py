"""NewsSnap AI - Application settings and configuration."""

from enum import Enum


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
