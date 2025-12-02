"""
Persistent storage for pending approval requests
Handles storing and retrieving approval data across bot restarts
"""

import json
import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Database file in data/ folder
import os
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
PENDING_APPROVALS_FILE = str(PROJECT_ROOT / "data" / ".pending_approvals.json")


class PendingApprovalsDB:
    """Database to store pending approval requests persistently"""

    def __init__(self, db_file: str = PENDING_APPROVALS_FILE):
        """
        Initialize pending approvals database

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
                logger.error(f"Error loading pending approvals database: {e}")
                return {}
        return {}

    def _save(self):
        """Save database to file"""
        try:
            os.makedirs(os.path.dirname(self.db_file) or ".", exist_ok=True)
            with open(self.db_file, 'w') as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving pending approvals database: {e}")

    def add_approval(
        self,
        approval_id: str,
        user_id: int,
        book_title: str,
        request_type: str,
        torrent_results: list,
        selected_torrent: dict,
        message_id: int,
        channel_id: int,
        user_message_id: int = None,
        user_channel_id: int = None,
    ) -> bool:
        """
        Add a new pending approval request

        Args:
            approval_id: Unique ID for this approval
            user_id: Discord user ID who requested
            book_title: Title of the book
            request_type: "ebook" or "audiobook"
            torrent_results: List of torrent search results
            selected_torrent: The selected/best torrent result
            message_id: ID of the approval message in admin channel
            channel_id: ID of the admin channel
            user_message_id: ID of the user's message (for status updates)
            user_channel_id: ID of the channel where user message is (DM or channel)

        Returns:
            True if added successfully
        """
        try:
            self.data[approval_id] = {
                "user_id": user_id,
                "book_title": book_title,
                "request_type": request_type,
                "torrent_results": torrent_results,
                "selected_torrent": selected_torrent,
                "message_id": message_id,
                "channel_id": channel_id,
                "user_message_id": user_message_id,
                "user_channel_id": user_channel_id,
                "status": "pending",
                "created_at": datetime.now().isoformat(),
            }
            self._save()
            logger.info(f"Added pending approval: {approval_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding approval: {e}")
            return False

    def get_approval(self, approval_id: str) -> Optional[Dict]:
        """
        Get a pending approval by ID

        Args:
            approval_id: Unique ID of the approval

        Returns:
            Approval data dict or None if not found
        """
        return self.data.get(approval_id)

    def update_approval(self, approval_id: str, status: str, result: dict = None) -> bool:
        """
        Update approval status

        Args:
            approval_id: Unique ID of the approval
            status: New status ("approved", "denied", "completed")
            result: Optional result data

        Returns:
            True if updated successfully
        """
        try:
            if approval_id in self.data:
                self.data[approval_id]["status"] = status
                if result:
                    self.data[approval_id]["result"] = result
                self.data[approval_id]["updated_at"] = datetime.now().isoformat()
                self._save()
                logger.info(f"Updated approval {approval_id} status: {status}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating approval: {e}")
            return False

    def remove_approval(self, approval_id: str) -> bool:
        """
        Remove a completed approval

        Args:
            approval_id: Unique ID of the approval

        Returns:
            True if removed successfully
        """
        try:
            if approval_id in self.data:
                del self.data[approval_id]
                self._save()
                logger.info(f"Removed approval: {approval_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing approval: {e}")
            return False

    def get_pending_approvals(self) -> Dict[str, Dict]:
        """
        Get all pending approvals

        Returns:
            Dict of approval_id -> approval data
        """
        return {
            aid: data for aid, data in self.data.items()
            if data.get("status") == "pending"
        }
    
    def get_all_approvals(self) -> Dict[str, Dict]:
        """
        Get all approvals (regardless of status)

        Returns:
            Dict of approval_id -> approval data
        """
        return self.data.copy()

    def get_by_message_id(self, message_id: int) -> Optional[Dict]:
        """
        Find approval by admin channel message ID

        Args:
            message_id: Discord message ID in admin channel

        Returns:
            Approval data or None
        """
        for data in self.data.values():
            if data.get("message_id") == message_id:
                return data
        return None

    def get_by_user_message_id(self, user_message_id: int) -> Optional[Dict]:
        """
        Find approval by user message ID (reverse lookup)

        Args:
            user_message_id: Discord message ID of user's request message

        Returns:
            Approval data or None
        """
        for approval_id, data in self.data.items():
            if data.get("user_message_id") == user_message_id:
                return approval_id, data
        return None

    def get_by_user_id(self, user_id: int) -> Dict[str, Dict]:
        """
        Get all approvals for a user

        Args:
            user_id: Discord user ID

        Returns:
            Dict of approval_id -> approval data
        """
        return {
            aid: data for aid, data in self.data.items()
            if data.get("user_id") == user_id
        }
