"""
AudiobookShelf API integration for library scanning

Provides functions to trigger library scans in AudiobookShelf
"""

import aiohttp
import asyncio
import logging
from typing import Optional
from config import Config

logger = logging.getLogger(__name__)


async def trigger_library_scan(library_id: Optional[str] = None) -> bool:
    """
    Trigger a library scan in AudiobookShelf
    
    Args:
        library_id: Library ID to scan (uses config default if not provided)
    
    Returns:
        True if successful, False otherwise
    """
    if not Config.AUDIOBOOKSHELF_API_KEY:
        logger.warning("AudiobookShelf API key not configured - skipping library scan")
        return False
    
    if not Config.AUDIOBOOKSHELF_URL:
        logger.warning("AudiobookShelf URL not configured - skipping library scan")
        return False
    
    lib_id = library_id or Config.AUDIOBOOKSHELF_LIBRARY_ID
    
    if not lib_id:
        logger.warning("AudiobookShelf Library ID not configured - skipping library scan")
        return False
    
    url = f"{Config.AUDIOBOOKSHELF_URL}/api/libraries/{lib_id}/scan"
    headers = {
        "Authorization": f"Bearer {Config.AUDIOBOOKSHELF_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        logger.debug(f"Triggering AudiobookShelf library scan for library: {lib_id}")
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=Config.AUDIOBOOKSHELF_TIMEOUT)) as session:
            async with session.post(url, headers=headers) as response:
                if response.status == 200:
                    logger.info(f"✅ Successfully triggered AudiobookShelf library scan for library: {lib_id}")
                    return True
                elif response.status == 401:
                    logger.error("AudiobookShelf: Invalid API key (401 Unauthorized)")
                    return False
                elif response.status == 404:
                    logger.error(f"AudiobookShelf: Library not found (404) - Library ID: {lib_id}")
                    return False
                else:
                    error_text = await response.text()
                    logger.warning(f"AudiobookShelf scan request failed with status {response.status}: {error_text}")
                    return False
    
    except asyncio.TimeoutError:
        logger.warning(f"AudiobookShelf library scan request timed out (timeout: {Config.AUDIOBOOKSHELF_TIMEOUT}s)")
        return False
    except aiohttp.ClientError as e:
        logger.warning(f"AudiobookShelf connection error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error triggering AudiobookShelf scan: {e}", exc_info=True)
        return False


async def get_library_status(library_id: Optional[str] = None) -> Optional[dict]:
    """
    Get the status of an AudiobookShelf library
    
    Args:
        library_id: Library ID to check (uses config default if not provided)
    
    Returns:
        Library info dict or None if request fails
    """
    if not Config.AUDIOBOOKSHELF_API_KEY or not Config.AUDIOBOOKSHELF_URL:
        return None
    
    lib_id = library_id or Config.AUDIOBOOKSHELF_LIBRARY_ID
    
    if not lib_id:
        return None
    
    url = f"{Config.AUDIOBOOKSHELF_URL}/api/libraries/{lib_id}"
    headers = {
        "Authorization": f"Bearer {Config.AUDIOBOOKSHELF_API_KEY}",
    }
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=Config.AUDIOBOOKSHELF_TIMEOUT)) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"AudiobookShelf: Failed to get library status (status: {response.status})")
                    return None
    
    except Exception as e:
        logger.warning(f"Error getting AudiobookShelf library status: {e}")
        return None


async def test_connection() -> bool:
    """
    Test connection to AudiobookShelf and verify authentication
    
    Returns:
        True if connected and authenticated, False otherwise
    """
    if not Config.AUDIOBOOKSHELF_API_KEY or not Config.AUDIOBOOKSHELF_URL:
        logger.info("⏭️  AudiobookShelf not configured - skipping connection test")
        return False
    
    if not Config.AUDIOBOOKSHELF_LIBRARY_ID:
        logger.warning("⚠️  AudiobookShelf library ID not configured")
        return False
    
    url = f"{Config.AUDIOBOOKSHELF_URL}/api/me"
    headers = {
        "Authorization": f"Bearer {Config.AUDIOBOOKSHELF_API_KEY}",
    }
    
    try:
        logger.info(f"🔗 Testing AudiobookShelf connection: {Config.AUDIOBOOKSHELF_URL}")
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=Config.AUDIOBOOKSHELF_TIMEOUT)) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    user_data = await response.json()
                    logger.info(f"✅ AudiobookShelf authenticated successfully (User: {user_data.get('username', 'Unknown')})")
                    return True
                elif response.status == 401:
                    logger.error("❌ AudiobookShelf authentication failed - Invalid API key")
                    return False
                else:
                    logger.error(f"❌ AudiobookShelf connection failed (status: {response.status})")
                    return False
    
    except asyncio.TimeoutError:
        logger.error(f"❌ AudiobookShelf connection timeout (timeout: {Config.AUDIOBOOKSHELF_TIMEOUT}s)")
        return False
    except aiohttp.ClientError as e:
        logger.error(f"❌ AudiobookShelf connection error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error testing AudiobookShelf connection: {e}")
        return False
