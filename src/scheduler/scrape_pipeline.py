"""NewsSnap AI - Scrape Pipeline Orchestration (Issue 8).

Orchestrates the end-to-end news scraping pipeline:
1. Source rotation and staggering across interval
2. Scrape execution (Playwright / RSS / Static)
3. Parse and normalize article data
4. Store in database with duplicate detection
5. Track health metrics per source (5 consecutive failures -> unhealthy, 30 min cooldown)
6. Cycle logging and throughput metrics
7. Resilience: individual source failures do not crash the cycle
"""

import asyncio
import inspect
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.config.database import SessionLocal
from src.config.settings import Language, ScrapeType
from src.models.article import Article
from src.models.category import Category
from src.models.source import Source
from src.scrapers.article_parser import ScrapedArticle
from src.scrapers.playwright_scraper import PlaywrightScraper
from src.scrapers.rss_scraper import RSSScraper
from src.scrapers.source_registry import SourceConfig, SourceRegistry

logger = logging.getLogger(__name__)

# Constants
MAX_CONSECUTIVE_FAILURES = 5
COOLDOWN_MINUTES = 30


class ScrapePipeline:
    """Orchestrates scraping, deduplication, database storage, and health monitoring."""

    def __init__(self, registry: Optional[SourceRegistry] = None):
        self.registry = registry or SourceRegistry()
        self.registry.load_from_disk()

        # In-memory per-source health tracking
        # slug -> {consecutive_failures, is_healthy, unhealthy_since, cooldown_until,
        #          last_scrape_time, success_count, error_count, articles_scraped, last_error}
        self.source_health: Dict[str, Dict[str, Any]] = {}

        # Pipeline-wide metrics
        self.total_articles_scraped: int = 0
        self.total_duplicates_found: int = 0
        self.total_errors: int = 0
        self.cycle_count: int = 0
        self.last_cycle_time: Optional[datetime] = None
        self.cycle_history: List[Dict[str, Any]] = []

    # ----------------------------------------------------------------------
    # Source Health Management
    # ----------------------------------------------------------------------

    def _get_or_init_health(self, slug: str, name: str = "") -> Dict[str, Any]:
        """Get or initialize the in-memory health record for a source."""
        if slug not in self.source_health:
            self.source_health[slug] = {
                "slug": slug,
                "name": name or slug,
                "is_healthy": True,
                "status": "healthy",
                "consecutive_failures": 0,
                "unhealthy_since": None,
                "cooldown_until": None,
                "last_scrape_time": None,
                "success_count": 0,
                "error_count": 0,
                "articles_scraped": 0,
                "last_error": None,
            }
        elif name and not self.source_health[slug].get("name"):
            self.source_health[slug]["name"] = name
        return self.source_health[slug]

    def is_in_cooldown(self, slug: str, current_time: Optional[datetime] = None) -> bool:
        """
        Check if a source is currently in cooldown.
        If the cooldown period (30 mins) has expired, allows retry.
        """
        health = self._get_or_init_health(slug)
        if health["is_healthy"]:
            return False

        cooldown_until = health.get("cooldown_until")
        if not cooldown_until:
            return False

        now = current_time or datetime.now(timezone.utc)
        if cooldown_until.tzinfo is None and now.tzinfo is not None:
            cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
        elif cooldown_until.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if now < cooldown_until:
            return True  # Still in cooldown

        # Cooldown expired: allow retry
        return False

    def record_success(
        self,
        slug: str,
        articles_count: int = 0,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Record a successful scrape for a source."""
        health = self._get_or_init_health(slug)
        scrape_time = now or datetime.now(timezone.utc)

        health["consecutive_failures"] = 0
        health["is_healthy"] = True
        health["status"] = "healthy"
        health["unhealthy_since"] = None
        health["cooldown_until"] = None
        health["last_scrape_time"] = scrape_time
        health["success_count"] += 1
        health["articles_scraped"] += articles_count
        health["last_error"] = None

        if db:
            try:
                db_source = db.query(Source).filter(Source.slug == slug).first()
                if db_source:
                    db_source.last_scrape_time = scrape_time.replace(tzinfo=None) if scrape_time.tzinfo else scrape_time
                    db_source.success_count += 1
                    db_source.is_healthy = True
                    db.commit()
            except Exception as e:
                logger.debug(f"DB update skipped for {slug}: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

    def record_failure(
        self,
        slug: str,
        error_msg: str,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> None:
        """Record a failed scrape for a source. Marks unhealthy after 5 consecutive failures."""
        health = self._get_or_init_health(slug)
        fail_time = now or datetime.now(timezone.utc)

        health["consecutive_failures"] += 1
        health["error_count"] += 1
        health["last_error"] = error_msg

        if health["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            health["is_healthy"] = False
            health["status"] = "unhealthy"
            health["unhealthy_since"] = fail_time
            health["cooldown_until"] = fail_time + timedelta(minutes=COOLDOWN_MINUTES)
            logger.warning(
                f"Source {slug} marked UNHEALTHY after {health['consecutive_failures']} consecutive failures. "
                f"Cooldown active until {health['cooldown_until']}."
            )
        else:
            health["status"] = "degraded"

        if db:
            try:
                db_source = db.query(Source).filter(Source.slug == slug).first()
                if db_source:
                    db_source.error_count += 1
                    if not health["is_healthy"]:
                        db_source.is_healthy = False
                    db.commit()
            except Exception as e:
                logger.debug(f"DB update skipped for {slug}: {e}")
                try:
                    db.rollback()
                except Exception:
                    pass

    # ----------------------------------------------------------------------
    # Database Helper Methods
    # ----------------------------------------------------------------------

    def _get_or_create_category(self, db: Session, category_slug: str) -> Category:
        """Get an existing category or create a new one."""
        cat = db.query(Category).filter(Category.slug == category_slug).first()
        if not cat:
            cat = Category(
                slug=category_slug,
                name=category_slug.replace("_", " ").title(),
                is_active=True,
            )
            db.add(cat)
            db.flush()
        return cat

    def _get_or_create_source(self, db: Session, slug: str, config: Optional[SourceConfig] = None) -> Source:
        """Get or create the Source DB entity."""
        db_source = db.query(Source).filter(Source.slug == slug).first()
        if not db_source:
            cfg = config or self.registry.get_config(slug)
            name = cfg.name if cfg else slug.replace("_", " ").title()
            base_url = str(cfg.base_url) if cfg else f"https://{slug}.com"
            list_url = str(cfg.article_list_url) if cfg else base_url
            lang = cfg.language if cfg else Language.ENGLISH
            scr_type = cfg.scrape_type if cfg else ScrapeType.STATIC

            db_source = Source(
                slug=slug,
                name=name,
                base_url=base_url,
                article_list_url=list_url,
                language=lang,
                scrape_type=scr_type,
                is_active=True,
                is_healthy=True,
            )
            db.add(db_source)
            db.flush()
        return db_source

    def store_articles(
        self,
        db: Session,
        source_slug: str,
        articles: List[ScrapedArticle],
        config: Optional[SourceConfig] = None,
    ) -> tuple[int, int]:
        """
        Store parsed articles in the database with duplicate detection.
        Returns: (inserted_count, duplicate_count)
        """
        if not articles:
            return 0, 0

        db_source = self._get_or_create_source(db, source_slug, config)
        inserted = 0
        duplicates = 0

        for item in articles:
            # Check for existing article by source_url (duplicate check)
            existing = db.query(Article).filter(Article.source_url == item.source_url).first()
            if existing:
                duplicates += 1
                continue

            category_slug = item.category or "national"
            cat = self._get_or_create_category(db, category_slug)

            # Resolve language
            lang_val = item.language or (db_source.language.value if db_source.language else "en")
            try:
                article_lang = Language(lang_val)
            except ValueError:
                article_lang = Language.ENGLISH

            pub_time = item.publish_time
            if pub_time and pub_time.tzinfo is not None:
                pub_time = pub_time.replace(tzinfo=None)
            elif not pub_time:
                pub_time = datetime.utcnow()

            new_article = Article(
                title=item.title,
                body=item.body,
                source_id=db_source.id,
                category_id=cat.id,
                language=article_lang,
                source_url=item.source_url,
                image_url=item.image_url,
                publish_time=pub_time,
                author=item.author,
                is_duplicate=False,
            )
            db.add(new_article)
            inserted += 1

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error committing articles for {source_slug}: {e}")
            raise

        return inserted, duplicates

    # ----------------------------------------------------------------------
    # Single Source Scraping
    # ----------------------------------------------------------------------

    async def scrape_source(
        self,
        source_slug: str,
        db: Optional[Session] = None,
        custom_scraper: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Scrape, parse, and store articles for a single source.
        Handles errors gracefully and updates health state.
        """
        config = self.registry.get_config(source_slug)
        source_name = config.name if config else source_slug
        self._get_or_init_health(source_slug, source_name)

        # 1. Check cooldown
        if self.is_in_cooldown(source_slug):
            logger.info(f"Skipping {source_slug}: Source is in cooldown.")
            return {
                "status": "skipped_cooldown",
                "source_slug": source_slug,
                "articles_scraped": 0,
                "duplicates_found": 0,
                "errors": 0,
            }

        try:
            # 2. Fetch/Scrape articles
            scraped_items: List[ScrapedArticle] = []
            if custom_scraper:
                if inspect.iscoroutinefunction(custom_scraper.scrape_source):
                    scraped_items = await custom_scraper.scrape_source(source_slug)
                else:
                    scraped_items = custom_scraper.scrape_source(source_slug)
            elif config and config.scrape_type == ScrapeType.RSS:
                scraper = RSSScraper(registry=self.registry)
                scraped_items = await scraper.scrape_source(source_slug)
            elif config and config.scrape_type == ScrapeType.PLAYWRIGHT:
                scraper = PlaywrightScraper()
                scraped_items = await scraper.scrape_source(source_slug)
            else:
                # Default to RSS or empty
                scraper = RSSScraper(registry=self.registry)
                scraped_items = await scraper.scrape_source(source_slug)

            # 3. Store in DB if db session is provided
            inserted_count = len(scraped_items)
            duplicate_count = 0

            if db is not None:
                inserted_count, duplicate_count = self.store_articles(
                    db=db,
                    source_slug=source_slug,
                    articles=scraped_items,
                    config=config,
                )

            # 4. Record success
            self.record_success(source_slug, articles_count=inserted_count, db=db)
            self.total_articles_scraped += inserted_count
            self.total_duplicates_found += duplicate_count

            return {
                "status": "success",
                "source_slug": source_slug,
                "articles_scraped": inserted_count,
                "duplicates_found": duplicate_count,
                "errors": 0,
            }

        except Exception as e:
            error_str = str(e)
            logger.error(f"Scrape failure for source {source_slug}: {error_str}", exc_info=True)
            self.record_failure(source_slug, error_msg=error_str, db=db)
            self.total_errors += 1
            return {
                "status": "error",
                "source_slug": source_slug,
                "articles_scraped": 0,
                "duplicates_found": 0,
                "errors": 1,
                "error_message": error_str,
            }

    # ----------------------------------------------------------------------
    # Full Scrape Cycle Orchestration
    # ----------------------------------------------------------------------

    async def run_scrape_cycle(
        self,
        db: Optional[Session] = None,
        sources: Optional[List[str]] = None,
        stagger_seconds: float = 0.0,
        custom_scraper: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Run a full scrape cycle across all configured sources.
        - Spreads/staggers sources across the interval
        - Handles individual failures gracefully (cycle continues)
        - Logs articles scraped, duplicates found, errors per cycle
        """
        start_time = datetime.now(timezone.utc)

        # Get list of source slugs
        if sources is None:
            if not self.registry.configs:
                self.registry.load_from_disk()
            slugs = list(self.registry.configs.keys())
        else:
            slugs = sources

        logger.info(f"--- Starting scrape cycle for {len(slugs)} sources ---")

        cycle_articles = 0
        cycle_duplicates = 0
        cycle_errors = 0
        results = []

        owns_session = False
        if db is None:
            try:
                db = SessionLocal()
                owns_session = True
            except Exception as e:
                logger.debug(f"DB session not available for scrape cycle, running in-memory: {e}")
                db = None

        try:
            for idx, slug in enumerate(slugs):
                # Stagger across interval if delay requested and not first source
                if stagger_seconds > 0 and idx > 0:
                    logger.debug(f"Stagger delay of {stagger_seconds}s before scraping {slug}")
                    await asyncio.sleep(stagger_seconds)

                # Scrape single source (survives individual failures)
                res = await self.scrape_source(slug, db=db, custom_scraper=custom_scraper)
                results.append(res)
                cycle_articles += res.get("articles_scraped", 0)
                cycle_duplicates += res.get("duplicates_found", 0)
                cycle_errors += res.get("errors", 0)

        finally:
            if owns_session and db is not None:
                try:
                    db.close()
                except Exception:
                    pass

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        # Update cycle metadata
        self.cycle_count += 1
        self.last_cycle_time = end_time
        cycle_summary = {
            "cycle_number": self.cycle_count,
            "timestamp": end_time.isoformat(),
            "sources_attempted": len(slugs),
            "articles_scraped": cycle_articles,
            "duplicates_found": cycle_duplicates,
            "errors": cycle_errors,
            "duration_seconds": round(duration, 2),
        }
        self.cycle_history.append(cycle_summary)
        if len(self.cycle_history) > 50:
            self.cycle_history.pop(0)

        # Acceptance Criteria 7: Pipeline logs: articles scraped, duplicates found, errors per cycle
        logger.info(
            f"=== Scrape cycle completed: articles_scraped={cycle_articles}, "
            f"duplicates_found={cycle_duplicates}, errors={cycle_errors}, "
            f"sources_scraped={len(slugs)}, duration={duration:.2f}s ==="
        )

        return {
            "cycle_summary": cycle_summary,
            "results": results,
        }

    # ----------------------------------------------------------------------
    # Health and Dashboard Metrics
    # ----------------------------------------------------------------------

    def get_health_metrics(self, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Return per-source health metrics and pipeline throughput for GET /api/admin/scrape-health.
        """
        # Ensure all registered sources appear in metrics
        if not self.registry.configs:
            self.registry.load_from_disk()

        for slug, cfg in self.registry.configs.items():
            self._get_or_init_health(slug, cfg.name)

        sources_data = []
        for slug, h in self.source_health.items():
            last_scrape = h["last_scrape_time"]
            if isinstance(last_scrape, datetime):
                last_scrape_str = last_scrape.isoformat()
            else:
                last_scrape_str = None

            cooldown = h["cooldown_until"]
            if isinstance(cooldown, datetime):
                cooldown_str = cooldown.isoformat()
            else:
                cooldown_str = None

            total_attempts = h["success_count"] + h["error_count"]
            source_err_rate = round(h["error_count"] / total_attempts, 2) if total_attempts > 0 else 0.0

            sources_data.append(
                {
                    "slug": slug,
                    "name": h.get("name", slug),
                    "is_healthy": h["is_healthy"],
                    "status": h.get("status", "healthy"),
                    "consecutive_failures": h["consecutive_failures"],
                    "success_count": h["success_count"],
                    "error_count": h["error_count"],
                    "error_rate": source_err_rate,
                    "articles_scraped": h["articles_scraped"],
                    "last_scrape_time": last_scrape_str,
                    "cooldown_until": cooldown_str,
                    "last_error": h["last_error"],
                }
            )

        total_requests = (
            sum(s["success_count"] + s["error_count"] for s in sources_data)
            if sources_data
            else (self.total_articles_scraped + self.total_errors)
        )
        overall_error_rate = round(self.total_errors / total_requests, 4) if total_requests > 0 else 0.0

        return {
            "sources": sources_data,
            "pipeline": {
                "total_articles_scraped": self.total_articles_scraped,
                "total_duplicates_found": self.total_duplicates_found,
                "total_errors": self.total_errors,
                "total_cycles_completed": self.cycle_count,
                "overall_error_rate": overall_error_rate,
                "last_cycle_time": self.last_cycle_time.isoformat() if self.last_cycle_time else None,
            },
        }

    def get_recent_articles(
        self,
        db: Session,
        limit: int = 10,
        source_slug: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch recently scraped articles for administration and monitoring."""
        query = db.query(Article)
        if source_slug:
            source = db.query(Source).filter(Source.slug == source_slug).first()
            if source:
                query = query.filter(Article.source_id == source.id)
            else:
                return []

        articles = query.order_by(Article.created_at.desc()).limit(limit).all()

        results = []
        for a in articles:
            src = a.source
            cat = a.category
            results.append(
                {
                    "id": str(a.id),
                    "title": a.title,
                    "source_url": a.source_url,
                    "publish_time": a.publish_time.isoformat() if a.publish_time else None,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "category": cat.slug if cat else "national",
                    "source_slug": src.slug if src else None,
                    "source_name": src.name if src else None,
                    "language": a.language.value if hasattr(a.language, "value") else str(a.language),
                    "image_url": a.image_url,
                    "author": a.author,
                    "is_duplicate": a.is_duplicate,
                }
            )
        return results


# Global pipeline instance
pipeline_instance = ScrapePipeline()
