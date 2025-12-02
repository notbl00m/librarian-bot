"""
Request message tracking
Maps user request messages to admin approval messages for bi-directional updates
"""

import json
import logging
import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

REQUEST_TRACKING_FILE = ".request_tracking.json"


class RequestTrackingDB:
    """Database to track user request messages and map them to admin approval messages"""

    def __init__(self, db_file: str = REQUEST_TRACKING_FILE):
        """
        Initialize request tracking database

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
                logger.error(f"Error loading request tracking database: {e}")
                return {}
        return {}

    def _save(self):
        """Save database to file"""
        try:
            os.makedirs(os.path.dirname(self.db_file) or ".", exist_ok=True)
            with open(self.db_file, 'w') as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving request tracking database: {e}")

    def add_request_message(
        self,
        user_message_id: int,
        user_id: int,
        channel_id: int,
        book_title: str,
        request_type: str,
    ) -> bool:
        """
        Add a user request message

        Args:
            user_message_id: ID of the user's request message
            user_id: Discord user ID
            channel_id: ID of the channel where message is
            book_title: Title of the book
            request_type: "ebook" or "audiobook"

        Returns:
            True if added successfully
        """
        try:
            self.data[str(user_message_id)] = {
                "user_message_id": user_message_id,
                "user_id": user_id,
                "channel_id": channel_id,
                "book_title": book_title,
                "request_type": request_type,
                "admin_message_id": None,
                "admin_channel_id": None,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
            }
            self._save()
            logger.info(f"Tracked request message: {user_message_id} for {book_title}")
            return True
        except Exception as e:
            logger.error(f"Error adding request message: {e}")
            return False

    def link_admin_message(
        self,
        user_message_id: int,
        admin_message_id: int,
        admin_channel_id: int,
    ) -> bool:
        """
        Link an admin approval message to a user request message

        Args:
            user_message_id: ID of the user's request message
            admin_message_id: ID of the admin approval message
            admin_channel_id: ID of the admin channel

        Returns:
            True if linked successfully
        """
        try:
            key = str(user_message_id)
            if key in self.data:
                self.data[key]["admin_message_id"] = admin_message_id
                self.data[key]["admin_channel_id"] = admin_channel_id
                self._save()
                logger.info(f"Linked user message {user_message_id} to admin message {admin_message_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error linking admin message: {e}")
            return False

    def get_request_by_user_message(self, user_message_id: int) -> Optional[Dict]:
        """
        Get request info by user message ID

        Args:
            user_message_id: ID of the user's request message

        Returns:
            Request data dict or None
        """
        key = str(user_message_id)
        return self.data.get(key)

    def get_request_by_admin_message(self, admin_message_id: int) -> Optional[Dict]:
        """
        Get request info by admin message ID (reverse lookup)

        Args:
            admin_message_id: ID of the admin approval message

        Returns:
            Request data dict or None
        """
        for data in self.data.values():
            if data.get("admin_message_id") == admin_message_id:
                return data
        return None

    def update_status(self, user_message_id: int, status: str) -> bool:
        """
        Update request status

        Args:
            user_message_id: ID of the user's request message
            status: New status ("pending", "approved", "denied", "completed")

        Returns:
            True if updated successfully
        """
        try:
            key = str(user_message_id)
            if key in self.data:
                self.data[key]["status"] = status
                self.data[key]["updated_at"] = datetime.now().isoformat()
                self._save()
                logger.info(f"Updated request {user_message_id} status to {status}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            return False

    def get_all_pending_requests_for_user(self, user_id: int) -> Dict[str, Dict]:
        """
        Get all pending requests for a user

        Args:
            user_id: Discord user ID

        Returns:
            Dict of user_message_id -> request data
        """
        return {
            key: data for key, data in self.data.items()
            if data.get("user_id") == user_id and data.get("status") == "pending"
        }
