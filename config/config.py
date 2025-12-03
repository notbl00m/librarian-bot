"""
Configuration module for Librarian Bot
Handles all environment variables and configuration settings
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Get the project root directory (parent of config folder)
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / "config" / ".env"

# Load environment variables from .env file
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()  # Try to load from current directory as fallback


class Config:
    """Main configuration class for the bot"""

    # Discord Configuration
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    ADMIN_ROLE: str = os.getenv("ADMIN_ROLE", "Admin")
    ADMIN_CHANNEL_ID: int = int(os.getenv("ADMIN_CHANNEL_ID", "1291129984353566820"))

    # Prowlarr Configuration
    PROWLARR_URL: str = os.getenv("PROWLARR_URL", "http://localhost:9696")
    PROWLARR_API_KEY: str = os.getenv("PROWLARR_API_KEY", "")
    PROWLARR_TIMEOUT: int = int(os.getenv("PROWLARR_TIMEOUT", "30"))

    # qBittorrent Configuration
    QBIT_URL: str = os.getenv("QBIT_URL", "http://localhost:8080")
    QBIT_USERNAME: str = os.getenv("QBIT_USERNAME", "admin")
    QBIT_PASSWORD: str = os.getenv("QBIT_PASSWORD", "adminPassword")
    QBIT_DOWNLOAD_PATH: str = os.getenv("QBIT_DOWNLOAD_PATH", "./downloads")
    QBIT_TIMEOUT: int = int(os.getenv("QBIT_TIMEOUT", "30"))
    QBIT_POLL_INTERVAL: int = int(os.getenv("QBIT_POLL_INTERVAL", "5"))  # seconds

    # Library Configuration
    LIBRARY_PATH: str = os.getenv("LIBRARY_PATH", "./library")
    GOOGLE_BOOKS_API_KEY: str = os.getenv("GOOGLE_BOOKS_API_KEY", "")
    DOWNLOAD_CATEGORY: str = os.getenv("DOWNLOAD_CATEGORY", "librarian-bot")

    # Path Mapping Configuration (for cross-server setups)
    ENABLE_PATH_MAPPING: bool = os.getenv("ENABLE_PATH_MAPPING", "false").lower() == "true"
    SERVER_MODE: str = os.getenv("SERVER_MODE", "local")  # local, remote, seedbox
    
    # Seedbox Configuration
    SEEDBOX_HOST: str = os.getenv("SEEDBOX_HOST", "localhost")
    SEEDBOX_USER: str = os.getenv("SEEDBOX_USER", "")
    SEEDBOX_PASSWORD: str = os.getenv("SEEDBOX_PASSWORD", "")
    SEEDBOX_SSH_PORT: int = int(os.getenv("SEEDBOX_SSH_PORT", "22"))
    SEEDBOX_DOWNLOAD_PATH: str = os.getenv("SEEDBOX_DOWNLOAD_PATH", "/mnt/downloads")
    
    # Unraid Configuration
    UNRAID_HOST: str = os.getenv("UNRAID_HOST", "localhost")
    UNRAID_USER: str = os.getenv("UNRAID_USER", "root")
    UNRAID_PASSWORD: str = os.getenv("UNRAID_PASSWORD", "")
    UNRAID_LIBRARY_PATH: str = os.getenv("UNRAID_LIBRARY_PATH", "/mnt/user/library")
    
    # AudiobookShelf Configuration
    AUDIOBOOKSHELF_URL: str = os.getenv("AUDIOBOOKSHELF_URL", "http://localhost:13378")
    AUDIOBOOKSHELF_API_KEY: str = os.getenv("AUDIOBOOKSHELF_API_KEY", "")
    AUDIOBOOKSHELF_LIBRARY_ID: str = os.getenv("AUDIOBOOKSHELF_LIBRARY_ID", "")
    AUDIOBOOKSHELF_TIMEOUT: int = int(os.getenv("AUDIOBOOKSHELF_TIMEOUT", "30"))
    
    # Path Mappings: parse from env variable
    _path_mappings_str: str = os.getenv("PATH_MAPPINGS", "")
    PATH_MAPPINGS: dict = {}  # Will be parsed in __post_init__

    # Bot Configuration
    COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!")
    MAX_RESULTS: int = int(os.getenv("MAX_RESULTS", "5"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "300"))  # 5 minutes
    APPROVAL_TIMEOUT: int = int(os.getenv("APPROVAL_TIMEOUT", "600"))  # 10 minutes
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Optional[str] = os.getenv("LOG_FILE", None)

    # Optional Settings
    ENABLE_HARDLINKS: bool = os.getenv("ENABLE_HARDLINKS", "true").lower() == "true"
    AUTO_APPROVE_MIN_SEEDERS: int = int(os.getenv("AUTO_APPROVE_MIN_SEEDERS", "0"))
    SUPPORTED_AUDIO_FORMATS: list = [".m4b", ".mp3", ".m4a", ".flac", ".wav", ".aac"]
    SUPPORTED_EBOOK_FORMATS: list = [".epub", ".mobi", ".pdf", ".azw3"]

    @classmethod
    def validate(cls) -> bool:
        """Validate all required configuration is present"""
        required_vars = [
            ("DISCORD_TOKEN", cls.DISCORD_TOKEN),
            ("PROWLARR_API_KEY", cls.PROWLARR_API_KEY),
            ("QBIT_PASSWORD", cls.QBIT_PASSWORD),
        ]

        missing_vars = [name for name, value in required_vars if not value]

        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        # Validate paths exist (only for local mode)
        if cls.SERVER_MODE == "local":
            paths_to_check = [
                # Note: QBIT_DOWNLOAD_PATH is now managed by qBittorrent category settings
                # and may not exist in the container, so we don't validate it
                ("LIBRARY_PATH", cls.LIBRARY_PATH),
            ]

            for name, path in paths_to_check:
                if not Path(path).exists():
                    raise ValueError(f"{name} does not exist: {path}")

        # Parse path mappings if enabled
        if cls.ENABLE_PATH_MAPPING and cls._path_mappings_str:
            cls._parse_path_mappings()

        return True

    @classmethod
    def _parse_path_mappings(cls):
        """Parse PATH_MAPPINGS environment variable into dict"""
        cls.PATH_MAPPINGS = {}
        if not cls._path_mappings_str:
            return
        
        # Format: /seedbox/path|/unraid/path;/another/seedbox|/another/unraid
        for mapping in cls._path_mappings_str.split(";"):
            mapping = mapping.strip()
            if "|" in mapping:
                seedbox_path, unraid_path = mapping.split("|", 1)
                cls.PATH_MAPPINGS[seedbox_path.strip()] = unraid_path.strip()

    @classmethod
    def map_path(cls, path: str, direction: str = "seedbox_to_unraid") -> str:
        """
        Map a path from seedbox to unraid or vice versa
        
        Args:
            path: Path to map
            direction: "seedbox_to_unraid" or "unraid_to_seedbox"
            
        Returns:
            Mapped path
        """
        if not cls.ENABLE_PATH_MAPPING or not cls.PATH_MAPPINGS:
            return path
        
        if direction == "seedbox_to_unraid":
            # Replace seedbox paths with unraid paths
            for seedbox_path, unraid_path in cls.PATH_MAPPINGS.items():
                if path.startswith(seedbox_path):
                    return path.replace(seedbox_path, unraid_path, 1)
        
        elif direction == "unraid_to_seedbox":
            # Replace unraid paths with seedbox paths
            for seedbox_path, unraid_path in cls.PATH_MAPPINGS.items():
                if path.startswith(unraid_path):
                    return path.replace(unraid_path, seedbox_path, 1)
        
        return path

    @classmethod
    def get_config_summary(cls) -> str:
        """Get a summary of current configuration (without sensitive data)"""
        return f"""
Librarian Bot Configuration Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Discord:
  - Admin Role: {cls.ADMIN_ROLE}

Prowlarr:
  - URL: {cls.PROWLARR_URL}
  - Timeout: {cls.PROWLARR_TIMEOUT}s

qBittorrent:
  - URL: {cls.QBIT_URL}
  - Download Path: {cls.QBIT_DOWNLOAD_PATH}
  - Poll Interval: {cls.QBIT_POLL_INTERVAL}s
  - Category: {cls.DOWNLOAD_CATEGORY}

Library:
  - Path: {cls.LIBRARY_PATH}
  - Hardlinks Enabled: {cls.ENABLE_HARDLINKS}

Bot:
  - Command Prefix: {cls.COMMAND_PREFIX}
  - Max Results: {cls.MAX_RESULTS}
  - Request Timeout: {cls.REQUEST_TIMEOUT}s
  - Log Level: {cls.LOG_LEVEL}
"""


# Alternative config for different environments
class DevelopmentConfig(Config):
    """Development environment configuration"""

    LOG_LEVEL = "DEBUG"
    PROWLARR_TIMEOUT = 60
    QBIT_TIMEOUT = 60


class ProductionConfig(Config):
    """Production environment configuration"""

    LOG_LEVEL = "INFO"


def get_config() -> type:
    """Get the appropriate config based on environment"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env == "production":
        return ProductionConfig
    return DevelopmentConfig
