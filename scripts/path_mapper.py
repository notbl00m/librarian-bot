"""
Path Mapper - Handle cross-server path translation
Translates between seedbox and unraid paths for distributed setup
"""

import logging
from typing import Optional, Dict
from pathlib import Path
import paramiko

from config import Config

logger = logging.getLogger(__name__)


class PathMapper:
    """Maps paths between seedbox and unraid servers"""

    def __init__(self):
        """Initialize path mapper"""
        self.seedbox_ssh = None
        self.enabled = Config.ENABLE_PATH_MAPPING
        self.mappings = Config.PATH_MAPPINGS

    def map_path(
        self, path: str, direction: str = "seedbox_to_unraid"
    ) -> str:
        """
        Map path from seedbox to unraid or vice versa

        Args:
            path: Path to map
            direction: "seedbox_to_unraid" or "unraid_to_seedbox"

        Returns:
            Mapped path
        """
        if not self.enabled or not self.mappings:
            return path

        if direction == "seedbox_to_unraid":
            return self._map_seedbox_to_unraid(path)
        elif direction == "unraid_to_seedbox":
            return self._map_unraid_to_seedbox(path)

        return path

    def _map_seedbox_to_unraid(self, path: str) -> str:
        """Map seedbox path to unraid path"""
        for seedbox_path, unraid_path in self.mappings.items():
            if path.startswith(seedbox_path):
                return path.replace(seedbox_path, unraid_path, 1)
        return path

    def _map_unraid_to_seedbox(self, path: str) -> str:
        """Map unraid path to seedbox path"""
        for seedbox_path, unraid_path in self.mappings.items():
            if path.startswith(unraid_path):
                return path.replace(unraid_path, seedbox_path, 1)
        return path

    def connect_seedbox(self) -> bool:
        """
        Connect to seedbox via SSH

        Returns:
            True if successful, False otherwise
        """
        if not Config.SEEDBOX_HOST or not Config.SEEDBOX_USER:
            logger.warning("Seedbox SSH credentials not configured")
            return False

        try:
            self.seedbox_ssh = paramiko.SSHClient()
            self.seedbox_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.seedbox_ssh.connect(
                hostname=Config.SEEDBOX_HOST,
                port=Config.SEEDBOX_SSH_PORT,
                username=Config.SEEDBOX_USER,
                password=Config.SEEDBOX_PASSWORD,
                timeout=10,
            )
            logger.info(f"Connected to seedbox: {Config.SEEDBOX_HOST}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to seedbox: {e}")
            return False

    def disconnect_seedbox(self):
        """Disconnect from seedbox"""
        if self.seedbox_ssh:
            self.seedbox_ssh.close()
            self.seedbox_ssh = None

    def file_exists_on_seedbox(self, path: str) -> bool:
        """
        Check if file exists on seedbox

        Args:
            path: File path on seedbox

        Returns:
            True if file exists, False otherwise
        """
        if not self.seedbox_ssh:
            if not self.connect_seedbox():
                return False

        try:
            stdin, stdout, stderr = self.seedbox_ssh.exec_command(f"test -f {path}")
            return stdout.channel.recv_exit_status() == 0
        except Exception as e:
            logger.error(f"Error checking file on seedbox: {e}")
            return False

    def copy_from_seedbox(
        self, seedbox_path: str, local_path: str, use_sftp: bool = True
    ) -> bool:
        """
        Copy file from seedbox to local unraid

        Args:
            seedbox_path: Path on seedbox
            local_path: Path on unraid
            use_sftp: Use SFTP (preferred) or SCP

        Returns:
            True if successful, False otherwise
        """
        if not self.seedbox_ssh:
            if not self.connect_seedbox():
                return False

        try:
            if use_sftp:
                sftp = self.seedbox_ssh.open_sftp()
                sftp.get(seedbox_path, local_path)
                sftp.close()
            else:
                # Use SCP via shell
                stdin, stdout, stderr = self.seedbox_ssh.exec_command(
                    f"cat {seedbox_path}"
                )
                content = stdout.read()
                Path(local_path).write_bytes(content)

            logger.info(f"Copied {seedbox_path} to {local_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to copy file from seedbox: {e}")
            return False

    def get_local_path(self, torrent_path: str) -> str:
        """
        Get local (unraid) path for a torrent downloaded on seedbox

        Args:
            torrent_path: Path as reported by qBittorrent (seedbox path)

        Returns:
            Mapped local path
        """
        if Config.SERVER_MODE == "local":
            # Same server, no mapping needed
            return torrent_path

        # Map seedbox path to unraid path
        local_path = self.map_path(torrent_path, "seedbox_to_unraid")
        logger.debug(f"Mapped {torrent_path} -> {local_path}")
        return local_path

    def get_remote_path(self, local_path: str) -> str:
        """
        Get remote (seedbox) path for local (unraid) path

        Args:
            local_path: Path on unraid

        Returns:
            Mapped seedbox path
        """
        if Config.SERVER_MODE == "local":
            # Same server, no mapping needed
            return local_path

        # Map unraid path to seedbox path
        remote_path = self.map_path(local_path, "unraid_to_seedbox")
        logger.debug(f"Mapped {local_path} -> {remote_path}")
        return remote_path


# Singleton instance
_mapper_instance: Optional[PathMapper] = None


def get_path_mapper() -> PathMapper:
    """Get or create path mapper instance"""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = PathMapper()
    return _mapper_instance


def map_torrent_path(torrent_path: str) -> str:
    """
    Convenience function to map torrent path

    Args:
        torrent_path: Path from qBittorrent

    Returns:
        Mapped local path
    """
    mapper = get_path_mapper()
    return mapper.get_local_path(torrent_path)
