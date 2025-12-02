"""
Discord command handlers
All Discord slash commands and command group
"""

import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from prowlarr_api import search_prowlarr, search_audiobook, search_ebook, SearchCategory
from qbit_client import get_qbit_client
from discord_views import SearchResultsView, AdminApprovalView, PaginatedView
from utils import format_size, truncate_string, split_into_chunks

logger = logging.getLogger(__name__)


class LibrarianCommands(commands.Cog):
    """Librarian Bot commands"""

    def __init__(self, bot: commands.Bot):
        """
        Initialize commands cog

        Args:
            bot: Discord bot instance
        """
        self.bot = bot
        self.pending_requests = {}  # Track pending search requests

    @app_commands.command(name="request", description="Search for a book or audiobook")
    @app_commands.describe(
        query="Book/audiobook title or author",
        media_type="Type of media to search for",
    )
    async def request_command(
        self,
        interaction: discord.Interaction,
        query: str,
        media_type: str = "all",
    ):
        """
        Search for a book or audiobook

        Args:
            interaction: Discord interaction
            query: Search query
            media_type: "audiobook", "ebook", or "all"
        """
        try:
            await interaction.response.defer()

            # Validate media type
            media_type = media_type.lower()
            if media_type not in ["audiobook", "ebook", "all"]:
                await interaction.followup.send(
                    "❌ Invalid media type. Use: audiobook, ebook, or all",
                    ephemeral=True,
                )
                return

            logger.info(f"Search request from {interaction.user}: {query} ({media_type})")

            # Show searching message
            await interaction.followup.send(f"🔍 Searching for: **{query}**...")

            # Perform search based on media type
            if media_type == "audiobook":
                results = await search_audiobook(query, limit=Config.MAX_RESULTS)
            elif media_type == "ebook":
                results = await search_ebook(query, limit=Config.MAX_RESULTS)
            else:
                results = await search_prowlarr(query, SearchCategory.ALL, Config.MAX_RESULTS)

            if not results:
                await interaction.followup.send(
                    f"❌ No results found for: **{query}**",
                    ephemeral=True,
                )
                return

            # Format results for display
            result_dicts = [r.to_dict() for r in results]

            # Create embeds for results
            embeds = []
            for idx, result in enumerate(results[:Config.MAX_RESULTS], 1):
                embed = discord.Embed(
                    title=f"📚 Result {idx}: {truncate_string(result.title, 150)}",
                    description=f"**Indexer:** {result.indexer}\n"
                    f"**Size:** {format_size(result.size)}\n"
                    f"**Seeders:** {result.seeders} | **Leechers:** {result.leechers}\n"
                    f"**Published:** {result.publish_date}",
                    color=discord.Color.blue(),
                )
                embed.set_footer(text=f"Result {idx} of {len(results)}")
                embeds.append(embed)

            # Create selection view
            async def on_result_select(inter, selected, idx):
                await inter.response.defer()
                # Store selection for next step
                self.pending_requests[interaction.user.id] = {
                    "query": query,
                    "results": result_dicts,
                    "selected_idx": idx,
                    "selected_result": selected,
                }
                await inter.followup.send(
                    f"✅ Selected: **{selected['title']}**\n\n"
                    f"Awaiting admin approval...",
                    ephemeral=True,
                )
                # Send approval request to admins
                await self._send_approval_request(interaction, selected, idx)

            # Send results with dropdown
            view = SearchResultsView(result_dicts, on_select=on_result_select)
            await interaction.followup.send(
                embeds=embeds[:1] if len(embeds) > 1 else embeds,
                view=view,
            )

            # Send pagination if multiple results
            if len(embeds) > 1:
                paginated_view = PaginatedView(embeds)
                await interaction.followup.send(
                    "📖 **Scroll through results:**",
                    view=paginated_view,
                    ephemeral=True,
                )

        except Exception as e:
            logger.error(f"Error in request command: {e}")
            await interaction.followup.send(
                f"❌ Error searching: {str(e)}",
                ephemeral=True,
            )

    async def _send_approval_request(
        self,
        interaction: discord.Interaction,
        result: dict,
        result_idx: int,
    ):
        """
        Send approval request to admins

        Args:
            interaction: Original user interaction
            result: Selected search result
            result_idx: Result index
        """
        try:
            # Create approval embed
            embed = discord.Embed(
                title="📥 Download Approval Requested",
                description=f"**Requester:** {interaction.user.mention}\n"
                f"**Title:** {truncate_string(result['title'], 100)}\n"
                f"**Indexer:** {result['indexer']}\n"
                f"**Size:** {format_size(result['size'])}\n"
                f"**Seeders:** {result['seeders']}",
                color=discord.Color.orange(),
            )

            # Create approval view
            async def on_approve(inter):
                await self._approve_download(inter, interaction.user, result)

            async def on_deny(inter):
                await self._deny_download(inter, interaction.user, result)

            approval_view = AdminApprovalView(
                required_role=Config.ADMIN_ROLE,
                on_approve=on_approve,
                on_deny=on_deny,
            )

            # Find admin channel or use current channel
            admin_channel = None
            for channel in interaction.guild.text_channels:
                if "admin" in channel.name.lower() or "approval" in channel.name.lower():
                    admin_channel = channel
                    break

            if not admin_channel:
                admin_channel = interaction.channel

            await admin_channel.send(
                embed=embed,
                view=approval_view,
            )

            logger.info(
                f"Approval request sent for: {result['title']} "
                f"(Requester: {interaction.user})"
            )

        except Exception as e:
            logger.error(f"Error sending approval request: {e}")

    async def _approve_download(
        self,
        interaction: discord.Interaction,
        requester: discord.User,
        result: dict,
    ):
        """
        Approve and start download

        Args:
            interaction: Admin interaction
            requester: User who requested
            result: Search result to download
        """
        try:
            await interaction.response.defer()

            # Create approval embed
            embed = discord.Embed(
                title="✅ Download Approved",
                description=f"**Requester:** {requester.mention}\n"
                f"**Title:** {truncate_string(result['title'], 100)}\n"
                f"**Indexer:** {result['indexer']}\n"
                f"**Approved by:** {interaction.user.mention}",
                color=discord.Color.green(),
            )

            await interaction.channel.send(embed=embed)

            # Add torrent to qBittorrent
            client = get_qbit_client()
            if not client.connect():
                await requester.send(
                    "❌ Failed to connect to download client. Please try again later."
                )
                logger.error("Failed to connect to qBittorrent")
                return

            torrent_hash = client.add_torrent(result["download_url"])
            if not torrent_hash:
                await requester.send(
                    "❌ Failed to add torrent to download queue. Please try again later."
                )
                logger.error(f"Failed to add torrent: {result['download_url']}")
                return

            # Notify requester
            await requester.send(
                f"✅ **Download Approved!**\n\n"
                f"**Title:** {result['title']}\n"
                f"**Status:** Added to download queue\n\n"
                f"I'll notify you when it's complete and organized."
            )

            logger.info(
                f"Download approved for: {result['title']} "
                f"(Requester: {requester}, Torrent: {torrent_hash})"
            )

        except Exception as e:
            logger.error(f"Error approving download: {e}")

    async def _deny_download(
        self,
        interaction: discord.Interaction,
        requester: discord.User,
        result: dict,
    ):
        """
        Deny download request

        Args:
            interaction: Admin interaction
            requester: User who requested
            result: Search result that was denied
        """
        try:
            await interaction.response.defer()

            # Create denial embed
            embed = discord.Embed(
                title="❌ Download Denied",
                description=f"**Requester:** {requester.mention}\n"
                f"**Title:** {truncate_string(result['title'], 100)}\n"
                f"**Denied by:** {interaction.user.mention}",
                color=discord.Color.red(),
            )

            await interaction.channel.send(embed=embed)

            # Notify requester
            await requester.send(
                f"❌ **Download Denied**\n\n"
                f"**Title:** {result['title']}\n"
                f"**Reason:** Admin approval denied\n\n"
                f"You can try requesting a different result."
            )

            logger.info(
                f"Download denied for: {result['title']} "
                f"(Requester: {requester}, Denier: {interaction.user})"
            )

        except Exception as e:
            logger.error(f"Error denying download: {e}")

    @app_commands.command(name="status", description="View active downloads")
    async def status_command(self, interaction: discord.Interaction):
        """
        View active downloads and organization status

        Args:
            interaction: Discord interaction
        """
        try:
            await interaction.response.defer()

            client = get_qbit_client()
            if not client.connect():
                await interaction.followup.send(
                    "❌ Cannot connect to download client",
                    ephemeral=True,
                )
                return

            torrents = client.get_torrents_in_category()

            if not torrents:
                await interaction.followup.send(
                    "📭 No active downloads in the library category",
                    ephemeral=True,
                )
                return

            # Create status embeds
            embeds = []
            for torrent in torrents[:10]:  # Show first 10
                progress_pct = int(torrent.progress * 100)
                embed = discord.Embed(
                    title=f"📥 {truncate_string(torrent.name, 100)}",
                    description=f"**Progress:** {progress_pct}%\n"
                    f"**Size:** {format_size(torrent.size)}\n"
                    f"**Downloaded:** {format_size(torrent.downloaded)}\n"
                    f"**Speed:** ⬇️ {format_size(torrent.download_speed)}/s\n"
                    f"**State:** {torrent.state.value}",
                    color=discord.Color.blue(),
                )
                embeds.append(embed)

            if len(embeds) > 1:
                view = PaginatedView(embeds)
                await interaction.followup.send(
                    embeds=[embeds[0]],
                    view=view,
                )
            else:
                await interaction.followup.send(embeds=embeds)

        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await interaction.followup.send(
                f"❌ Error getting status: {str(e)}",
                ephemeral=True,
            )

    @app_commands.command(
        name="help",
        description="Show available commands and how to use them",
    )
    async def help_command(self, interaction: discord.Interaction):
        """
        Show help information

        Args:
            interaction: Discord interaction
        """
        try:
            await interaction.response.defer()

            embed = discord.Embed(
                title="📚 Librarian Bot Help",
                description="Automated audiobook and ebook management bot",
                color=discord.Color.blue(),
            )

            embed.add_field(
                name="/request <query> [media_type]",
                value="Search for a book or audiobook\n"
                "- `query`: Book title or author\n"
                "- `media_type`: audiobook, ebook, or all (default: all)",
                inline=False,
            )

            embed.add_field(
                name="/status",
                value="View active downloads and organization jobs",
                inline=False,
            )

            embed.add_field(
                name="/help",
                value="Show this help message",
                inline=False,
            )

            embed.add_field(
                name="How it works:",
                value="1. Use `/request` to search\n"
                "2. Select a result from the dropdown\n"
                "3. Admin approves or denies\n"
                "4. Approved downloads start automatically\n"
                "5. Receive DM when complete and organized",
                inline=False,
            )

            embed.set_footer(text=f"Bot prefix: {Config.COMMAND_PREFIX}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await interaction.followup.send(
                "❌ Error getting help",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    """
    Setup function for cog loading

    Args:
        bot: Discord bot instance
    """
    await bot.add_cog(LibrarianCommands(bot))
