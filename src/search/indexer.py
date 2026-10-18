"""NewsSnap AI - Article Search Indexer (Issue 18).

Responsible for:
- Formatting articles and snap translations into Meilisearch schema
- Batch indexing of articles
- Auto-indexing hook for new articles processed by pipeline
- Full database re-indexing (`index_all()`)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from src.config.database import SessionLocal
from src.models.article import Article
from src.models.snap import Snap
from src.search.meilisearch_client import MeilisearchClient, meilisearch_client

logger = logging.getLogger(__name__)


class SearchIndexer:
    """Indexes articles and multilingual summaries into Meilisearch."""

    def __init__(
        self,
        client: Optional[MeilisearchClient] = None,
        db: Optional[Session] = None,
    ):
        self.client = client or meilisearch_client
        self._db = db

    def _get_db(self) -> Session:
        """Provide or create DB session."""
        if self._db is not None:
            return self._db
        return SessionLocal()

    @staticmethod
    def format_article_document(
        article: Article,
        snap: Optional[Snap] = None,
    ) -> Dict[str, Any]:
        """
        Format an Article and its associated Snap/translations into a Meilisearch document.
        Includes all 5 language translations when available.
        """
        # Resolve source and category metadata
        src = getattr(article, "source", None)
        source_slug = src.slug if src and hasattr(src, "slug") else "unknown"
        source_name = src.name if src and hasattr(src, "name") else "Unknown"

        cat = getattr(article, "category", None)
        category_slug = cat.slug if cat and hasattr(cat, "slug") else "national"

        # Resolve snap (if not provided, check article.snaps relationship)
        resolved_snap = snap
        if resolved_snap is None and hasattr(article, "snaps") and article.snaps:
            resolved_snap = article.snaps[0]

        # Extract timestamps
        pub_time = getattr(article, "publish_time", None)
        if pub_time and isinstance(pub_time, datetime):
            pub_ts = int(pub_time.timestamp())
            pub_iso = pub_time.isoformat()
        else:
            now = datetime.utcnow()
            pub_ts = int(now.timestamp())
            pub_iso = now.isoformat()

        # Primary summary
        primary_summary = ""
        if resolved_snap and getattr(resolved_snap, "summary", None):
            primary_summary = resolved_snap.summary
        elif getattr(article, "body", None):
            primary_summary = article.body[:300]

        # Primary language
        art_lang = getattr(article, "language", "en")
        if hasattr(art_lang, "value"):
            art_lang_val = art_lang.value
        else:
            art_lang_val = str(art_lang)

        # Base document
        doc: Dict[str, Any] = {
            "id": str(article.id),
            "article_id": str(article.id),
            "title": article.title,
            "body": article.body[:1000] if getattr(article, "body", None) else "",
            "summary": primary_summary,
            "category": category_slug,
            "source": source_slug,
            "source_name": source_name,
            "source_url": article.source_url if getattr(article, "source_url", None) else "",
            "image_url": article.image_url or (resolved_snap.image_url if resolved_snap else ""),
            "publish_time": pub_ts,
            "publish_time_iso": pub_iso,
            "language": art_lang_val,
            "snap_id": str(resolved_snap.id) if resolved_snap else None,
            "quality_score": getattr(article, "quality_score", None),
        }

        # Initialize language summary fields
        doc["summary_en"] = primary_summary if art_lang_val == "en" else ""
        doc["summary_hi"] = primary_summary if art_lang_val == "hi" else ""
        doc["summary_ta"] = primary_summary if art_lang_val == "ta" else ""
        doc["summary_te"] = primary_summary if art_lang_val == "te" else ""
        doc["summary_kn"] = primary_summary if art_lang_val == "kn" else ""

        # Map translations from Snap
        if resolved_snap and hasattr(resolved_snap, "translations") and resolved_snap.translations:
            for trans in resolved_snap.translations:
                trans_lang = getattr(trans, "language", None)
                if hasattr(trans_lang, "value"):
                    lang_key = trans_lang.value
                else:
                    lang_key = str(trans_lang)

                trans_summary = getattr(trans, "summary", "")
                if trans_summary:
                    doc[f"summary_{lang_key}"] = trans_summary

        # Default fallback for empty translations
        for lang in ["en", "hi", "ta", "te", "kn"]:
            key = f"summary_{lang}"
            if not doc.get(key):
                doc[key] = primary_summary

        return doc

    def index_article(
        self,
        article: Article,
        snap: Optional[Snap] = None,
        wait: bool = False,
    ) -> bool:
        """Index a single article into Meilisearch."""
        try:
            doc = self.format_article_document(article, snap=snap)
            self.client.add_documents([doc], wait=wait)
            return True
        except Exception as e:
            logger.error(f"Failed to index article {article.id}: {e}")
            return False

    def index_batch(
        self,
        articles: List[Article],
        wait: bool = False,
    ) -> int:
        """Index a batch of articles into Meilisearch."""
        if not articles:
            return 0

        docs: List[Dict[str, Any]] = []
        for art in articles:
            try:
                docs.append(self.format_article_document(art))
            except Exception as e:
                logger.warning(f"Error formatting article {getattr(art, 'id', 'unknown')}: {e}")

        if not docs:
            return 0

        try:
            self.client.add_documents(docs, wait=wait)
            return len(docs)
        except Exception as e:
            logger.error(f"Failed to index batch of {len(docs)} articles: {e}")
            return 0

    def index_all(
        self,
        db: Optional[Session] = None,
        batch_size: int = 100,
        wait: bool = True,
    ) -> int:
        """
        Re-index all articles from database with their categories, sources, snaps, and translations.
        Used for initial indexing and sync.
        """
        session = db or self._get_db()
        should_close = db is None and self._db is None

        # Ensure index settings exist
        try:
            self.client.init_index(wait=wait)
        except Exception as e:
            logger.warning(f"Could not initialize Meilisearch index during index_all: {e}")

        total_indexed = 0

        try:
            query = (
                session.query(Article)
                .filter(Article.is_duplicate.is_(False))
                .options(
                    joinedload(Article.source),
                    joinedload(Article.category),
                    joinedload(Article.snaps).joinedload(Snap.translations),
                )
            )

            offset = 0
            while True:
                batch = query.offset(offset).limit(batch_size).all()
                if not batch:
                    break

                count = self.index_batch(batch, wait=wait)
                total_indexed += count
                offset += batch_size

                logger.info(f"Indexed batch: {total_indexed} total articles indexed so far.")

            return total_indexed
        finally:
            if should_close:
                session.close()

    def delete_article(self, article_id: str, wait: bool = False) -> bool:
        """Remove article from search index."""
        try:
            self.client.delete_document(str(article_id), wait=wait)
            return True
        except Exception as e:
            logger.error(f"Failed to delete article {article_id} from index: {e}")
            return False

    def get_count(self) -> int:
        """Get count of indexed articles in Meilisearch."""
        return self.client.get_count()

    def auto_index_article(self, article: Article, snap: Optional[Snap] = None) -> bool:
        """
        Graceful auto-indexing hook for new articles processed in the pipeline.
        Ensures search failures do not crash the pipeline.
        """
        try:
            return self.index_article(article, snap=snap, wait=False)
        except Exception as e:
            logger.warning(f"Auto-indexing skipped for article {getattr(article, 'id', None)}: {e}")
            return False


# Global singleton indexer
search_indexer = SearchIndexer()
