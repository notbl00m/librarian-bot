#!/usr/bin/env python3
"""
MAM Download Organizer
Scans a mixed audiobook/ebook download folder and organizes files by author
using Google Books API for metadata, creating hardlinks to preserve seeding.

REQUIREMENTS:
    pip install requests colorama
"""

import os
import re
import json
import time
import hashlib
import requests
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import logging
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Color support for Windows and Unix
try:
    from colorama import init, Fore, Style
    init(autoreset=True)  # Auto-reset colors after each print
    COLORS_ENABLED = True
except ImportError:
    # Fallback if colorama not installed
    COLORS_ENABLED = False
    class Fore:
        GREEN = RED = YELLOW = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""

# ============================================================================
# CONFIGURATION - Edit these paths
# ============================================================================
# WINDOWS USERS: Use one of these path formats:
#   - Raw strings: r"C:\Users\YourName\Downloads"
#   - Forward slashes: "C:/Users/YourName/Downloads"
# LINUX USERS: Use regular paths: "/home/username/downloads"
# ============================================================================

CONFIG = {
    # Source: Your downloads folder from qBittorrent
    "source_folder": os.getenv("QBIT_DOWNLOAD_PATH", "/home/bloomstreaming/downloads/completed/MAM"),
    
    # Destination: Your organized library folder
    "destination_folder": os.getenv("LIBRARY_PATH", "/home/bloomstreaming/downloads/completed/BLOOM-LIBRARY"),
    
    # Organizer directory (where script and its files live)
    "organizer_dir": os.getenv("ORGANIZER_REMOTE_PATH", "/home/bloomstreaming/downloads/completed/BLOOM-LIBRARY/[Organizer]"),
    
    # Database file to track processed items (prevents re-processing)
    "database_file": os.path.join(os.getenv("ORGANIZER_REMOTE_PATH", "/home/bloomstreaming/downloads/completed/BLOOM-LIBRARY/[Organizer]"), "organizer.db.json"),
    
    # Log file location
    "log_file": os.path.join(os.getenv("ORGANIZER_REMOTE_PATH", "/home/bloomstreaming/downloads/completed/BLOOM-LIBRARY/[Organizer]"), "organizer.log"),
    
    # Audiobook extensions
    "audiobook_extensions": [".m4b", ".m4a", ".mp3", ".opus", ".flac"],
    
    # Ebook extensions
    "ebook_extensions": [".epub", ".mobi", ".azw3", ".pdf", ".cbz", ".cbr"],
    
    # Google Books API settings
    "api_delay": 1.0,  # Delay between API calls (seconds)
    "api_timeout": 10,  # API request timeout (seconds)
    
    # Manual overrides: {"folder_name": {"author": "Author Name", "title": "Book Title"}}
    "manual_overrides": {}
}

# Create organizer directory if it doesn't exist
organizer_dir = CONFIG["organizer_dir"]
os.makedirs(organizer_dir, exist_ok=True)

# ============================================================================
# Setup Logging with Colors
# ============================================================================

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""
    
    def format(self, record):
        # Add colors based on log level
        if record.levelno == logging.INFO:
            if '[SUCCESS]' in record.msg:
                record.msg = f"{Fore.GREEN}{Style.BRIGHT}{record.msg}{Style.RESET_ALL}"
            elif '[WARNING]' in record.msg or 'WARNING' in record.levelname:
                record.msg = f"{Fore.YELLOW}{record.msg}{Style.RESET_ALL}"
        elif record.levelno == logging.WARNING:
            record.msg = f"{Fore.YELLOW}{record.msg}{Style.RESET_ALL}"
        elif record.levelno == logging.ERROR:
            record.msg = f"{Fore.RED}{Style.BRIGHT}{record.msg}{Style.RESET_ALL}"
        
        return super().format(record)

# Create handlers
console_handler = logging.StreamHandler(sys.stdout)
file_handler = logging.FileHandler(CONFIG["log_file"])

# Set formatters
log_format = '%(asctime)s - %(levelname)s - %(message)s'
console_handler.setFormatter(ColoredFormatter(log_format))
file_handler.setFormatter(logging.Formatter(log_format))  # No colors in file

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

# ============================================================================
# Database Management
# ============================================================================

class ProcessedDB:
    """Simple JSON database to track processed items"""
    
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.data = self._load()
    
    def _load(self) -> Dict:
        """Load database from file"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading database: {e}")
                return {}
        return {}
    
    def _save(self):
        """Save database to file"""
        try:
            with open(self.db_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving database: {e}")
    
    def is_processed(self, item_hash: str) -> bool:
        """Check if item has been processed"""
        return item_hash in self.data
    
    def mark_processed(self, item_hash: str, metadata: Dict):
        """Mark item as processed with metadata"""
        self.data[item_hash] = {
            "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "metadata": metadata
        }
        self._save()
    
    def get_item(self, item_hash: str) -> Optional[Dict]:
        """Get processed item metadata"""
        return self.data.get(item_hash)

# ============================================================================
# Utility Functions
# ============================================================================

def get_item_hash(path: str) -> str:
    """Generate a unique hash for a file/folder path"""
    return hashlib.md5(path.encode()).hexdigest()

def clean_filename(name: str) -> str:
    """Clean filename for safer filesystem operations"""
    # Remove/replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace multiple spaces with single space
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

def is_audiobook(path: Path) -> bool:
    """Determine if path contains audiobook files"""
    if path.is_file():
        return path.suffix.lower() in CONFIG["audiobook_extensions"]
    
    # Check if folder contains audio files
    for ext in CONFIG["audiobook_extensions"]:
        if list(path.glob(f"**/*{ext}")):
            return True
    return False

def is_ebook(path: Path) -> bool:
    """Determine if path is an ebook file"""
    if path.is_file():
        return path.suffix.lower() in CONFIG["ebook_extensions"]
    
    # Check if folder contains ebook files
    for ext in CONFIG["ebook_extensions"]:
        if list(path.glob(f"**/*{ext}")):
            return True
    return False

def extract_metadata_from_name(name: str) -> Dict[str, str]:
    """
    Try to extract author and title from filename/folder name
    Common patterns:
    - "Author Name - Book Title"
    - "Book Title - Author Name"
    - "Author Name - Series Name 01 - Book Title"
    """
    result = {"author": None, "title": None, "raw_name": name}
    
    # Remove common suffixes
    name = re.sub(r'\.(m4b|epub|mobi|mp3|pdf)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\[.*?\]', '', name)  # Remove [tags]
    name = re.sub(r'\(.*?\)', '', name)  # Remove (parentheses)
    
    # Try to split by dash
    if ' - ' in name:
        parts = [p.strip() for p in name.split(' - ')]
        if len(parts) >= 2:
            # Heuristic: shorter part is likely author, longer is title
            # But author usually comes first in MAM naming
            result["author"] = parts[0]
            result["title"] = parts[1] if len(parts) == 2 else ' - '.join(parts[1:])
    else:
        # Can't determine, use full name as title
        result["title"] = name
    
    return result

# ============================================================================
# Google Books API
# ============================================================================

def query_google_books(search_term: str) -> Optional[Dict]:
    """
    Query Google Books API for book metadata
    Returns: {"author": "Author Name", "title": "Book Title", "series": "Series Name"}
    """
    try:
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": search_term,
            "maxResults": 1
        }
        
        response = requests.get(url, params=params, timeout=CONFIG["api_timeout"])
        response.raise_for_status()
        
        data = response.json()
        
        if "items" not in data or len(data["items"]) == 0:
            logger.warning(f"No results found for: {search_term}")
            return None
        
        # Extract metadata from first result
        volume_info = data["items"][0]["volumeInfo"]
        
        metadata = {
            "author": volume_info.get("authors", ["Unknown Author"])[0],
            "title": volume_info.get("title", "Unknown Title"),
            "series": None,  # Google Books doesn't always have series info
            "published": volume_info.get("publishedDate"),
            "source": "google_books"
        }
        
        logger.info(f"Found: {metadata['author']} - {metadata['title']}")
        return metadata
        
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing API response: {e}")
        return None

def get_book_metadata(item_name: str, item_path: Path) -> Optional[Dict]:
    """
    Get book metadata using multiple strategies:
    1. Check manual overrides
    2. Parse filename for basic info
    3. Query Google Books API
    """
    
    # Strategy 1: Manual overrides
    if item_name in CONFIG["manual_overrides"]:
        logger.info(f"Using manual override for: {item_name}")
        metadata = CONFIG["manual_overrides"][item_name].copy()
        metadata["source"] = "manual_override"
        return metadata
    
    # Strategy 2: Extract from filename
    parsed = extract_metadata_from_name(item_name)
    
    # Strategy 3: Query API
    if parsed["author"] and parsed["title"]:
        search_term = f"{parsed['author']} {parsed['title']}"
    else:
        search_term = parsed["title"] or item_name
    
    logger.info(f"Searching API for: {search_term}")
    metadata = query_google_books(search_term)
    
    time.sleep(CONFIG["api_delay"])  # Rate limiting
    
    # Fallback to parsed data if API fails
    if not metadata:
        logger.warning(f"API failed, using parsed data for: {item_name}")
        metadata = {
            "author": parsed["author"] or "Unknown Author",
            "title": parsed["title"] or item_name,
            "series": None,
            "source": "filename_parse"
        }
    
    return metadata

# ============================================================================
# File Organization
# ============================================================================

def create_hardlinks(source_path: Path, dest_path: Path) -> bool:
    """
    Create hardlinks from source to destination
    Handles both files and directories
    """
    try:
        dest_path.mkdir(parents=True, exist_ok=True)
        
        if source_path.is_file():
            # Single file
            dest_file = dest_path / source_path.name
            if not dest_file.exists():
                os.link(source_path, dest_file)
                logger.info(f"Hardlinked: {source_path.name}")
            else:
                logger.info(f"Already exists: {dest_file.name}")
        else:
            # Directory - hardlink all files recursively
            for item in source_path.rglob('*'):
                if item.is_file():
                    relative_path = item.relative_to(source_path)
                    dest_file = dest_path / relative_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    if not dest_file.exists():
                        os.link(item, dest_file)
                        logger.debug(f"Hardlinked: {relative_path}")
                    else:
                        logger.debug(f"Already exists: {relative_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error creating hardlinks: {e}")
        return False

def organize_item(item_path: Path, db: ProcessedDB) -> bool:
    """
    Organize a single item from MAM downloads
    Returns True if successful, False otherwise
    """
    item_name = item_path.name
    item_hash = get_item_hash(str(item_path))
    
    # Check if already processed
    if db.is_processed(item_hash):
        logger.debug(f"Already processed: {item_name}")
        return True
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {item_name}")
    
    # Determine media type
    if not (is_audiobook(item_path) or is_ebook(item_path)):
        logger.info(f"Skipping (not a book): {item_name}")
        return False
    
    # Get metadata
    metadata = get_book_metadata(item_name, item_path)
    if not metadata:
        logger.error(f"Failed to get metadata for: {item_name}")
        return False
    
    # Clean names for filesystem
    author_clean = clean_filename(metadata["author"])
    title_clean = clean_filename(metadata["title"])
    
    # Build destination path: /library/Author Name/Book Title/
    dest_path = Path(CONFIG["destination_folder"]) / author_clean / title_clean
    
    logger.info(f"Destination: {dest_path}")
    
    # Create hardlinks
    success = create_hardlinks(item_path, dest_path)
    
    if success:
        # Mark as processed
        db.mark_processed(item_hash, {
            "source": str(item_path),
            "destination": str(dest_path),
            "metadata": metadata
        })
        logger.info(f"[SUCCESS] Successfully organized: {item_name}")
    else:
        logger.error(f"[FAILED] Failed to organize: {item_name}")
    
    return success

# ============================================================================
# Main Scanner
# ============================================================================

def scan_and_organize():
    """Main function to scan MAM folder and organize items"""
    
    logger.info("="*60)
    logger.info("MAM Download Organizer - Starting")
    logger.info("="*60)
    
    # Get paths from CONFIG
    source_folder = CONFIG["source_folder"]
    dest_folder = CONFIG["destination_folder"]
    
    # If paths look like Linux paths but we're on Windows, they need to be mapped
    # For now, just use them as-is and let Path handle it
    source_path = Path(source_folder)
    dest_path = Path(dest_folder)
    
    logger.info(f"Source: {source_path} (exists: {source_path.exists()})")
    logger.info(f"Destination: {dest_path}")
    
    if not source_path.exists():
        logger.error(f"Source folder does not exist: {source_path}")
        logger.error(f"Please check your QBIT_DOWNLOAD_PATH in .env")
        logger.error(f"If files are on a remote server, ensure they are mounted/mapped to this machine")
        return
    
    # Create destination folder if it doesn't exist
    try:
        dest_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Destination folder ready: {dest_path}")
    except Exception as e:
        logger.error(f"Could not create destination folder: {e}")
        return
    
    # Initialize database
    db = ProcessedDB(CONFIG["database_file"])
    
    # Get all items in source folder
    items = [item for item in source_path.iterdir() if item.is_file() or item.is_dir()]
    logger.info(f"Found {len(items)} items to check")
    
    # Process each item
    stats = {"success": 0, "failed": 0, "skipped": 0}
    
    for item in items:
        # Skip hidden files and common non-book items
        if item.name.startswith('.'):
            continue
        
        try:
            result = organize_item(item, db)
            if result:
                stats["success"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            logger.error(f"Unexpected error processing {item.name}: {e}")
            stats["failed"] += 1
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    logger.info(f"{Fore.GREEN}Successfully organized: {stats['success']}{Style.RESET_ALL}")
    if stats['skipped'] > 0:
        logger.info(f"{Fore.YELLOW}Skipped: {stats['skipped']}{Style.RESET_ALL}")
    else:
        logger.info(f"Skipped: {stats['skipped']}")
    if stats['failed'] > 0:
        logger.info(f"{Fore.RED}Failed: {stats['failed']}{Style.RESET_ALL}")
    else:
        logger.info(f"Failed: {stats['failed']}")
    logger.info("="*60)

# ============================================================================
# Entry Point
# ============================================================================

def validate_config():
    """Validate configuration before running"""
    errors = []
    
    # Check if paths are still default
    if CONFIG["source_folder"] == "/path/to/mam/downloads":
        errors.append("source_folder is not configured (still using default path)")
    
    if CONFIG["destination_folder"] == "/path/to/organized/library":
        errors.append("destination_folder is not configured (still using default path)")
    
    if CONFIG["database_file"] == "/path/to/mam_organizer.db.json":
        errors.append("database_file is not configured (still using default path)")
    
    if CONFIG["log_file"] == "/path/to/mam_organizer.log":
        errors.append("log_file is not configured (still using default path)")
    
    # Check if log_file and database_file are actual files (not directories)
    if not CONFIG["log_file"].endswith('.log'):
        errors.append(f"log_file must be a file path ending in .log, not a directory: {CONFIG['log_file']}")
    
    if not CONFIG["database_file"].endswith('.json'):
        errors.append(f"database_file must be a file path ending in .json, not a directory: {CONFIG['database_file']}")
    
    if errors:
        print("=" * 60)
        print(f"{Fore.RED}{Style.BRIGHT}CONFIGURATION ERRORS{Style.RESET_ALL}")
        print("=" * 60)
        for error in errors:
            print(f"{Fore.RED}[ERROR] {error}{Style.RESET_ALL}")
        print("=" * 60)
        print("\nPlease edit the CONFIG section at the top of the script.")
        print("\nFor Windows paths, use one of these formats:")
        print('  - Raw strings: r"C:\\Users\\Name\\Downloads"')
        print('  - Forward slashes: "C:/Users/Name/Downloads"')
        if not COLORS_ENABLED:
            print(f"\n{Fore.YELLOW}TIP: Install 'colorama' for colored output: pip install colorama{Style.RESET_ALL}")
        return False
    
    return True

if __name__ == "__main__":
    # Validate configuration first
    if not validate_config():
        exit(1)
    
    try:
        scan_and_organize()
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)