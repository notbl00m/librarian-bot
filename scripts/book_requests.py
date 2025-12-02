"""
Book request tracking
Maps ISBN/book titles to Discord messages so we can update them when downloads complete
"""

import json
import logging
import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Database file in data/ folder
import os
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
BOOK_REQUESTS_FILE = str(PROJECT_ROOT / "data" / ".book_requests.json")


class BookRequestsDB:
    """Database to track book requests and their corresponding Discord messages"""

    def __init__(self, db_file: str = BOOK_REQUESTS_FILE):
        """
        Initialize book requests database

        Args:
            db_file: Path to JSON database file
        """
        self.db_file = db_file
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load database from file"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading book requests database: {e}")
                return {}
        return {}

    def _save(self):
        """Save database to file"""
        try:
            os.makedirs(os.path.dirname(self.db_file) or ".", exist_ok=True)
            with open(self.db_file, 'w') as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving book requests database: {e}")

    def add_request(
        self,
        isbn: str,
        book_title: str,
        user_id: int,
        message_id: int,
        channel_id: int,
        request_type: str,
    ) -> bool:
        """
        Add a book request and its message for tracking

        Args:
            isbn: ISBN of the book
            book_title: Title of the book
            user_id: Discord user ID who requested
            message_id: ID of the user's request message
            channel_id: ID of the channel where the message is
            request_type: "ebook" or "audiobook"

        Returns:
            True if added successfully
        """
        try:
            # Use ISBN as primary key if available, otherwise use book title
            key = isbn if isbn else book_title.lower()

            self.data[key] = {
                "isbn": isbn,
                "book_title": book_title,
                "user_id": user_id,
                "message_id": message_id,
                "channel_id": channel_id,
                "request_type": request_type,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
            }
            self._save()
            logger.info(f"Added book request: {book_title} (ISBN: {isbn})")
            return True
        except Exception as e:
            logger.error(f"Error adding request: {e}")
            return False

    def get_request(self, isbn: str = None, book_title: str = None) -> Optional[Dict]:
        """
        Get a book request by ISBN or title

        Args:
            isbn: ISBN of the book
            book_title: Title of the book (used if ISBN not available)

        Returns:
            Request data dict or None if not found
        """
        if isbn and isbn in self.data:
            return self.data[isbn]

        if book_title:
            key = book_title.lower()
            if key in self.data:
                return self.data[key]

        return None

    def mark_complete(
        self, isbn: str = None, book_title: str = None, status: str = "completed"
    ) -> bool:
        """
        Mark a request as completed/found in library

        Args:
            isbn: ISBN of the book
            book_title: Title of the book
            status: New status ("completed", "found")

        Returns:
            True if updated successfully
        """
        try:
            key = None
            if isbn and isbn in self.data:
                key = isbn
            elif book_title:
                key = book_title.lower()
                if key not in self.data:
                    return False

            if key:
                self.data[key]["status"] = status
                self.data[key]["completed_at"] = datetime.now().isoformat()
                self._save()
                logger.info(f"Marked request complete: {self.data[key]['book_title']}")
                return True

            return False
        except Exception as e:
            logger.error(f"Error updating request: {e}")
            return False

    def get_pending_requests(self) -> Dict[str, Dict]:
        """
        Get all pending requests

        Returns:
            Dict of key -> request data
        """
        return {
            key: data for key, data in self.data.items()
            if data.get("status") == "pending"
        }

    def get_message_info(
        self, isbn: str = None, book_title: str = None
    ) -> Optional[Tuple[int, int]]:
        """
        Get Discord message info (message_id, channel_id) for a book

        Args:
            isbn: ISBN of the book
            book_title: Title of the book

        Returns:
            Tuple of (message_id, channel_id) or None
        """
        request = self.get_request(isbn, book_title)
        if request:
            return (request.get("message_id"), request.get("channel_id"))
        return None

    def remove_request(self, isbn: str = None, book_title: str = None) -> bool:
        """
        Remove a request from tracking

        Args:
            isbn: ISBN of the book
            book_title: Title of the book

        Returns:
            True if removed successfully
        """
        try:
            key = None
            if isbn and isbn in self.data:
                key = isbn
            elif book_title:
                key = book_title.lower()

            if key and key in self.data:
                del self.data[key]
                self._save()
                logger.info(f"Removed request: {book_title}")
                return True

            return False
        except Exception as e:
            logger.error(f"Error removing request: {e}")
            return False
