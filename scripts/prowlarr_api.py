"""
Prowlarr API integration module
Handles all Prowlarr searches and API interactions
"""

import aiohttp
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

from config import Config

logger = logging.getLogger(__name__)


class SearchCategory(Enum):
    """Search categories for Prowlarr"""

    AUDIOBOOK = 3010
    EBOOK = 3030
    ALL = None  # No specific category filter


@dataclass
class SearchResult:
    """Data class representing a single search result"""

    title: str
    download_url: str
    seeders: int
    leechers: int
    size: int
    indexer: str
    publish_date: str
    guid: str
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "title": self.title,
            "download_url": self.download_url,
            "seeders": self.seeders,
            "leechers": self.leechers,
            "size": self.size,
            "indexer": self.indexer,
            "publish_date": self.publish_date,
            "guid": self.guid,
        }

    @property
    def health_score(self) -> float:
        """Calculate health score based on seeders/leechers"""
        total = self.seeders + self.leechers
        if total == 0:
            return 0.0
        return (self.seeders / total) * 100


class ProwlarrAPI:
    """Prowlarr API client for searching indexers"""

    def __init__(self):
        """Initialize Prowlarr API client"""
        self.base_url = Config.PROWLARR_URL.rstrip("/")
        self.api_key = Config.PROWLARR_API_KEY
        self.timeout = aiohttp.ClientTimeout(total=Config.PROWLARR_TIMEOUT)
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with API key"""
        return {"X-Api-Key": self.api_key, "Content-Type": "application/json"}

    async def health_check(self) -> bool:
        """
        Check if Prowlarr is accessible and API key is valid

        Returns:
            True if healthy, False otherwise
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/v1/system/status"
            async with session.get(url, headers=self._get_headers()) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Prowlarr health check failed: {e}")
            return False

    async def search(
        self,
        query: str,
        category: SearchCategory = SearchCategory.ALL,
        limit: int = 50,
    ) -> List[SearchResult]:
        """
        Search Prowlarr indexers for a query

        Args:
            query: Search query string
            category: Search category (AUDIOBOOK, EBOOK, or ALL)
            limit: Maximum number of results to return

        Returns:
            List of SearchResult objects

        Raises:
            ValueError: If query is empty
            Exception: If API request fails
        """
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")

        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/v1/search"

            params = {
                "query": query.strip(),
                "type": "search",
            }

            # Don't add category filter - let Prowlarr search all categories
            # Category filtering was causing 0 results

            logger.debug(f"Prowlarr API call: {url}")
            logger.debug(f"Prowlarr params: {params}")

            async with session.get(
                url, headers=self._get_headers(), params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"Prowlarr search failed with status {response.status}: {error_text}"
                    )
                    raise Exception(
                        f"Prowlarr API error: {response.status} - {error_text}"
                    )

                data = await response.json()
                logger.debug(f"Prowlarr API returned {len(data)} raw results")
                results = self._parse_search_results(data)

                logger.info(f"Found {len(results)} valid results for query: {query} (from {len(data)} API results)")
                return results

        except aiohttp.ClientError as e:
            logger.error(f"Prowlarr connection error: {e}")
            raise Exception(f"Failed to connect to Prowlarr: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during Prowlarr search: {e}")
            raise

    def _parse_search_results(self, data: List[Dict]) -> List[SearchResult]:
        """
        Parse raw API response into SearchResult objects

        Args:
            data: Raw API response data

        Returns:
            List of parsed SearchResult objects
        """
        results = []
        logger.debug(f"Parsing {len(data)} raw results from Prowlarr")

        for idx, item in enumerate(data):
            try:
                # Extract required fields with defaults
                title = item.get("title", "Unknown")
                download_url = item.get("downloadUrl") or item.get("magnetUrl", "")

                # Skip if no download URL
                if not download_url:
                    logger.debug(f"Result {idx}: Skipping '{title}' (no download URL)")
                    continue

                logger.debug(f"Result {idx}: Accepting '{title}' from {item.get('indexer', 'Unknown')}")

                result = SearchResult(
                    title=title,
                    download_url=download_url,
                    seeders=int(item.get("seeders", 0)),
                    leechers=int(item.get("leechers", 0)),
                    size=int(item.get("size", 0)),
                    indexer=item.get("indexer", "Unknown"),
                    publish_date=item.get("publishDate", ""),
                    guid=item.get("guid", ""),
                    imdb_id=item.get("imdbId"),
                    tvdb_id=item.get("tvdbId"),
                    tmdb_id=item.get("tmdbId"),
                )
                results.append(result)

            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Error parsing search result: {e}, item: {item}")
                continue

        logger.debug(f"Parsed {len(results)} valid results from {len(data)} total")
        return results

    async def search_audiobook(
        self, query: str, limit: int = 50
    ) -> List[SearchResult]:
        """
        Search specifically for audiobooks

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of SearchResult objects
        """
        # Search without category filter, return all results
        # Prowlarr category filtering can be too restrictive
        return await self.search(query, SearchCategory.ALL, limit)

    async def search_ebook(self, query: str, limit: int = 50) -> List[SearchResult]:
        """
        Search specifically for ebooks

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of SearchResult objects
        """
        # Search without category filter, return all results
        # Prowlarr category filtering can be too restrictive
        return await self.search(query, SearchCategory.ALL, limit)

    async def get_indexers(self) -> List[Dict[str, Any]]:
        """
        Get list of configured indexers

        Returns:
            List of indexer information dicts
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/v1/indexer"

            async with session.get(url, headers=self._get_headers()) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"Failed to get indexers: {response.status} - {error_text}"
                    )
                    return []

                data = await response.json()
                logger.info(f"Retrieved {len(data)} indexers from Prowlarr")
                return data

        except Exception as e:
            logger.error(f"Error getting indexers: {e}")
            return []

    async def get_active_indexers(self) -> List[str]:
        """
        Get list of active (enabled) indexer names

        Returns:
            List of active indexer names
        """
        indexers = await self.get_indexers()
        active = [idx.get("name") for idx in indexers if idx.get("enable", False)]
        return active

    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None


async def search_prowlarr(
    query: str, category: SearchCategory = SearchCategory.ALL, limit: int = 50
) -> List[SearchResult]:
    """
    Standalone function to search Prowlarr

    Args:
        query: Search query
        category: Search category
        limit: Maximum number of results

    Returns:
        List of SearchResult objects
    """
    async with ProwlarrAPI() as api:
        return await api.search(query, category, limit)


async def search_audiobook(query: str, limit: int = 50) -> List[SearchResult]:
    """
    Standalone function to search for audiobooks

    Args:
        query: Search query
        limit: Maximum number of results

    Returns:
        List of SearchResult objects
    """
    async with ProwlarrAPI() as api:
        return await api.search_audiobook(query, limit)


async def search_ebook(query: str, limit: int = 50) -> List[SearchResult]:
    """
    Standalone function to search for ebooks

    Args:
        query: Search query
        limit: Maximum number of results

    Returns:
        List of SearchResult objects
    """
    async with ProwlarrAPI() as api:
        return await api.search_ebook(query, limit)


async def test_prowlarr_connection() -> bool:
    """
    Test connection to Prowlarr API

    Returns:
        True if connection successful, False otherwise
    """
    async with ProwlarrAPI() as api:
        return await api.health_check()
