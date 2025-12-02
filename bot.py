"""
Librarian Bot - Main entry point
Discord bot for automated audiobook/ebook downloads and organization
"""

import os
import sys
import logging
import asyncio
from typing import Optional
import discord
from discord.ext import commands, tasks

from config import Config, get_config
from scripts.utils import get_timestamp
from scripts.prowlarr_api import test_prowlarr_connection
from scripts.qbit_client import get_qbit_client
from scripts.qbit_monitor import QBitMonitor
from scripts.audiobookshelf_api import test_connection as test_audiobookshelf
from scripts import library_organizer

# Setup logging
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

# Configure StreamHandler with UTF-8 encoding for Windows
for handler in logging.root.handlers:
    if isinstance(handler, logging.StreamHandler):
        handler.stream.reconfigure(encoding='utf-8')

# Add file logging if configured
if Config.LOG_FILE:
    file_handler = logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
    file_handler.setLevel(log_level)  # Use same log level as console
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)


class LibrarianBot(commands.Bot):
    """Discord bot for library management"""

    def __init__(self, *args, **kwargs):
        """Initialize bot"""
        super().__init__(*args, **kwargs)
        self.start_time = None
        self.config = get_config()
        self.qbit_monitor: Optional[QBitMonitor] = None

    async def setup_hook(self):
        """Setup hook - called before bot connects"""
        logger.info("Setting up bot...")

        # Load cogs
        try:
            await self.load_extension("scripts.discord_commands")
            logger.info("✅ Loaded discord_commands cog")
        except Exception as e:
            logger.error(f"❌ Failed to load discord_commands: {e}")

        # Initialize qBit monitor (pass self so it can notify cog)
        qbit_client = get_qbit_client()
        self.qbit_monitor = QBitMonitor(qbit_client, library_organizer, bot=self)
        
        # Update qbit_monitor with book_requests_db from the cog after a short delay
        # (gives the cog time to fully initialize)
        async def setup_book_requests_db():
            await asyncio.sleep(0.5)
            try:
                cog = self.get_cog('LibrarianCommands')
                if cog and hasattr(cog, 'book_requests_db'):
                    self.qbit_monitor.book_requests_db = cog.book_requests_db
                    logger.info("✅ Linked book_requests_db to qbit_monitor")
            except Exception as e:
                logger.warning(f"Could not link book_requests_db: {e}")
        
        asyncio.create_task(setup_book_requests_db())
        
        # Start background tasks
        self.monitor_torrents.start()
        logger.info("✅ Started background tasks")

    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f"✅ Bot logged in as {self.user}")
        logger.info(f"📋 Serving {len(self.guilds)} guild(s)")

        # Sync commands
        try:
            synced = await self.tree.sync()
            logger.info(f"✅ Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"❌ Failed to sync commands: {e}")

        # Print startup info
        print("\n" + "=" * 50)
        print("🤖 Librarian Bot Ready!")
        print("=" * 50)
        print(Config.get_config_summary())
        print("=" * 50 + "\n")

    async def on_error(self, event_method: str, *args, **kwargs):
        """Handle unhandled exceptions"""
        logger.exception(f"Unhandled exception in {event_method}:")
        await super().on_error(event_method, *args, **kwargs)

    @tasks.loop(minutes=5)
    async def monitor_torrents(self):
        """Monitor torrents for completion and trigger organization"""
        if not self.qbit_monitor:
            logger.warning("qBit monitor not initialized")
            return
            
        # Start the monitor (idempotent - won't restart if already running)
        if not self.qbit_monitor.monitoring:
            await self.qbit_monitor.start()
            logger.info("🔄 qBit monitor started")

    @monitor_torrents.before_loop
    async def before_monitor_torrents(self):
        """Wait until bot is ready before starting monitor"""
        await self.wait_until_ready()


async def create_bot() -> LibrarianBot:
    """
    Create and configure the Discord bot

    Returns:
        Configured LibrarianBot instance
    """
    # Setup intents
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True

    # Create bot
    bot = LibrarianBot(
        command_prefix=Config.COMMAND_PREFIX,
        intents=intents,
        help_command=None,  # Use slash commands instead
    )

    return bot


async def main():
    """Main entry point"""
    try:
        # Validate configuration
        logger.info("📋 Validating configuration...")
        Config.validate()
        logger.info("✅ Configuration validated")

        # Test connections
        logger.info("🔌 Testing external connections...")

        # Test Prowlarr
        prowlarr_ok = await test_prowlarr_connection()
        if prowlarr_ok:
            logger.info("✅ Prowlarr connection OK")
        else:
            logger.warning("⚠️  Prowlarr connection failed (non-blocking)")

        # Test qBittorrent
        client = get_qbit_client()
        qbit_ok = await client.health_check()
        if qbit_ok:
            logger.info("✅ qBittorrent connection OK")
        else:
            logger.warning("⚠️  qBittorrent connection failed (non-blocking)")

        # Test AudiobookShelf
        abs_ok = await test_audiobookshelf()
        if abs_ok:
            logger.info("✅ AudiobookShelf connection OK")
        else:
            logger.debug("ℹ️  AudiobookShelf not configured or unreachable (non-blocking)")

        # Create and run bot
        logger.info("🚀 Starting Discord bot...")
        bot = await create_bot()

        async with bot:
            await bot.start(Config.DISCORD_TOKEN)

    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        sys.exit(1)
    except discord.errors.LoginFailure:
        logger.error("❌ Invalid Discord token")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Check if running on Windows and use ProactorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(main())
