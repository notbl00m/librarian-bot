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
    image_url: Optional[str] = None  # Cover/poster image
    thumbnail_url: Optional[str] = None  # Smaller thumbnail

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
    Search Google Books API asynchronously with retry logic

    Args:
        query: Search query (can be "title author" format for better results)
        max_results: Maximum results to return

    Returns:
        List of BookMetadata objects
    """
    # Validate and clean query
    if not query or not query.strip():
        logger.warning("Empty query provided to Google Books search")
        logger.debug("Returning empty list for empty query")
        return []
    
    query = query.strip()
    logger.debug(f"Google Books search initiated with query: {query}")
    
    # Parse query to extract title and author if both provided
    # Format: "Title Author" or just "Title"
    parts = query.rsplit(" ", 1)  # Split on last space
    search_query = query
    
    # Don't use complex structured queries - just use the full query as-is
    # Google Books is better at finding results with simple queries
    logger.debug(f"Final search query for API: {search_query}")
    
    # Retry logic with exponential backoff
    max_retries = 3
    retry_delay = 1  # Start with 1 second
    
    for attempt in range(max_retries):
        try:
            params = {
                "q": search_query,
                "maxResults": min(max_results, 40),  # API max is 40
                "printType": "BOOKS",  # Only books, no magazines
            }

            # Add API key if available
            if Config.GOOGLE_BOOKS_API_KEY:
                params["key"] = Config.GOOGLE_BOOKS_API_KEY

            logger.debug(f"Searching Google Books for: {query} (attempt {attempt + 1}/{max_retries})")

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    GOOGLE_BOOKS_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status == 400:
                        error_text = await response.text()
                        logger.error(f"Google Books API returned 400 Bad Request: {error_text}")
                        return []
                    
                    if response.status == 403:
                        logger.error("Google Books API returned 403 Forbidden - Invalid API key")
                        return []
                    
                    if response.status == 429:
                        logger.warning(f"Google Books API rate limited (attempt {attempt + 1}/{max_retries}) - Retrying...")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        continue
                    
                    if response.status == 503:
                        logger.warning(f"Google Books API unavailable (attempt {attempt + 1}/{max_retries}) - Retrying...")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        continue
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.warning(f"Google Books API returned status {response.status} (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        continue

                    data = await response.json()
                    items = data.get("items", [])
                    logger.debug(f"Google Books API returned {len(items)} items")

                    results = []
                    for idx, item in enumerate(items):
                        try:
                            volume_info = item.get("volumeInfo", {})
                            title = volume_info.get("title", "Unknown")
                            description = volume_info.get("description", "")
                            
                            # FILTER OUT support books (summaries, guides, analysis, etc.)
                            # Check title, description, AND authors for support book indicators
                            authors_list = volume_info.get("authors", [])
                            if _is_support_book(title, description, authors_list):
                                logger.debug(f"Filtered out support/summary book: {title} by {authors_list}")
                                continue
                            
                            # Extract cover images with enhancement
                            image_links = volume_info.get("imageLinks", {})
                            image_url = _get_best_cover_url(image_links)
                            
                            metadata = BookMetadata(
                                title=title,
                                authors=volume_info.get("authors", []),
                                published_date=volume_info.get("publishedDate", ""),
                                description=description,
                                isbn_10=_extract_isbn(volume_info, "ISBN_10"),
                                isbn_13=_extract_isbn(volume_info, "ISBN_13"),
                                categories=volume_info.get("categories", []),
                                image_url=image_url,
                                thumbnail_url=image_links.get("thumbnail"),
                            )
                            logger.debug(f"Added result {len(results)+1}: {title} by {', '.join(metadata.authors or ['Unknown'])}")
                            results.append(metadata)
                        except Exception as e:
                            logger.warning(f"Error parsing Google Books result: {e}")
                            logger.debug(f"Failed item index: {idx}")
                            continue

                    logger.info(f"Found {len(results)} books on Google Books for: {query} (filtered from {len(items)} raw results)")
                    return results

        except asyncio.TimeoutError:
            logger.warning(f"Google Books API timeout (attempt {attempt + 1}/{max_retries}) - Retrying...")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            continue
        except aiohttp.ClientSSLError as e:
            logger.error(f"Google Books API SSL error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            continue
        except aiohttp.ClientError as e:
            logger.warning(f"Google Books API connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            continue
        except Exception as e:
            logger.error(f"Unexpected error searching Google Books (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            continue
    
    logger.error(f"Google Books search failed for '{query}' after {max_retries} attempts")
    return []


def _get_best_cover_url(image_links: dict) -> Optional[str]:
    """
    Extract best quality cover URL from Google Books image links
    
    Returns highest quality available:
    1. extraLarge (highest quality)
    2. large
    3. medium
    4. small
    5. thumbnail (lowest quality)
    
    Then enhances thumbnail URLs by:
    - Replacing &zoom=1 with &zoom=0
    - Appending &fife=w800 for up to 800px width
    - Converting http:// to https://
    """
    if not image_links:
        return None
    
    # Try to get best quality in order
    for size in ["extraLarge", "large", "medium", "small"]:
        if size in image_links:
            url = image_links[size]
            # Convert to https
            url = url.replace("http://", "https://")
            return url
    
    # Fallback to thumbnail with enhancement
    if "thumbnail" in image_links:
        url = image_links["thumbnail"]
        
        # Enhance thumbnail quality
        # Replace &zoom=1 with &zoom=0 for better quality
        url = url.replace("&zoom=1", "&zoom=0")
        # Request up to 800px width
        if "&fife=w" not in url:
            url += "&fife=w800"
        # Convert to https
        url = url.replace("http://", "https://")
        
        logger.debug(f"Enhanced thumbnail URL for better quality")
        return url
    
    return None


def _extract_isbn(volume_info: dict, isbn_type: str) -> Optional[str]:
    """Extract ISBN from volume info"""
    identifiers = volume_info.get("industryIdentifiers", [])
    for identifier in identifiers:
        if identifier.get("type") == isbn_type:
            return identifier.get("identifier")
    return None


def _is_support_book(title: str, description: str = "", authors: list = None) -> bool:
    """
    Determine if a book is a support/reference book (summary, guide, analysis, etc.)
    These are NOT actual books but study aids and should be excluded
    
    Args:
        title: Book title to check
        description: Book description to check (optional)
        authors: List of authors to check (optional)
    
    Returns:
        True if support book, False if actual book
    """
    # Check title, description, AND authors
    combined_text = (title + " " + description).lower()
    if authors:
        authors_text = " ".join(str(a).lower() for a in authors)
        combined_text += " " + authors_text
    
    # Keywords that indicate this is a support/reference book
    support_keywords = [
        "summary", "summaries", "sparknotes", "cliffsnotes", "cliff notes",
        "study guide", "study guides", "guide to", "guides to",
        "quick summary", "key ideas", "key takeaways", "key points",
        "analysis", "explained", "for dummies", "easy to understand",
        "discussion guide", "reader's guide", "bookrags",
        "chapter summary", "chapter summaries",
        "notes and questions", "study material",
        "overview of", "introduction to", "beginner's guide",
        "critical essays", "study notes", "study help",
        "quicklet", "instaread", "summary station", "getabstract",
        "blinkist", "scribd", "audible study guide"
    ]
    
    for keyword in support_keywords:
        if keyword in combined_text:
            return True
    
    return False


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
