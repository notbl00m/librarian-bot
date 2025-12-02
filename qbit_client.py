"""
qBittorrent API integration module
Handles torrent downloading, monitoring, and management
"""

import asyncio
import logging
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import qbittorrentapi

from config import Config

logger = logging.getLogger(__name__)


class TorrentState(Enum):
    """Torrent state enumeration"""

    DOWNLOADING = "downloading"
    SEEDING = "seeding"
    COMPLETED = "completed"
    PAUSED = "paused"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class TorrentInfo:
    """Data class representing torrent information"""

    hash: str
    name: str
    state: TorrentState
    progress: float
    size: int
    downloaded: int
    uploaded: int
    ratio: float
    download_speed: int
    upload_speed: int
    num_seeds: int
    num_complete: int
    num_incomplete: int
    added_on: str
    completion_on: Optional[str] = None
    category: str = ""
    save_path: str = ""
    magnet_uri: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "hash": self.hash,
            "name": self.name,
            "state": self.state.value,
            "progress": self.progress,
            "size": self.size,
            "downloaded": self.downloaded,
            "uploaded": self.uploaded,
            "ratio": self.ratio,
            "download_speed": self.download_speed,
            "upload_speed": self.upload_speed,
            "category": self.category,
            "save_path": self.save_path,
        }


class QBittorrentClient:
    """qBittorrent WebAPI client"""

    def __init__(self):
        """Initialize qBittorrent client"""
        self.url = Config.QBIT_URL
        self.username = Config.QBIT_USERNAME
        self.password = Config.QBIT_PASSWORD
        self.download_path = Config.QBIT_DOWNLOAD_PATH
        self.category = Config.DOWNLOAD_CATEGORY
        self.client: Optional[qbittorrentapi.Client] = None

    def connect(self) -> bool:
        """
        Connect to qBittorrent

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client = qbittorrentapi.Client(
                host=self.url, username=self.username, password=self.password
            )
            # Test connection
            self.client.auth_log_in()
            logger.info(f"Successfully connected to qBittorrent at {self.url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to qBittorrent: {e}")
            self.client = None
            return False

    def disconnect(self):
        """Disconnect from qBittorrent"""
        if self.client:
            try:
                self.client.auth_log_out()
            except Exception as e:
                logger.warning(f"Error logging out from qBittorrent: {e}")
            self.client = None

    def _ensure_connected(self):
        """Ensure client is connected, raise if not"""
        if not self.client:
            if not self.connect():
                raise RuntimeError("Failed to connect to qBittorrent")

    async def health_check(self) -> bool:
        """
        Check if qBittorrent is accessible

        Returns:
            True if healthy, False otherwise
        """
        try:
            self.connect()
            app_info = self.client.app.web_api_version
            logger.debug(f"qBittorrent API version: {app_info}")
            return True
        except Exception as e:
            logger.error(f"qBittorrent health check failed: {e}")
            return False

    def add_torrent(
        self,
        torrent_input: str,
        use_auto_torrent_management: bool = False,
        is_paused: bool = False,
    ) -> Optional[str]:
        """
        Add a torrent to qBittorrent

        Args:
            torrent_input: Magnet link or path to .torrent file
            use_auto_torrent_management: Let qBit manage download location
            is_paused: Add torrent in paused state

        Returns:
            Torrent hash if successful, None if failed
        """
        try:
            self._ensure_connected()

            logger.debug(f"Adding torrent: {torrent_input[:50]}...")

            self.client.torrents_add(
                urls=torrent_input,
                category=self.category,
                use_auto_torrent_management=use_auto_torrent_management,
                is_paused=is_paused,
                save_path=self.download_path,
            )

            # Get the newly added torrent hash
            torrents = self.client.torrents_info()
            for torrent in torrents:
                if (
                    torrent.magnet_uri == torrent_input
                    or torrent_input in str(torrent.name)
                ):
                    logger.info(f"Successfully added torrent: {torrent.name}")
                    return torrent.hash

            logger.warning("Could not verify added torrent")
            return None

        except Exception as e:
            logger.error(f"Failed to add torrent: {e}")
            return None

    def get_torrent(self, torrent_hash: str) -> Optional[TorrentInfo]:
        """
        Get information about a specific torrent

        Args:
            torrent_hash: Torrent hash

        Returns:
            TorrentInfo object if found, None otherwise
        """
        try:
            self._ensure_connected()

            torrent = self.client.torrents_info(torrent_hashes=torrent_hash)
            if not torrent:
                return None

            return self._parse_torrent(torrent[0])

        except Exception as e:
            logger.error(f"Failed to get torrent info: {e}")
            return None

    def get_all_torrents(self) -> List[TorrentInfo]:
        """
        Get information about all torrents

        Returns:
            List of TorrentInfo objects
        """
        try:
            self._ensure_connected()

            torrents = self.client.torrents_info()
            return [self._parse_torrent(t) for t in torrents]

        except Exception as e:
            logger.error(f"Failed to get torrents list: {e}")
            return []

    def get_torrents_in_category(self, category: str = None) -> List[TorrentInfo]:
        """
        Get all torrents in a specific category

        Args:
            category: Category name (defaults to bot's category)

        Returns:
            List of TorrentInfo objects
        """
        if category is None:
            category = self.category

        try:
            self._ensure_connected()

            torrents = self.client.torrents_info()
            filtered = [
                self._parse_torrent(t) for t in torrents if t.category == category
            ]
            return filtered

        except Exception as e:
            logger.error(f"Failed to get torrents in category {category}: {e}")
            return []

    def _parse_torrent(self, torrent) -> TorrentInfo:
        """
        Parse qBittorrent torrent object to TorrentInfo

        Args:
            torrent: qBittorrentapi torrent object

        Returns:
            TorrentInfo object
        """
        # Map qBit states to our state enum
        state_map = {
            "downloading": TorrentState.DOWNLOADING,
            "uploading": TorrentState.SEEDING,
            "queuedForSeeding": TorrentState.SEEDING,
            "queuedForChecking": TorrentState.DOWNLOADING,
            "checking": TorrentState.DOWNLOADING,
            "missingFiles": TorrentState.ERROR,
            "paused": TorrentState.PAUSED,
            "forcedUP": TorrentState.SEEDING,
            "forcedDL": TorrentState.DOWNLOADING,
            "stalledUP": TorrentState.SEEDING,
            "stalledDL": TorrentState.DOWNLOADING,
            "allocating": TorrentState.DOWNLOADING,
            "metaDL": TorrentState.DOWNLOADING,
        }

        state = state_map.get(torrent.state, TorrentState.UNKNOWN)

        # Determine completion date
        completion_on = None
        completion_time = getattr(torrent, 'completion_on', 0)
        if completion_time > 0:
            completion_on = datetime.fromtimestamp(completion_time).isoformat()

        # Get attributes safely (different qBit API versions might use different names)
        added_time = getattr(torrent, 'added_on', 0)
        
        return TorrentInfo(
            hash=torrent.hash,
            name=torrent.name,
            state=state,
            progress=torrent.progress,
            size=getattr(torrent, 'total_size', getattr(torrent, 'size', 0)),
            downloaded=getattr(torrent, 'downloaded', 0),
            uploaded=getattr(torrent, 'uploaded', 0),
            ratio=getattr(torrent, 'ratio', 0.0),
            download_speed=getattr(torrent, 'dlspeed', getattr(torrent, 'dl_speed', 0)),
            upload_speed=getattr(torrent, 'upspeed', getattr(torrent, 'up_speed', 0)),
            num_seeds=getattr(torrent, 'num_seeds', 0),
            num_complete=getattr(torrent, 'num_complete', 0),
            num_incomplete=getattr(torrent, 'num_incomplete', getattr(torrent, 'num_leechs', 0)),
            added_on=datetime.fromtimestamp(added_time).isoformat() if added_time > 0 else None,
            completion_on=completion_on,
            category=getattr(torrent, 'category', ''),
            save_path=getattr(torrent, 'save_path', ''),
            magnet_uri=getattr(torrent, 'magnet_uri', ''),
        )

    def pause_torrent(self, torrent_hash: str) -> bool:
        """
        Pause a torrent

        Args:
            torrent_hash: Torrent hash

        Returns:
            True if successful, False otherwise
        """
        try:
            self._ensure_connected()
            self.client.torrents_pause(torrent_hashes=torrent_hash)
            logger.info(f"Paused torrent: {torrent_hash}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause torrent: {e}")
            return False

    def resume_torrent(self, torrent_hash: str) -> bool:
        """
        Resume a torrent

        Args:
            torrent_hash: Torrent hash

        Returns:
            True if successful, False otherwise
        """
        try:
            self._ensure_connected()
            self.client.torrents_resume(torrent_hashes=torrent_hash)
            logger.info(f"Resumed torrent: {torrent_hash}")
            return True
        except Exception as e:
            logger.error(f"Failed to resume torrent: {e}")
            return False

    def remove_torrent(
        self, torrent_hash: str, delete_files: bool = False
    ) -> bool:
        """
        Remove a torrent

        Args:
            torrent_hash: Torrent hash
            delete_files: Also delete downloaded files

        Returns:
            True if successful, False otherwise
        """
        try:
            self._ensure_connected()
            self.client.torrents_delete(
                torrent_hashes=torrent_hash, delete_files=delete_files
            )
            logger.info(f"Removed torrent: {torrent_hash}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove torrent: {e}")
            return False

    async def wait_for_completion(
        self,
        torrent_hash: str,
        poll_interval: int = None,
        timeout: int = None,
        on_progress: Optional[Callable[[TorrentInfo], None]] = None,
    ) -> Optional[TorrentInfo]:
        """
        Wait for a torrent to complete

        Args:
            torrent_hash: Torrent hash
            poll_interval: How often to check (seconds, defaults to Config)
            timeout: Maximum time to wait (seconds, None = infinite)
            on_progress: Callback function called on each progress update

        Returns:
            TorrentInfo when complete, None if timeout/error
        """
        if poll_interval is None:
            poll_interval = Config.QBIT_POLL_INTERVAL

        elapsed = 0

        while True:
            # Check timeout
            if timeout and elapsed >= timeout:
                logger.warning(f"Timeout waiting for torrent: {torrent_hash}")
                return None

            # Get torrent status
            torrent_info = self.get_torrent(torrent_hash)
            if not torrent_info:
                logger.error(f"Torrent not found: {torrent_hash}")
                return None

            # Call progress callback
            if on_progress:
                on_progress(torrent_info)

            # Check if complete
            if torrent_info.progress >= 1.0:
                logger.info(f"Torrent completed: {torrent_info.name}")
                return torrent_info

            # Sleep before next poll
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

    async def monitor_torrents(
        self,
        category: str = None,
        poll_interval: int = None,
        on_completed: Optional[
            Callable[[TorrentInfo], None]
        ] = None,  # Can be async or sync
    ):
        """
        Monitor torrents in a category for completion

        Args:
            category: Category to monitor (defaults to bot's category)
            poll_interval: How often to check (seconds)
            on_completed: Callback function when torrent completes
        """
        if category is None:
            category = self.category
        if poll_interval is None:
            poll_interval = Config.QBIT_POLL_INTERVAL

        completed_hashes = set()

        logger.info(f"Starting torrent monitor for category: {category}")

        while True:
            try:
                torrents = self.get_torrents_in_category(category)

                for torrent in torrents:
                    # Check if torrent completed and we haven't processed it yet
                    if (
                        torrent.progress >= 1.0
                        and torrent.hash not in completed_hashes
                    ):
                        logger.info(f"Torrent completed: {torrent.name}")
                        completed_hashes.add(torrent.hash)

                        if on_completed:
                            # Handle both sync and async callbacks
                            result = on_completed(torrent)
                            if hasattr(result, "__await__"):
                                await result

                await asyncio.sleep(poll_interval)

            except Exception as e:
                logger.error(f"Error in torrent monitor: {e}")
                await asyncio.sleep(poll_interval)

    def get_app_preferences(self) -> Dict[str, Any]:
        """
        Get qBittorrent application preferences

        Returns:
            Dict of preferences
        """
        try:
            self._ensure_connected()
            return self.client.app.preferences
        except Exception as e:
            logger.error(f"Failed to get app preferences: {e}")
            return {}

    def get_transfer_info(self) -> Dict[str, Any]:
        """
        Get current transfer information (speeds, etc.)

        Returns:
            Dict with transfer stats
        """
        try:
            self._ensure_connected()
            transfer_info = self.client.transfer.info
            return {
                "dl_info_speed": transfer_info.dl_info_speed,
                "up_info_speed": transfer_info.up_info_speed,
                "dl_info_data": transfer_info.dl_info_data,
                "up_info_data": transfer_info.up_info_data,
                "connection_status": transfer_info.connection_status,
            }
        except Exception as e:
            logger.error(f"Failed to get transfer info: {e}")
            return {}


# Singleton-like functions for easy usage
_client_instance: Optional[QBittorrentClient] = None


def get_qbit_client() -> QBittorrentClient:
    """Get or create qBittorrent client instance"""
    global _client_instance
    if _client_instance is None:
        _client_instance = QBittorrentClient()
    return _client_instance


async def test_qbit_connection() -> bool:
    """Test connection to qBittorrent"""
    client = get_qbit_client()
    return await client.health_check()


async def add_torrent_and_wait(
    torrent_input: str,
    timeout: int = 3600,
    on_progress: Optional[Callable[[TorrentInfo], None]] = None,
) -> Optional[TorrentInfo]:
    """
    Add a torrent and wait for completion in one call

    Args:
        torrent_input: Magnet link or torrent file path
        timeout: Maximum time to wait (seconds)
        on_progress: Progress callback

    Returns:
        TorrentInfo when complete, None if failed
    """
    client = get_qbit_client()
    if not client.connect():
        logger.error("Failed to connect to qBittorrent")
        return None

    torrent_hash = client.add_torrent(torrent_input, is_paused=False)
    if not torrent_hash:
        logger.error("Failed to add torrent")
        return None

    return await client.wait_for_completion(
        torrent_hash, timeout=timeout, on_progress=on_progress
    )
