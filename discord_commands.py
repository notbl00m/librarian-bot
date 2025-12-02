"""
Discord command handlers
All Discord slash commands and command group
"""

import logging
from typing import Optional, List
import discord
from discord import app_commands
from discord.ext import commands
import asyncio

from config import Config
from prowlarr_api import (
    search_audiobook,
    search_ebook,
    SearchResult,
)
from qbit_client import get_qbit_client
from discord_views import (
    AdminApprovalView,
    PaginatedView,
    RequestTypeView,
    PendingApprovalView,
    ApprovedView,
    DeniedView,
)
from open_library_api import search_open_library, BookMetadata as OLBookMetadata
from google_books_api import search_google_books, BookMetadata as GoogleBookMetadata
from utils import format_size, truncate_string

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
        author="Author name (required)"
    )
    async def request_command(
        self,
        interaction: discord.Interaction,
        title: str,
        author: str,
    ):
        """
        Search for a book and request ebook or audiobook

        Args:
            interaction: Discord interaction
            title: Book title
            author: Author name
        """
        try:
            # DEFER IMMEDIATELY with ephemeral to ensure Discord gets a response
            await interaction.response.defer(ephemeral=True)

            # Build search query with both title and author
            query = f"{title.strip()} {author.strip()}"

            logger.info(f"Search request from {interaction.user}: {query}")

            # Show searching message
            await interaction.followup.send(f"🔍 Searching for: **{query}**...")

            # Search Google Books only (Open Library disabled for now)
            logger.debug(f"Searching Google Books for: {query}")
            try:
                logger.debug("Initiating Google Books API call with max_results=40")
                google_results = await search_google_books(query, max_results=40)
                logger.debug(f"Google Books returned {len(google_results)} results")
            except Exception as e:
                logger.warning(f"Google Books search error: {e}")
                logger.debug(f"Exception details: {type(e).__name__}: {str(e)}")
                google_results = []
            ol_results = []  # Open Library disabled
            logger.debug("Open Library search disabled")

            # Merge and deduplicate results
            book_results = self._merge_book_results(google_results, ol_results, query)

            if not book_results:
                await interaction.followup.send(
                    f"❌ No books found for: **{query}**\n"
                    f"Please try a different search term or check the spelling.",
                    ephemeral=True,
                )
                return

            logger.info(f"Found {len(book_results)} unique books after deduplication")

            # If multiple results, show selection (but filter to best matches only)
            if len(book_results) > 1:
                await self._show_book_selection(interaction, book_results, query)
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

    def _merge_book_results(self, google_books: list, ol_books: list, query: str = "") -> list:
        """
        Merge Google Books and Open Library results, deduplicating.
        DISABLED: All scoring logic disabled - just return raw API results

        Args:
            google_books: List of GoogleBookMetadata
            ol_books: List of OLBookMetadata
            query: Original search query (unused - scoring disabled)

        Returns:
            List of deduplicated books in order received (no scoring)
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
                    image_url=gb_book.image_url,  # PRESERVE Google Books image URL
                )
                merged[key] = ol_book
                logger.debug(f"Added GB book (converted): {gb_book.title}")
            else:
                # Book already exists, merge metadata if Google Books has better cover
                existing = merged[key]
                if gb_book.image_url and not existing.image_url and not existing.cover_id:
                    existing.image_url = gb_book.image_url
                    logger.debug(f"Merging Google Books cover data for: {gb_book.title}")

        # Return in order received (NO SORTING OR SCORING)
        result_list = list(merged.values())
        logger.info(f"Merged {len(google_books)} Google Books + {len(ol_books)} OL books = {len(result_list)} unique (NO SCORING - raw order)")
        return result_list

    def _score_book_relevance(self, title: str, authors: list, query: str = "") -> int:
        """
        Score book relevance based on exact title/author match
        Simple scoring: exact match gets highest score
        
        Args:
            title: Book title
            authors: List of authors
            query: Original search query (for matching)
        
        Returns:
            Score (higher = better match)
        """
        score = 0
        title_lower = title.lower().strip()
        query_lower = query.lower().strip()
        
        logger.debug(f"Starting score calculation for: {title}")
        
        # HEAVILY penalize obviously wrong types (study guides, summaries, etc.)
        bad_keywords = [
            "summary", "guide", "study guide", "sparknotes", "cliff", 
            "cliffsnotes", "bookrags", "quick summary", "key ideas",
            "analysis", "discussion"
        ]
        for keyword in bad_keywords:
            if keyword in title_lower:
                score -= 10000  # Very negative so these don't show
                logger.debug(f"Penalizing wrong type for '{title}': found '{keyword}' in title (-10000)")
                return score
        
        logger.debug(f"Book '{title}' passed support-book filter")
        
        # Extract key words from both title and query for matching
        # Remove common words like "the", "a", "an", "of"
        stop_words = {"the", "a", "an", "of", "and", "or", "in", "on", "at", "to", "for"}
        title_words = [w for w in title_lower.split() if w not in stop_words]
        query_words = [w for w in query_lower.split() if w not in stop_words]
        
        logger.debug(f"Title words: {title_words}, Query words: {query_words}")
        
        # Count how many title words appear in query
        matches = sum(1 for w in title_words if any(w in qw or qw in w for qw in query_words))
        match_ratio = matches / len(title_words) if title_words else 0
        logger.debug(f"Word match ratio: {matches}/{len(title_words)} = {match_ratio*100:.1f}%")
        
        # Exact title match or very close (exact match gets 5000)
        if title_lower == query_lower or title_lower in query_lower:
            score += 5000
            logger.debug(f"Exact title match: {title} (+5000)")
        elif match_ratio >= 0.9:  # 90%+ match
            score += 4000
            logger.debug(f"Very strong title match ({match_ratio*100:.0f}%): {title} (+4000)")
        elif match_ratio >= 0.7:  # 70%+ match
            score += 3000
            logger.debug(f"Strong title match ({match_ratio*100:.0f}%): {title} (+3000)")
        elif match_ratio >= 0.5:  # 50%+ match
            score += 1500
            logger.debug(f"Partial title match ({match_ratio*100:.0f}%): {title} (+1500)")
        else:
            score -= 1000  # Wrong book
            logger.debug(f"Weak match ({match_ratio*100:.0f}%): {title} (-1000)")
        
        # Bonus for author match (if we have one from the query)
        if authors and len(authors) > 0:
            first_author = (authors[0] if isinstance(authors[0], str) else 
                          getattr(authors[0], 'name', '')).lower()
            
            # HEAVILY penalize "unknown" author when we have a specific author query
            if first_author == "unknown" and query_lower:
                score -= 5000  # Disqualify unknown authors
                logger.debug(f"Penalizing unknown author for query '{query_lower}' (-5000)")
            elif first_author and first_author in query_lower:
                score += 2000
                logger.debug(f"Author match: {first_author} in query (+2000)")
        
        logger.debug(f"Score for '{title}': {score}")
        return score

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

    async def _show_book_selection(
        self, interaction: discord.Interaction, books: List[OLBookMetadata], query: str = ""
    ):
        """Show selection of books, filtering to only show exact/close matches"""
        try:
            logger.debug(f"_show_book_selection called with {len(books)} books, query: {query}")
            
            # SCORING DISABLED - Just show all results as-is
            logger.info(f"Showing all {len(books)} raw API results (scoring disabled)")
            
            if not books:
                await interaction.response.send_message(
                    "❌ No books found.",
                    ephemeral=True
                )
                return
            
            # If we have only 1 result, just proceed directly
            if len(books) == 1:
                await self._show_book_request(interaction, books[0])
                return
            
            # Create a view with numbered buttons and pagination
            class BookSelectButtons(discord.ui.View):
                def __init__(self, cog_instance, books_list):
                    super().__init__(timeout=300)
                    self.cog = cog_instance
                    self.books_list = books_list
                    self.current_page = 0  # Page 0 = books 0-4, page 1 = books 5-9, etc
                    self.total_pages = (len(books_list) + 4) // 5  # Ceiling division
                    self.message = None
                
                def _get_current_books(self):
                    """Get the 5 books for current page"""
                    start = self.current_page * 5
                    end = start + 5
                    return self.books_list[start:end]
                
                def _build_embed(self):
                    """Build the embed for current page"""
                    current_books = self._get_current_books()
                    book_text = "**📚 Which book did you mean?**\n\n"
                    
                    for idx, book in enumerate(current_books, 1):
                        authors_str = ", ".join(book.authors) if book.authors else "Unknown"
                        year_str = f"{book.first_publish_year}" if book.first_publish_year else ""
                        
                        availability = []
                        if book.has_ebook:
                            availability.append("📖")
                        if book.has_audiobook:
                            availability.append("🎧")
                        avail_str = " " + " ".join(availability) if availability else ""
                        
                        book_text += f"{idx}. **{truncate_string(book.title, 70)}** by {truncate_string(authors_str, 40)}\n"
                        book_text += f"   ({year_str}){avail_str}\n\n"
                    
                    # Add pagination info
                    if self.total_pages > 1:
                        book_text += f"*Page {self.current_page + 1} of {self.total_pages}*"
                    
                    embed = discord.Embed(
                        description=book_text,
                        color=discord.Color.blue()
                    )
                    return embed
                
                def _update_button_states(self):
                    """Enable/disable prev/next buttons based on current page"""
                    prev_button = None
                    next_button = None
                    
                    for item in self.children:
                        if isinstance(item, discord.ui.Button):
                            if item.emoji and item.emoji.name == "arrow_left":
                                prev_button = item
                            elif item.emoji and item.emoji.name == "arrow_right":
                                next_button = item
                    
                    if prev_button:
                        prev_button.disabled = self.current_page == 0
                    if next_button:
                        next_button.disabled = self.current_page >= self.total_pages - 1
                
                @discord.ui.button(label="", style=discord.ButtonStyle.primary, emoji="1️⃣")
                async def button_1(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    await self._select_book(button_interaction, 0)
                
                @discord.ui.button(label="", style=discord.ButtonStyle.primary, emoji="2️⃣")
                async def button_2(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    await self._select_book(button_interaction, 1)
                
                @discord.ui.button(label="", style=discord.ButtonStyle.primary, emoji="3️⃣")
                async def button_3(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    await self._select_book(button_interaction, 2)
                
                @discord.ui.button(label="", style=discord.ButtonStyle.primary, emoji="4️⃣")
                async def button_4(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    await self._select_book(button_interaction, 3)
                
                @discord.ui.button(label="", style=discord.ButtonStyle.primary, emoji="5️⃣")
                async def button_5(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    await self._select_book(button_interaction, 4)
                
                @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀")
                async def button_prev(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if self.current_page > 0:
                        self.current_page -= 1
                        self._update_button_states()
                        await button_interaction.response.edit_message(
                            embed=self._build_embed(),
                            view=self
                        )
                    else:
                        await button_interaction.response.defer()
                
                @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶")
                async def button_next(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                    if self.current_page < self.total_pages - 1:
                        self.current_page += 1
                        self._update_button_states()
                        await button_interaction.response.edit_message(
                            embed=self._build_embed(),
                            view=self
                        )
                    else:
                        await button_interaction.response.defer()
                
                async def _select_book(self, button_interaction: discord.Interaction, relative_idx: int):
                    """Select a book from current page"""
                    try:
                        # Calculate absolute index in full books list
                        abs_idx = self.current_page * 5 + relative_idx
                        
                        if abs_idx >= len(self.books_list):
                            await button_interaction.response.defer()
                            return
                        
                        await button_interaction.response.defer()
                        selected_book = self.books_list[abs_idx]
                        
                        # Show request view for selected book, replacing the selection message
                        await self.cog._show_book_request(button_interaction, selected_book, self.message)
                        self.stop()
                    except Exception as e:
                        logger.error(f"Error in book selection: {e}", exc_info=True)
                        await button_interaction.followup.send(
                            f"❌ Error selecting book: {str(e)}",
                            ephemeral=True,
                        )
            
            # Create view and update button states
            view = BookSelectButtons(self, books)
            view._update_button_states()
            
            # Disable number buttons if there aren't enough books on current page
            current_books = view._get_current_books()
            for i in range(len(current_books), 5):
                if i < len(view.children) - 2:  # Don't disable prev/next buttons
                    view.children[i].disabled = True

            # Store the message in the view so we can edit it later
            view.message = await interaction.followup.send(
                embed=view._build_embed(),
                view=view,
            )

        except Exception as e:
            logger.error(f"Error in book selection: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error showing book options: {str(e)}",
                ephemeral=True,
            )

    async def _show_book_request(
        self, interaction: discord.Interaction, book: OLBookMetadata, selection_message: discord.Message = None
    ):
        """Show single book with request type buttons"""
        try:
            # Create book info embed
            embed = discord.Embed(
                title=f"📚 {book.title}",
                description=truncate_string(book.description, 500) if book.description else "*No synopsis available*",
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

            # Send or edit message with book info and request type buttons
            if selection_message:
                # Replace the selection message with book info
                message = await selection_message.edit(embed=embed, view=view)
            else:
                # Create new message if no selection message provided
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

            # Update the message with pending approval buttons
            pending_view = PendingApprovalView(book.title, request_type)
            try:
                await message.edit(view=pending_view)
            except Exception as e:
                logger.warning(f"Could not edit message: {e}")

            # Search Prowlarr for torrents
            # Clean the title - remove series info
            search_title = book.title.split(" - ")[0].split(" (")[0].strip()
            search_query = search_title
            if book.authors:
                search_query += f" {book.authors[0]}"

            logger.debug(f"Searching Prowlarr for {request_type}: {search_query}")

            if request_type == "audiobook":
                prowlarr_results = await search_audiobook(search_query, limit=Config.MAX_RESULTS)
            else:  # ebook
                prowlarr_results = await search_ebook(search_query, limit=Config.MAX_RESULTS)

            logger.debug(f"Prowlarr returned {len(prowlarr_results)} results for {request_type}")

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
                "isbn": book.isbn_13 or book.isbn_10,  # Store ISBN for completion tracking
            }

            # Send to admin channel for approval
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

            # Show available torrents info
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
        torrent: SearchResult,
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
                name="/request <title> [author]",
                value="Search for a book or audiobook\n"
                "- `title`: Book title (required)\n"
                "- `author`: Author name (optional, improves accuracy)",
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
                value="1. Use `/request` to search Google Books & Open Library\n"
                "2. Select the correct book from results\n"
                "3. Choose ebook or audiobook\n"
                "4. Admin approves the best torrent\n"
                "5. Download starts automatically & organizes when done",
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

    async def on_download_completed(self, torrent_name: str):
        """
        Called when a download is completed and organized
        Updates the user's message to show "Download Complete - Now Available"

        Args:
            torrent_name: Name of the completed torrent
        """
        try:
            logger.info(f"📚 Download completed: {torrent_name}")

            # Search through pending requests to find matching download
            for user_id, request_data in list(self.pending_requests.items()):
                try:
                    user = request_data.get("user")
                    user_message = request_data.get("message")
                    book = request_data.get("book")
                    request_type = request_data.get("request_type")
                    torrent = request_data.get("torrent")

                    if not user_message or not book:
                        continue

                    # Check if torrent name matches (partial match since names may vary)
                    if torrent_name.lower() in user_message.content.lower() or \
                       book.title.lower() in torrent_name.lower():
                        
                        logger.info(f"✅ Matched download to request: {book.title}")

                        # Update message with completion status
                        try:
                            # Use the original embed and update it
                            if user_message.embeds:
                                embed = user_message.embeds[0]
                                # Update description to show completion
                                embed.description = "✨ Download Complete - Now Available"
                                # Change color to gold
                                embed.color = discord.Color.gold()
                                
                                # Add or update the status field
                                # Remove old status field if exists
                                embed.remove_field(next((i for i, f in enumerate(embed.fields) if f.name == "Status"), -1))
                                
                                # Add completion status field at the end
                                embed.add_field(
                                    name="Status",
                                    value="✅ Download Complete - Now Available in Library",
                                    inline=False,
                                )
                            else:
                                # Fallback if no embed exists
                                embed = discord.Embed(
                                    title=book.title,
                                    description="✨ Download Complete - Now Available",
                                    color=discord.Color.gold(),
                                )
                                embed.add_field(
                                    name="Status",
                                    value="✅ Download Complete - Now Available in Library",
                                    inline=False,
                                )

                            # Update message (remove buttons, update status)
                            await user_message.edit(embed=embed, view=None)
                            logger.info(f"✅ Updated message for {user}: {book.title}")

                        except Exception as e:
                            logger.warning(f"Could not update message: {e}")

                        # Remove from pending since it's complete
                        del self.pending_requests[user_id]
                        break

                except Exception as e:
                    logger.warning(f"Error processing pending request for user {user_id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in on_download_completed: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    """
    Setup function for cog loading

    Args:
        bot: Discord bot instance
    """
    await bot.add_cog(LibrarianCommands(bot))
