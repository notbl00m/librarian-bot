"""
Google Books API integration
Validate searches and get book metadata before searching Prowlarr
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import aiohttp
import asyncio
from urllib.parse import quote

from config import Config

logger = logging.getLogger(__name__)

GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"


@dataclass
class BookMetadata:
    """Book metadata from Google Books API"""
    title: str
    authors: List[str]
    published_date: str
    description: str
    isbn_10: Optional[str] = None
    isbn_13: Optional[str] = None
    categories: List[str] = None
    image_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "title": self.title,
            "authors": self.authors,
            "published_date": self.published_date,
            "description": self.description,
            "isbn_10": self.isbn_10,
            "isbn_13": self.isbn_13,
            "categories": self.categories or [],
            "image_url": self.image_url,
        }


async def search_google_books(query: str, max_results: int = 5) -> List[BookMetadata]:
    """
    Search Google Books API asynchronously

    Args:
        query: Search query
        max_results: Maximum results to return

    Returns:
        List of BookMetadata objects
    """
    try:
        # Validate and clean query
        if not query or not query.strip():
            logger.warning("Empty query provided to Google Books search")
            return []
        
        query = query.strip()
        
        params = {
            "q": query,
            "maxResults": min(max_results, 40),  # API max is 40
            "printType": "BOOKS",  # Only books, no magazines
        }

        # Add API key if available
        if Config.GOOGLE_BOOKS_API_KEY:
            params["key"] = Config.GOOGLE_BOOKS_API_KEY

        logger.debug(f"Searching Google Books for: {query}")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                GOOGLE_BOOKS_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 400:
                    error_text = await response.text()
                    logger.error(f"Google Books API returned 400 Bad Request: {error_text}")
                    logger.debug(f"Query was: {query}, params: {params}")
                    return []
                
                if response.status == 403:
                    logger.error("Google Books API returned 403 Forbidden - Invalid API key")
                    return []
                
                if response.status == 429:
                    logger.warning("Google Books API rate limited - Try again later")
                    return []
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.warning(f"Google Books API returned status {response.status}: {error_text}")
                    return []

                data = await response.json()
                items = data.get("items", [])

                results = []
                for item in items:
                    try:
                        volume_info = item.get("volumeInfo", {})
                        metadata = BookMetadata(
                            title=volume_info.get("title", "Unknown"),
                            authors=volume_info.get("authors", []),
                            published_date=volume_info.get("publishedDate", ""),
                            description=volume_info.get("description", ""),
                            isbn_10=_extract_isbn(volume_info, "ISBN_10"),
                            isbn_13=_extract_isbn(volume_info, "ISBN_13"),
                            categories=volume_info.get("categories", []),
                            image_url=volume_info.get("imageLinks", {}).get("thumbnail"),
                        )
                        results.append(metadata)
                    except Exception as e:
                        logger.warning(f"Error parsing Google Books result: {e}")
                        continue

                logger.info(f"Found {len(results)} books on Google Books for: {query}")
                return results

    except asyncio.TimeoutError:
        logger.error(f"Google Books API timeout for query: {query}")
        return []
    except aiohttp.ClientSSLError as e:
        logger.error(f"Google Books API SSL error: {e}")
        return []
    except aiohttp.ClientError as e:
        logger.error(f"Google Books API connection error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error searching Google Books: {e}")
        return []


def _extract_isbn(volume_info: dict, isbn_type: str) -> Optional[str]:
    """Extract ISBN from volume info"""
    identifiers = volume_info.get("industryIdentifiers", [])
    for identifier in identifiers:
        if identifier.get("type") == isbn_type:
            return identifier.get("identifier")
    return None


def is_audiobook_or_ebook(metadata: BookMetadata) -> bool:
    """
    Check if book is likely an audiobook or ebook based on categories

    Args:
        metadata: BookMetadata object

    Returns:
        True if likely audiobook/ebook, False if likely physical book only
    """
    categories = [cat.lower() for cat in (metadata.categories or [])]

    # Keywords that suggest ebook/audiobook availability
    audiobook_keywords = [
        "audiobook",
        "audio",
        "narrated",
        "fiction",
        "mystery",
        "romance",
        "science fiction",
        "fantasy",
        "biography",
        "memoir",
        "self-help",
        "non-fiction",
        "young adult",
    ]

    ebook_keywords = audiobook_keywords + ["ebook", "digital", "reference"]

    # Check if any category matches
    for category in categories:
        for keyword in ebook_keywords:
            if keyword in category:
                return True

    return False


def format_search_query(metadata: BookMetadata) -> str:
    """
    Format book metadata into a good Prowlarr search query

    Args:
        metadata: BookMetadata object

    Returns:
        Formatted search query
    """
    author = metadata.authors[0] if metadata.authors else ""
    title = metadata.title

    if author:
        return f"{title} {author}"
    return title
