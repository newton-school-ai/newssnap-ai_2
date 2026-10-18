"""NewsSnap AI - Meilisearch Client Integration (Issue 18).

Provides client wrapper for:
- Connection and health checks
- Index initialization with searchable, filterable, sortable attributes and typo tolerance
- Document indexing, batching, updating, and deletion
- Fast, typo-tolerant multi-language search with faceted filtering
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import meilisearch
from meilisearch.index import Index

from src.config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_SEARCHABLE_ATTRIBUTES = [
    "title",
    "summary",
    "title_en",
    "summary_en",
    "title_hi",
    "summary_hi",
    "title_ta",
    "summary_ta",
    "title_te",
    "summary_te",
    "title_kn",
    "summary_kn",
    "category",
    "source_name",
    "source",
    "body",
]

DEFAULT_FILTERABLE_ATTRIBUTES = [
    "category",
    "source",
    "source_name",
    "language",
    "publish_time",
]

DEFAULT_SORTABLE_ATTRIBUTES = [
    "publish_time",
]

DEFAULT_TYPO_TOLERANCE = {
    "enabled": True,
    "minWordSizeForTypos": {
        "oneTypo": 4,
        "twoTypos": 8,
    },
    "disableOnWords": [],
    "disableOnAttributes": [],
}


class MeilisearchClient:
    """Wrapper around Meilisearch Python client for news article search."""

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
    ):
        self.url = url or settings.MEILISEARCH_URL
        self.api_key = api_key or settings.MEILISEARCH_API_KEY
        self.index_name = index_name or settings.MEILISEARCH_INDEX_NAME
        self._client: Optional[meilisearch.Client] = None

    @property
    def client(self) -> meilisearch.Client:
        """Lazy-initialize Meilisearch client."""
        if self._client is None:
            self._client = meilisearch.Client(url=self.url, api_key=self.api_key)
        return self._client

    def is_healthy(self) -> bool:
        """Check if Meilisearch server is reachable and healthy."""
        try:
            return self.client.is_healthy()
        except Exception as e:
            logger.debug(f"Meilisearch health check failed: {e}")
            return False

    def get_index(self, index_name: Optional[str] = None) -> Index:
        """Get index reference."""
        target_index = index_name or self.index_name
        return self.client.index(target_index)

    def init_index(
        self,
        index_name: Optional[str] = None,
        searchable_attributes: Optional[List[str]] = None,
        filterable_attributes: Optional[List[str]] = None,
        sortable_attributes: Optional[List[str]] = None,
        typo_tolerance: Optional[Dict[str, Any]] = None,
        wait: bool = False,
    ) -> Index:
        """
        Create and configure index if it doesn't already exist.
        Configures searchable, filterable, sortable fields and typo tolerance.
        """
        target_index = index_name or self.index_name

        try:
            # Check if index exists or create it
            index = self.client.get_index(target_index)
        except Exception:
            task = self.client.create_index(uid=target_index, options={"primaryKey": "id"})
            if wait and hasattr(task, "task_uid"):
                self.client.wait_for_task(task.task_uid)
            index = self.client.index(target_index)

        # Update index settings
        settings_payload: Dict[str, Any] = {
            "searchableAttributes": searchable_attributes or DEFAULT_SEARCHABLE_ATTRIBUTES,
            "filterableAttributes": filterable_attributes or DEFAULT_FILTERABLE_ATTRIBUTES,
            "sortableAttributes": sortable_attributes or DEFAULT_SORTABLE_ATTRIBUTES,
            "typoTolerance": typo_tolerance or DEFAULT_TYPO_TOLERANCE,
        }

        try:
            task = index.update_settings(settings_payload)
            if wait and hasattr(task, "task_uid"):
                self.client.wait_for_task(task.task_uid)
        except Exception as e:
            logger.warning(f"Could not update Meilisearch settings for {target_index}: {e}")

        return index

    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        index_name: Optional[str] = None,
        primary_key: str = "id",
        wait: bool = False,
    ) -> Any:
        """Index a batch of documents into Meilisearch."""
        if not documents:
            return None

        index = self.get_index(index_name)
        task = index.add_documents(documents, primary_key=primary_key)
        if wait and hasattr(task, "task_uid"):
            return self.client.wait_for_task(task.task_uid)
        return task

    def update_documents(
        self,
        documents: List[Dict[str, Any]],
        index_name: Optional[str] = None,
        primary_key: str = "id",
        wait: bool = False,
    ) -> Any:
        """Update existing documents or insert new ones."""
        if not documents:
            return None

        index = self.get_index(index_name)
        task = index.update_documents(documents, primary_key=primary_key)
        if wait and hasattr(task, "task_uid"):
            return self.client.wait_for_task(task.task_uid)
        return task

    def delete_documents(
        self,
        document_ids: List[str],
        index_name: Optional[str] = None,
        wait: bool = False,
    ) -> Any:
        """Delete documents by their IDs."""
        if not document_ids:
            return None

        index = self.get_index(index_name)
        task = index.delete_documents(document_ids)
        if wait and hasattr(task, "task_uid"):
            return self.client.wait_for_task(task.task_uid)
        return task

    def delete_document(
        self,
        document_id: str,
        index_name: Optional[str] = None,
        wait: bool = False,
    ) -> Any:
        """Delete a single document by ID."""
        return self.delete_documents([document_id], index_name=index_name, wait=wait)

    def delete_all_documents(
        self,
        index_name: Optional[str] = None,
        wait: bool = False,
    ) -> Any:
        """Delete all documents in the index."""
        index = self.get_index(index_name)
        task = index.delete_all_documents()
        if wait and hasattr(task, "task_uid"):
            return self.client.wait_for_task(task.task_uid)
        return task

    def get_document(
        self,
        document_id: str,
        index_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a single document by ID."""
        try:
            index = self.get_index(index_name)
            return index.get_document(document_id)
        except Exception as e:
            logger.debug(f"Document {document_id} not found: {e}")
            return None

    def get_count(self, index_name: Optional[str] = None) -> int:
        """Get the total number of documents in the index."""
        try:
            index = self.get_index(index_name)
            stats = index.get_stats()
            # Handle both object attributes and dict
            if hasattr(stats, "number_of_documents"):
                return stats.number_of_documents
            if isinstance(stats, dict):
                return stats.get("numberOfDocuments", 0)
            return 0
        except Exception as e:
            logger.debug(f"Failed to get index document count: {e}")
            return 0

    @staticmethod
    def build_filter_string(
        category: Optional[str] = None,
        source: Optional[str] = None,
        start_date: Optional[Union[int, float, datetime, str]] = None,
        end_date: Optional[Union[int, float, datetime, str]] = None,
        language: Optional[str] = None,
        custom_filter: Optional[str] = None,
    ) -> Optional[str]:
        """Build Meilisearch filter string expression from filter criteria."""
        clauses: List[str] = []

        if category:
            clauses.append(f'category = "{category.lower().strip()}"')

        if source:
            clauses.append(f'source = "{source.lower().strip()}"')

        if language:
            clauses.append(f'language = "{language.lower().strip()}"')

        def _to_timestamp(val: Union[int, float, datetime, str]) -> int:
            if isinstance(val, (int, float)):
                return int(val)
            if isinstance(val, datetime):
                return int(val.timestamp())
            if isinstance(val, str):
                # Try parsing ISO format or YYYY-MM-DD
                try:
                    return int(datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp())
                except ValueError:
                    return int(datetime.strptime(val, "%Y-%m-%d").timestamp())
            return 0

        if start_date is not None:
            clauses.append(f"publish_time >= {_to_timestamp(start_date)}")

        if end_date is not None:
            clauses.append(f"publish_time <= {_to_timestamp(end_date)}")

        if custom_filter:
            clauses.append(custom_filter)

        if not clauses:
            return None

        return " AND ".join(clauses)

    def search(
        self,
        query: str = "",
        category: Optional[str] = None,
        source: Optional[str] = None,
        start_date: Optional[Union[int, float, datetime, str]] = None,
        end_date: Optional[Union[int, float, datetime, str]] = None,
        filter_language: Optional[str] = None,
        target_language: str = "en",
        limit: int = 20,
        offset: int = 0,
        sort: Optional[List[str]] = None,
        facets: Optional[List[str]] = None,
        custom_filter: Optional[str] = None,
        index_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute search query with typo tolerance, multilingual matching, and faceted filtering.

        Returns:
            Dict containing:
            - hits: list of matching document dicts formatted for target_language
            - total: total number of matching hits
            - limit: pagination limit
            - offset: pagination offset
            - processing_time_ms: time taken in ms
            - facet_distribution: distribution of facets
            - query: search term
        """
        start_wall_time = time.perf_counter()
        index = self.get_index(index_name)

        filter_str = self.build_filter_string(
            category=category,
            source=source,
            start_date=start_date,
            end_date=end_date,
            language=filter_language,
            custom_filter=custom_filter,
        )

        opt_params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        if filter_str:
            opt_params["filter"] = filter_str

        # Default facets to category and source for rich discovery
        opt_params["facets"] = facets or ["category", "source"]

        # Default sorting: if query is empty, sort by publish_time desc
        if sort:
            opt_params["sort"] = sort
        elif not query.strip():
            opt_params["sort"] = ["publish_time:desc"]

        raw_result = index.search(query, opt_params)

        elapsed_ms = round((time.perf_counter() - start_wall_time) * 1000, 2)
        processing_ms = raw_result.get("processingTimeMs", elapsed_ms)

        raw_hits = raw_result.get("hits", [])
        formatted_hits = []

        for hit in raw_hits:
            doc = dict(hit)
            # Localize title and summary if target_language translation exists
            lang_key = target_language.lower().strip()
            summary_trans = doc.get(f"summary_{lang_key}")
            if summary_trans:
                doc["summary"] = summary_trans

            title_trans = doc.get(f"title_{lang_key}")
            if title_trans:
                doc["title"] = title_trans

            formatted_hits.append(doc)

        return {
            "hits": formatted_hits,
            "total": raw_result.get("estimatedTotalHits", len(formatted_hits)),
            "limit": limit,
            "offset": offset,
            "processing_time_ms": processing_ms,
            "facet_distribution": raw_result.get("facetDistribution", {}),
            "query": query,
        }


# Global singleton client instance
meilisearch_client = MeilisearchClient()
