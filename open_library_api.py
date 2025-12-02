"""
Open Library API integration
Search for books and display metadata without exposing indexers
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

OPEN_LIBRARY_API_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_COVERS_URL = "https://covers.openlibrary.org/b"


@dataclass
class BookMetadata:
    """Book metadata from Open Library API"""
    title: str
    authors: List[str]
    first_publish_year: Optional[int] = None
    isbn_10: Optional[str] = None
    isbn_13: Optional[str] = None
    cover_id: Optional[str] = None
    description: str = ""
    has_audiobook: bool = False
    has_ebook: bool = False
    image_url: Optional[str] = None  # For Google Books images

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "title": self.title,
            "authors": self.authors,
            "first_publish_year": self.first_publish_year,
            "isbn_10": self.isbn_10,
            "isbn_13": self.isbn_13,
            "cover_id": self.cover_id,
            "description": self.description,
            "has_audiobook": self.has_audiobook,
            "has_ebook": self.has_ebook,
            "image_url": self.image_url,
        }

    def get_cover_url(self, size: str = "M") -> Optional[str]:
        """
        Get cover image URL (prioritizes Google Books image_url, falls back to Open Library cover_id)

        Args:
            size: Image size - S (small), M (medium), L (large)

        Returns:
            Cover image URL or None
        """
        # Prioritize Google Books image_url if available
        if self.image_url:
            return self.image_url
        
        # Fall back to Open Library cover_id
        if not self.cover_id:
            return None
        return f"{OPEN_LIBRARY_COVERS_URL}/id/{self.cover_id}-{size}.jpg"


async def search_open_library(query: str, max_results: int = 5) -> List[BookMetadata]:
    """
    Search Open Library API asynchronously with retry logic and extended timeout

    Args:
        query: Search query (title or title+author)
        max_results: Maximum results to return

    Returns:
        List of BookMetadata objects
    """
    # Validate and clean query
    if not query or not query.strip():
        logger.warning("Empty query provided to Open Library search")
        return []

    query = query.strip()
    
    # Retry logic with exponential backoff
    max_retries = 3
    retry_delay = 1  # Start with 1 second

    for attempt in range(max_retries):
        try:
            # Build search query - try to get better results
            params = {
                "q": query,
                "limit": min(max_results * 2, 100),  # Get more results, filter after
                "fields": "title,author_name,first_publish_year,isbn,isbn_10,cover_id,has_fulltext,subject_type,subject",
            }

            logger.debug(f"Searching Open Library for: {query} (attempt {attempt + 1}/{max_retries})")

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    OPEN_LIBRARY_API_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=20),  # Extended timeout from 10s to 20s
                ) as response:
                    if response.status == 400:
                        error_text = await response.text()
                        logger.error(
                            f"Open Library API returned 400 Bad Request: {error_text}"
                        )
                        return []

                    if response.status == 429:
                        logger.warning(
                            f"Open Library API rate limited (attempt {attempt + 1}/{max_retries}) - Retrying..."
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        continue

                    if response.status != 200:
                        error_text = await response.text()
                        logger.warning(
                            f"Open Library API returned status {response.status} (attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        continue

                    data = await response.json()
                    docs = data.get("docs", [])

                    logger.debug(f"Open Library returned {len(docs)} results before filtering")

                    results = []
                    for doc in docs:
                        try:
                            # Skip if no title
                            if "title" not in doc:
                                continue

                            # Skip if no ISBN (usually means no digital version)
                            if not doc.get("isbn") and not doc.get("isbn_10"):
                                continue

                            # Check for digital availability
                            has_fulltext = doc.get("has_fulltext", False)
                            subjects = doc.get("subject", [])
                            subjects_str = " ".join(subjects).lower() if subjects else ""

                            # Skip if doesn't look like it has digital versions
                            if not has_fulltext and not any(
                                keyword in subjects_str
                                for keyword in [
                                    "ebook",
                                    "audiobook",
                                    "fiction",
                                    "novel",
                                    "fantasy",
                                    "science fiction",
                                    "mystery",
                                    "romance",
                                    "biography",
                                    "memoir",
                                ]
                            ):
                                continue

                            metadata = BookMetadata(
                                title=doc.get("title", "Unknown"),
                                authors=[
                                    author if isinstance(author, str) else author.get("name", "Unknown")
                                    for author in doc.get("author_name", [])
                                ]
                                or ["Unknown"],
                                first_publish_year=doc.get("first_publish_year"),
                                isbn_10=_get_first_isbn(doc.get("isbn_10", [])),
                                isbn_13=_get_first_isbn(doc.get("isbn", [])),
                                cover_id=doc.get("cover_id"),
                                description="",  # Open Library search doesn't include descriptions
                                has_ebook=has_fulltext or "ebook" in subjects_str,
                                has_audiobook="audiobook" in subjects_str,
                            )
                            results.append(metadata)

                            # Stop after getting enough good results
                            if len(results) >= max_results:
                                break

                        except Exception as e:
                            logger.warning(f"Error parsing Open Library result: {e}")
                            continue

                    logger.info(f"Found {len(results)} books on Open Library for: {query}")
                    return results

        except asyncio.TimeoutError:
            logger.warning(f"Open Library API timeout (attempt {attempt + 1}/{max_retries}) - Retrying...")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            continue
        except aiohttp.ClientSSLError as e:
            logger.error(f"Open Library API SSL error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            continue
        except aiohttp.ClientError as e:
            logger.warning(f"Open Library API connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            continue
        except Exception as e:
            logger.error(f"Unexpected error searching Open Library (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            continue

    logger.error(f"Open Library search failed for '{query}' after {max_retries} attempts")
    return []


def _get_first_isbn(isbn_list: List[str]) -> Optional[str]:
    """Get first ISBN from list"""
    if isbn_list and len(isbn_list) > 0:
        return isbn_list[0]
    return None
