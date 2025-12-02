"""
Discord command handlers
All Discord slash commands and command group
"""

import logging
from typing import Optional, List
import discord
from discord import app_commands
from discord.ext import commands

from config import Config
from prowlarr_api import (
    search_prowlarr,
    search_audiobook,
    search_ebook,
    SearchCategory,
    SearchResult,
)
from qbit_client import get_qbit_client
from discord_views import SearchResultsView, AdminApprovalView, PaginatedView, RequestTypeView, PendingApprovalView, ApprovedView, DeniedView
from open_library_api import search_open_library, BookMetadata as OLBookMetadata
from google_books_api import search_google_books, BookMetadata as GoogleBookMetadata
from utils import format_size, truncate_string, split_into_chunks
import asyncio

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
        title="Book title (required)",
        author="Author name (optional) - improves search accuracy"
    )
    async def request_command(
        self,
        interaction: discord.Interaction,
        title: str,
        author: Optional[str] = None,
    ):
        """
        Search for a book and request ebook or audiobook

        Args:
            interaction: Discord interaction
            query: Search query (title or title+author)
        """
        try:
            # DEFER IMMEDIATELY with ephemeral to ensure Discord gets a response
            await interaction.response.defer(ephemeral=True)

            # Build search query
            query = title.strip()
            if author:
                query = f"{title.strip()} {author.strip()}"

            logger.info(f"Search request from {interaction.user}: {query}")

            # Show searching message
            await interaction.followup.send(f"🔍 Searching for: **{query}**...")

            # Search both APIs in parallel
            logger.debug(f"Searching Google Books and Open Library for: {query}")
            google_results, ol_results = await asyncio.gather(
                search_google_books(query, max_results=10),
                search_open_library(query, max_results=10),
                return_exceptions=True
            )

            # Handle any exceptions from parallel searches
            if isinstance(google_results, Exception):
                logger.warning(f"Google Books search error: {google_results}")
                google_results = []
            if isinstance(ol_results, Exception):
                logger.warning(f"Open Library search error: {ol_results}")
                ol_results = []

            # Merge and deduplicate results
            book_results = self._merge_book_results(google_results, ol_results)

            if not book_results:
                await interaction.followup.send(
                    f"❌ No books found for: **{query}**\n"
                    f"Please try a different search term or check the spelling.",
                    ephemeral=True,
                )
                return

            logger.info(f"Found {len(book_results)} unique books after deduplication")

            # If multiple results, show selection
            if len(book_results) > 1:
                await self._show_book_selection(interaction, book_results)
            else:
                # Single result - proceed directly
                await self._show_book_request(interaction, book_results[0])

        except Exception as e:
            logger.error(f"Error in request command: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    f"❌ Error processing request: {str(e)}",
                    ephemeral=True,
                )
            except Exception as followup_error:
                logger.error(f"Could not send error message: {followup_error}")

    def _merge_book_results(self, google_books: list, ol_books: list) -> list:
        """
        Merge Google Books and Open Library results, deduplicating by title and author

        Args:
            google_books: List of GoogleBookMetadata
            ol_books: List of OLBookMetadata

        Returns:
            List of deduplicated OLBookMetadata (using Open Library format as standard)
        """
        merged = {}  # Use title+authors as key for deduplication

        # Add Open Library results first (they have better structure)
        for book in ol_books:
            key = self._get_book_key(book.title, book.authors)
            merged[key] = book
            logger.debug(f"Added OL book: {book.title}")

        # Add Google Books results, avoiding duplicates
        for gb_book in google_books:
            key = self._get_book_key(gb_book.title, gb_book.authors)
            
            # If not already in merged, convert and add it
            if key not in merged:
                # Convert GoogleBookMetadata to OLBookMetadata format
                ol_book = OLBookMetadata(
                    title=gb_book.title,
                    authors=gb_book.authors or ["Unknown"],
                    first_publish_year=self._extract_year(gb_book.published_date),
                    isbn_13=gb_book.isbn_13,
                    isbn_10=gb_book.isbn_10,
                    cover_id=None,  # Google Books has image_url instead
                    description=gb_book.description,
                    has_ebook=True,  # Assume ebook available from Google Books
                    has_audiobook=False,  # Google Books doesn't explicitly say
                )
                merged[key] = ol_book
                logger.debug(f"Added GB book (converted): {gb_book.title}")
            else:
                # Book already exists, merge metadata if Google Books has better cover
                existing = merged[key]
                if gb_book.image_url and not existing.cover_id:
                    logger.debug(f"Merging cover data for: {gb_book.title}")

        logger.info(f"Merged {len(google_books)} Google Books + {len(ol_books)} OL books = {len(merged)} unique")
        return list(merged.values())

    def _get_book_key(self, title: str, authors: list) -> str:
        """Create deduplication key from title and authors"""
        # Normalize title
        title_key = title.lower().strip()
        # Remove series info like "- The Empyrean #1" or "(Shadow of the Fox #1)"
        title_key = title_key.split(" - ")[0].split(" (")[0].strip()
        
        # Get first author or Unknown
        author_key = ""
        if authors:
            author = authors[0] if isinstance(authors[0], str) else getattr(authors[0], 'name', 'Unknown')
            author_key = author.lower().strip().split()[0] if author else ""
        
        return f"{title_key}|{author_key}"

    def _extract_year(self, date_str: str) -> Optional[int]:
        """Extract year from date string"""
        if not date_str:
            return None
        try:
            return int(date_str.split('-')[0])
        except (ValueError, IndexError):
            return None

    def _show_book_selection(
        self, interaction: discord.Interaction, books: List[BookMetadata]
    ):
        """Show selection of multiple books"""
        try:
            # Create embeds for each book
            embeds = []
            for idx, book in enumerate(books[:5], 1):  # Max 5 options
                embed = discord.Embed(
                    title=f"{idx}. {book.title}",
                    description=f"**Author(s):** {', '.join(book.authors)}",
                    color=discord.Color.blue(),
                )

                if book.first_publish_year:
                    embed.add_field(
                        name="Published",
                        value=str(book.first_publish_year),
                        inline=True,
                    )

                availability = []
                if book.has_ebook:
                    availability.append("✓ Ebook")
                if book.has_audiobook:
                    availability.append("✓ Audiobook")

                if availability:
                    embed.add_field(
                        name="Available",
                        value=" | ".join(availability),
                        inline=True,
                    )

                cover_url = book.get_cover_url("M")
                if cover_url:
                    embed.set_thumbnail(url=cover_url)

                embeds.append(embed)

            # Create selection buttons
            options = [
                discord.SelectOption(label=f"{idx}. {book.title}", value=str(idx - 1))
                for idx, book in enumerate(books[:5], 1)
            ]

            class BookSelect(discord.ui.Select):
                def __init__(self, books_list, cog_instance):
                    self.books_list = books_list
                    self.cog = cog_instance
                    super().__init__(
                        placeholder="Select a book...",
                        min_values=1,
                        max_values=1,
                        options=options,
                    )

                async def callback(self, select_interaction: discord.Interaction):
                    try:
                        await select_interaction.response.defer()
                        selected_idx = int(self.values[0])
                        selected_book = self.books_list[selected_idx]

                        # Show request view for selected book
                        await self.cog._show_book_request(
                            select_interaction, selected_book
                        )
                        self.view.stop()
                    except Exception as e:
                        logger.error(f"Error in book selection: {e}", exc_info=True)
                        await select_interaction.followup.send(
                            f"❌ Error selecting book: {str(e)}",
                            ephemeral=True,
                        )

            class BookSelectView(discord.ui.View):
                def __init__(self, cog_instance):
                    super().__init__(timeout=300)
                    self.add_item(BookSelect(books, cog_instance))

            view = BookSelectView(self)

            await interaction.followup.send(
                embeds=embeds,
                view=view,
                content="**Choose a book:**",
            )

        except Exception as e:
            logger.error(f"Error in book selection: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error showing book options: {str(e)}",
                ephemeral=True,
            )

    async def _show_book_request(
        self, interaction: discord.Interaction, book: OLBookMetadata
    ):
        """Show single book with request type buttons"""
        try:
            # Create book info embed
            embed = discord.Embed(
                title=f"📚 {book.title}",
                color=discord.Color.blue(),
            )

            # Add authors
            if book.authors:
                embed.add_field(name="Author(s)", value=", ".join(book.authors), inline=False)

            # Add publication year
            if book.first_publish_year:
                embed.add_field(
                    name="First Published",
                    value=str(book.first_publish_year),
                    inline=True,
                )

            # Add ISBN info
            if book.isbn_13:
                embed.add_field(name="ISBN-13", value=book.isbn_13, inline=True)

            # Add availability info
            availability = []
            if book.has_ebook:
                availability.append("✓ Ebook available")
            if book.has_audiobook:
                availability.append("✓ Audiobook available")

            if availability:
                embed.add_field(
                    name="Available Formats",
                    value="\n".join(availability),
                    inline=False,
                )

            # Add cover if available
            cover_url = book.get_cover_url("L")
            if cover_url:
                embed.set_thumbnail(url=cover_url)

            embed.set_footer(text=f"Requested by {interaction.user.name}")

            # Create request type view
            view = RequestTypeView(book.title)

            # Send book info with request type buttons
            message = await interaction.followup.send(embed=embed, view=view)

            # Wait for user to select type
            await view.wait()

            if view.selected_type is None:
                logger.info(f"Request timed out for {book.title}")
                return

            request_type = view.selected_type
            logger.info(
                f"User {interaction.user} requested {request_type} for: {book.title}"
            )

            # Update the message with pending approval buttons (edit the message)
            pending_view = PendingApprovalView(book.title, request_type)
            try:
                await message.edit(view=pending_view)
            except Exception as e:
                logger.warning(f"Could not edit message: {e}")

            # Search Prowlarr for torrents with correct category
            # Clean the title - remove series info like "- The Empyrean #1"
            search_title = book.title.split(" - ")[0].split(" (")[0].strip()
            search_query = search_title
            if book.authors:
                search_query += f" {book.authors[0]}"

            logger.debug(f"Searching Prowlarr for {request_type}: {search_query}")

            if request_type == "audiobook":
                prowlarr_results = await search_audiobook(search_query, limit=Config.MAX_RESULTS)
            else:  # ebook
                prowlarr_results = await search_ebook(search_query, limit=Config.MAX_RESULTS)

            logger.debug(f"Prowlarr returned {len(prowlarr_results)} results for {request_type}: {[r.title for r in prowlarr_results[:3]]}")

            if not prowlarr_results:
                await interaction.followup.send(
                    f"❌ No {request_type} torrents found for: **{book.title}**",
                    ephemeral=True,
                )
                return

            logger.info(f"Found {len(prowlarr_results)} {request_type} results")

            # Find best torrent (highest seeders)
            best_result = max(prowlarr_results, key=lambda x: x.seeders)

            logger.info(
                f"Selected best torrent: {best_result.title} ({best_result.seeders} seeders)"
            )

            # Store for admin approval
            self.pending_requests[interaction.user.id] = {
                "query": search_query,
                "request_type": request_type,
                "book": book,
                "torrent": best_result,
                "torrents_all": prowlarr_results,
                "user": interaction.user,
                "message": message,
            }

            # Send to admin channel for approval (pass all results)
            await self._send_admin_approval(
                interaction, book, request_type, best_result, interaction.user, prowlarr_results
            )

        except Exception as e:
            logger.error(f"Error showing book request: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error processing book: {str(e)}",
                ephemeral=True,
            )

    async def _send_admin_approval(
        self,
        interaction: discord.Interaction,
        book: OLBookMetadata,
        request_type: str,
        torrent: SearchResult,
        user: discord.User,
        all_torrents: List[SearchResult] = None,
    ):
        """
        Send approval request to admin channel

        Args:
            interaction: Original interaction
            book: Book metadata
            request_type: "ebook" or "audiobook"
            torrent: Best torrent result
            user: User who requested
            all_torrents: All available torrent results for selection
        """
        try:
            # Get admin channel
            admin_channel = self.bot.get_channel(Config.ADMIN_CHANNEL_ID)
            if not admin_channel:
                logger.error(f"Admin channel {Config.ADMIN_CHANNEL_ID} not found")
                await interaction.followup.send(
                    "⚠️ Admin channel not configured",
                    ephemeral=True,
                )
                return

            # Create approval embed
            embed = discord.Embed(
                title=f"📋 Approval Request - {request_type.upper()}",
                description=f"User: {user.mention} (@{user.name})",
                color=discord.Color.gold(),
            )

            embed.add_field(name="Book Title", value=book.title, inline=False)

            if book.authors:
                embed.add_field(name="Author(s)", value=", ".join(book.authors), inline=False)

            embed.add_field(
                name="Requested Format",
                value=f"🎯 {request_type.upper()}",
                inline=True,
            )

            # Show all available torrents info
            if all_torrents:
                torrent_list = "\n".join(
                    [f"• {t.indexer}: {t.seeders} seeders" for t in all_torrents[:5]]
                )
                embed.add_field(
                    name="Available Torrents",
                    value=torrent_list,
                    inline=False,
                )

            embed.add_field(
                name="Recommended (Highest Seeders)",
                value=f"**{torrent.title}**\n"
                f"Size: {format_size(torrent.size)}\n"
                f"Seeders: {torrent.seeders} | Leechers: {torrent.leechers}\n"
                f"Indexer: {torrent.indexer}",
                inline=False,
            )

            embed.set_footer(text=f"User ID: {user.id}")

            # Create approval view with all torrents
            approval_view = AdminApprovalView(
                torrent_results=all_torrents or [torrent],
                on_approve=lambda inter, view: self._handle_admin_approve(
                    inter, user, book, view.selected_torrent, request_type
                ),
                on_deny=lambda inter, view: self._handle_admin_deny(inter, user, book),
            )

            # Send to admin channel
            await admin_channel.send(embed=embed, view=approval_view)

        except Exception as e:
            logger.error(f"Error sending admin approval: {e}", exc_info=True)

    async def _handle_admin_approve(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        book: OLBookMetadata,
        torrent: SearchResult,  # Can be None, we'll use the selected from view
        request_type: str,
    ):
        """Handle admin approval and auto-download"""
        try:
            await interaction.response.defer()

            logger.info(
                f"Admin {interaction.user} approved {request_type} request for {book.title}"
            )

            # Use the torrent passed in (already selected from view)
            selected_torrent = torrent
            logger.info(f"Using torrent: {selected_torrent.title} from {selected_torrent.indexer}")

            # Update user's original message to show Approved button
            if user.id in self.pending_requests:
                try:
                    user_message = self.pending_requests[user.id].get("message")
                    if user_message:
                        approved_view = ApprovedView()
                        await user_message.edit(view=approved_view)
                except Exception as e:
                    logger.warning(f"Could not update user message: {e}")

            # Add torrent to qBittorrent
            qbit = get_qbit_client()
            download_url = selected_torrent.download_url
            if not download_url:
                logger.error(f"No download URL for torrent: {selected_torrent.title}")
                await interaction.followup.send(
                    f"❌ Error: No download URL available for {selected_torrent.title}",
                    ephemeral=True,
                )
                return

            # Add to qBittorrent with category
            qbit.add_torrent(
                torrent_input=download_url,
                is_paused=False,
            )

            logger.info(f"Torrent added to qBittorrent: {selected_torrent.title}")

            # Send confirmation to user
            try:
                user_embed = discord.Embed(
                    title="✅ Request Approved & Downloading",
                    description=f"Your {request_type} request has been approved!",
                    color=discord.Color.green(),
                )

                user_embed.add_field(name="Book", value=book.title, inline=False)
                user_embed.add_field(
                    name="Format",
                    value=request_type.upper(),
                    inline=True,
                )
                user_embed.add_field(
                    name="Torrent",
                    value=selected_torrent.title,
                    inline=False,
                )
                user_embed.add_field(
                    name="Status",
                    value="📥 Downloading...",
                    inline=True,
                )

                await user.send(embed=user_embed)
            except Exception as e:
                logger.warning(f"Could not send DM to user {user}: {e}")

            # Send admin confirmation
            await interaction.followup.send(
                f"✅ Download started for {user.mention}\n"
                f"**{book.title}** ({request_type})",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error in admin approval: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error processing approval: {str(e)}",
                ephemeral=True,
            )

    async def _handle_admin_deny(
        self, interaction: discord.Interaction, user: discord.User, book: OLBookMetadata
    ):
        """Handle admin denial"""
        try:
            await interaction.response.defer()

            logger.info(f"Admin {interaction.user} denied request for {book.title}")

            # Update user's original message to show Denied button
            if user.id in self.pending_requests:
                try:
                    user_message = self.pending_requests[user.id].get("message")
                    if user_message:
                        denied_view = DeniedView()
                        await user_message.edit(view=denied_view)
                except Exception as e:
                    logger.warning(f"Could not update user message: {e}")

            # Notify user
            try:
                deny_embed = discord.Embed(
                    title="❌ Request Denied",
                    description="Your request has been denied by an admin.",
                    color=discord.Color.red(),
                )
                deny_embed.add_field(name="Book", value=book.title, inline=False)

                await user.send(embed=deny_embed)
            except Exception as e:
                logger.warning(f"Could not send DM to user {user}: {e}")

            await interaction.followup.send(
                f"❌ Request denied for {user.mention}",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error in admin denial: {e}")

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
