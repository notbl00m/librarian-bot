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
        }

    def get_cover_url(self, size: str = "M") -> Optional[str]:
        """
        Get cover image URL

        Args:
            size: Image size - S (small), M (medium), L (large)

        Returns:
            Cover image URL or None
        """
        if not self.cover_id:
            return None
        return f"{OPEN_LIBRARY_COVERS_URL}/id/{self.cover_id}-{size}.jpg"


async def search_open_library(query: str, max_results: int = 5) -> List[BookMetadata]:
    """
    Search Open Library API asynchronously

    Args:
        query: Search query (title or title+author)
        max_results: Maximum results to return

    Returns:
        List of BookMetadata objects
    """
    try:
        # Validate and clean query
        if not query or not query.strip():
            logger.warning("Empty query provided to Open Library search")
            return []

        query = query.strip()

        # Build search query - try to get better results
        params = {
            "q": query,
            "limit": min(max_results * 2, 100),  # Get more results, filter after
            "fields": "title,author_name,first_publish_year,isbn,isbn_10,cover_id,has_fulltext,subject_type,subject",
        }

        logger.debug(f"Searching Open Library for: {query}")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                OPEN_LIBRARY_API_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 400:
                    error_text = await response.text()
                    logger.error(
                        f"Open Library API returned 400 Bad Request: {error_text}"
                    )
                    logger.debug(f"Query was: {query}")
                    return []

                if response.status == 429:
                    logger.warning(
                        "Open Library API rate limited - Try again later"
                    )
                    return []

                if response.status != 200:
                    error_text = await response.text()
                    logger.warning(
                        f"Open Library API returned status {response.status}: {error_text}"
                    )
                    return []

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
        logger.error(f"Open Library API timeout for query: {query}")
        return []
    except aiohttp.ClientSSLError as e:
        logger.error(f"Open Library API SSL error: {e}")
        return []
    except aiohttp.ClientError as e:
        logger.error(f"Open Library API connection error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error searching Open Library: {e}")
        return []


def _get_first_isbn(isbn_list: List[str]) -> Optional[str]:
    """Get first ISBN from list"""
    if isbn_list and len(isbn_list) > 0:
        return isbn_list[0]
    return None
