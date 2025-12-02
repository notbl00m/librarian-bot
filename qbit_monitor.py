"""
qBittorrent Monitor
Monitors qBittorrent for completed downloads and triggers organization
"""

import asyncio
import logging
import json
from typing import Set, Dict, Any
from datetime import datetime
import os
import paramiko
from pathlib import Path

logger = logging.getLogger(__name__)

class QBitMonitor:
    """Monitors qBittorrent for completed downloads and organizes them"""
    
    # Persistent database for tracking processed torrents (survives bot restart)
    PROCESSED_DB_FILE = ".processed_torrents.json"
    
    def __init__(self, qbit_client, organizer_module, bot=None, book_requests_db=None):
        """
        Initialize the monitor
        
        Args:
            qbit_client: QBittorrentAPI instance
            organizer_module: The library_organizer module
            bot: Optional Discord bot instance for notifications
            book_requests_db: Optional BookRequestsDB for updating user messages
        """
        self.qbit = qbit_client
        self.organizer = organizer_module
        self.bot = bot
        self.book_requests_db = book_requests_db
        self.processed_hashes: Set[str] = self._load_processed_hashes()
        self.monitoring = False
        self.task = None
    
    def _load_processed_hashes(self) -> Set[str]:
        """Load processed torrent hashes from persistent database"""
        try:
            if Path(self.PROCESSED_DB_FILE).exists():
                with open(self.PROCESSED_DB_FILE, 'r') as f:
                    data = json.load(f)
                    hashes = set(data.get("processed_hashes", []))
                    logger.debug(f"Loaded {len(hashes)} previously processed torrents from disk")
                    return hashes
        except Exception as e:
            logger.warning(f"Could not load processed torrents database: {e}")
        return set()
    
    def _save_processed_hashes(self):
        """Save processed torrent hashes to persistent database"""
        try:
            data = {
                "processed_hashes": list(self.processed_hashes),
                "last_updated": datetime.now().isoformat()
            }
            with open(self.PROCESSED_DB_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self.processed_hashes)} processed torrents to disk")
        except Exception as e:
            logger.error(f"Could not save processed torrents database: {e}")
        
    async def start(self):
        """Start monitoring qBittorrent"""
        if self.monitoring:
            logger.warning("Monitor already running")
            return
            
        self.monitoring = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("qBittorrent monitor started")
        
    async def stop(self):
        """Stop monitoring qBittorrent"""
        self.monitoring = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("qBittorrent monitor stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop"""
        check_interval = 30  # seconds
        
        while self.monitoring:
            try:
                await self._check_completed_downloads()
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)
                await asyncio.sleep(check_interval)
                
    async def _check_completed_downloads(self):
        """Check for completed downloads and organize them"""
        try:
            # Ensure connected (synchronous)
            loop = asyncio.get_event_loop()
            connected = await loop.run_in_executor(None, self.qbit.connect)
            
            if not connected:
                logger.debug("Could not connect to qBittorrent")
                return
            
            # Get all torrents with category "librarian-bot" (synchronous call in executor)
            torrents = await loop.run_in_executor(
                None,
                self.qbit.get_torrents_in_category,
                "librarian-bot"
            )
            
            for torrent in torrents:
                torrent_hash = torrent.hash
                
                # Skip if already processed
                if torrent_hash in self.processed_hashes:
                    continue
                    
                # Check if completed (seeding state or progress 100%)
                from qbit_client import TorrentState
                if torrent.state == TorrentState.SEEDING or torrent.progress >= 1.0:
                    logger.info(f"✅ Completed download detected: {torrent.name}")
                    logger.debug(f"Save path: {torrent.save_path}, Progress: {torrent.progress:.1%}")
                    
                    # Run organizer
                    await self._organize_download(torrent.name, torrent.save_path)
                    
                    # Notify bot about completion (for message update)
                    if self.bot:
                        await self._notify_bot_completion(torrent.name)
                    
                    # Mark as processed
                    self.processed_hashes.add(torrent_hash)
                    self._save_processed_hashes()  # Persist to disk
                    logger.info(f"📚 Marked as processed: {torrent.name}")
                    
        except Exception as e:
            logger.error(f"Error checking completed downloads: {e}", exc_info=True)
            
    async def _organize_download(self, name: str, save_path: str):
        """
        Organize a completed download
        
        Args:
            name: Torrent name
            save_path: Download location
        """
        try:
            logger.info(f"📂 Starting organization for: {name}")
            logger.debug(f"Source path: {save_path}")
            
            # Run organizer in thread pool (it's synchronous)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._run_organizer,
                save_path
            )
            
            logger.info(f"✨ Organization completed for: {name}")
            
        except Exception as e:
            logger.error(f"❌ Error organizing {name}: {e}", exc_info=True)
    
    async def _notify_bot_completion(self, torrent_name: str):
        """
        Notify bot that a download is complete and update user message
        
        Args:
            torrent_name: Name of the completed torrent
        """
        try:
            if not self.bot:
                return

            # Try to update the user's message if we have book_requests_db
            if self.book_requests_db:
                try:
                    # Get request info by torrent name (approximated as book title)
                    request_info = self.book_requests_db.get_request(book_title=torrent_name)
                    
                    if request_info:
                        message_id = request_info.get("message_id")
                        channel_id = request_info.get("channel_id")
                        
                        if message_id and channel_id:
                            try:
                                channel = await self.bot.fetch_channel(channel_id)
                                message = await channel.fetch_message(message_id)
                                
                                # Update message to show approved status
                                from discord_views import ApprovedView
                                await message.edit(view=ApprovedView())
                                logger.info(f"Updated user message for completed download: {torrent_name}")
                                
                                # Mark as completed in database
                                self.book_requests_db.mark_complete(book_title=torrent_name, status="completed")
                            except Exception as e:
                                logger.warning(f"Could not update user message for {torrent_name}: {e}")
                except Exception as e:
                    logger.debug(f"Could not find book request for {torrent_name}: {e}")
            
            # Also notify cog if it has the method
            cog = self.bot.get_cog('LibrarianCommands')
            if cog and hasattr(cog, 'on_download_completed'):
                await cog.on_download_completed(torrent_name)
        except Exception as e:
            logger.warning(f"Could not notify bot of completion: {e}")
            
    def _run_organizer(self, source_path: str):
        """
        Run the organizer synchronously - via SSH on the seedbox
        
        Args:
            source_path: Path to organize from (not used directly, organizer uses CONFIG)
        """
        try:
            # Always run on seedbox via SSH since files are there
            self._run_organizer_ssh()
            
        except Exception as e:
            logger.error(f"Organizer error: {e}", exc_info=True)
            raise
    
    def _run_organizer_ssh(self):
        """Upload organizer to seedbox and execute it"""
        try:
            host = os.getenv("SEEDBOX_HOST", "")
            user = os.getenv("SEEDBOX_USER", "")
            password = os.getenv("SEEDBOX_PASSWORD", "")
            port = int(os.getenv("SEEDBOX_SSH_PORT", "22"))
            
            if not host or not user:
                logger.error("Seedbox SSH credentials not configured in .env")
                return
            
            # Extract hostname from user@host format
            if "@" in host:
                user, host = host.split("@")
            
            logger.info(f"🔌 Connecting to seedbox: {user}@{host}:{port}")
            
            # Create SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, port=port, username=user, password=password, timeout=30)
            
            # Get paths
            organizer_remote_dir = os.getenv("ORGANIZER_REMOTE_PATH", "/home/bloomstreaming/downloads/completed/BLOOM-LIBRARY/[Organizer]")
            organizer_script_path = f"{organizer_remote_dir}/library_organizer.py"
            local_script = os.path.join(os.path.dirname(__file__), "library_organizer.py")
            
            # Create [Organizer] directory on seedbox
            logger.info(f"📁 Creating organizer directory: {organizer_remote_dir}")
            stdin, stdout, stderr = ssh.exec_command(f"mkdir -p '{organizer_remote_dir}'")
            stdout.channel.recv_exit_status()
            
            # Check if organizer script already exists on seedbox
            sftp = ssh.open_sftp()
            script_exists = False
            try:
                sftp.stat(organizer_script_path)
                script_exists = True
                logger.info(f"✅ Organizer script already exists on seedbox (skipping upload)")
            except FileNotFoundError:
                script_exists = False
            
            # Only upload if it doesn't exist (preserves database in that directory)
            if not script_exists:
                logger.info(f"📤 Uploading organizer script to seedbox...")
                sftp.put(local_script, organizer_script_path)
                logger.info(f"✅ Uploaded: {organizer_script_path}")
            
            # Create .env file on seedbox with correct paths (update each time in case config changed)
            env_content = f"""QBIT_DOWNLOAD_PATH={os.getenv("QBIT_DOWNLOAD_PATH", "/home/bloomstreaming/downloads/completed/MAM/")}
LIBRARY_PATH={os.getenv("LIBRARY_PATH", "/home/bloomstreaming/downloads/completed/BLOOM-LIBRARY")}
ORGANIZER_REMOTE_PATH={organizer_remote_dir}
"""
            env_path = f"{organizer_remote_dir}/.env"
            with sftp.open(env_path, 'w') as f:
                f.write(env_content)
            logger.info(f"✅ .env configured: {env_path}")
            
            sftp.close()
            
            # Check if python-dotenv and requests are installed
            logger.info("📦 Checking Python dependencies...")
            stdin, stdout, stderr = ssh.exec_command("python3 -c 'import requests, dotenv' 2>/dev/null && echo 'OK' || echo 'MISSING'")
            deps_check = stdout.read().decode().strip()
            
            if deps_check != "OK":
                logger.info("📦 Installing Python dependencies (python-dotenv, requests)...")
                ssh.exec_command("pip3 install --user python-dotenv requests colorama")
            
            # Debug: Check what directories exist
            logger.info("🔍 Checking seedbox directories...")
            stdin, stdout, stderr = ssh.exec_command("ls -la /home/bloomstreaming/downloads/completed/ 2>&1")
            dir_list = stdout.read().decode()
            logger.info(f"[Seedbox] Available directories:\n{dir_list}")
            
            # Run the organizer
            command = f"cd '{organizer_remote_dir}' && python3 library_organizer.py"
            logger.info(f"🚀 Running organizer on seedbox...")
            logger.info(f"   Command: {command}")
            
            stdin, stdout, stderr = ssh.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            
            # Stream output with task indicators
            output = stdout.read().decode()
            errors = stderr.read().decode()
            
            if output:
                for line in output.strip().split('\n'):
                    if line:
                        logger.info(f"[Organizer] {line}")
            if errors and exit_status != 0:
                for line in errors.strip().split('\n'):
                    if line:
                        logger.warning(f"[Organizer] {line}")
            
            if exit_status != 0:
                logger.error(f"❌ Organizer exited with status {exit_status}")
            else:
                logger.info("✅ Organization completed successfully")
            
            ssh.close()
            
        except Exception as e:
            logger.error(f"❌ SSH organizer error: {e}", exc_info=True)
            raise
