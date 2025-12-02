"""
Discord UI components (Views, Buttons, Selects)
Interactive Discord interface elements
"""

import logging
from typing import Optional, Callable, List, Any
import discord
from discord import ui, Interaction, Embed, Color
from discord.ext import commands

logger = logging.getLogger(__name__)


class ApprovalView(ui.View):
    """View for approval/denial buttons"""

    def __init__(
        self,
        on_approve: Optional[Callable] = None,
        on_deny: Optional[Callable] = None,
        timeout: int = 600,
    ):
        """
        Initialize approval view

        Args:
            on_approve: Callback when approved (can be async)
            on_deny: Callback when denied (can be async)
            timeout: How long view stays active (seconds)
        """
        super().__init__(timeout=timeout)
        self.on_approve = on_approve
        self.on_deny = on_deny
        self.result = None

    @ui.button(label="✅ Approve", style=discord.ButtonStyle.green)
    async def approve_button(self, interaction: Interaction, button: ui.Button):
        """Approve button handler"""
        try:
            if self.on_approve:
                result = self.on_approve(interaction)
                # Handle both sync and async callbacks
                if hasattr(result, "__await__"):
                    await result

            self.result = "approved"
            await interaction.response.defer()
            self.stop()

        except Exception as e:
            logger.error(f"Error in approve button: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing approval",
                ephemeral=True,
            )

    @ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny_button(self, interaction: Interaction, button: ui.Button):
        """Deny button handler"""
        try:
            if self.on_deny:
                result = self.on_deny(interaction)
                # Handle both sync and async callbacks
                if hasattr(result, "__await__"):
                    await result

            self.result = "denied"
            await interaction.response.defer()
            self.stop()

        except Exception as e:
            logger.error(f"Error in deny button: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing denial",
                ephemeral=True,
            )


class SearchResultSelect(ui.Select):
    """Dropdown for selecting search results"""

    def __init__(
        self,
        results: List[dict],
        on_select: Optional[Callable] = None,
        placeholder: str = "Select a result...",
    ):
        """
        Initialize search result select

        Args:
            results: List of search result dicts
            on_select: Callback when result selected (can be async)
            placeholder: Placeholder text
        """
        # Create options from results
        options = []
        for idx, result in enumerate(results[:25], 1):  # Discord max 25 options
            # Truncate title to fit Discord limits
            title = result.get("title", f"Result {idx}")[:100]
            indexer = result.get("indexer", "Unknown")[:10]
            seeders = result.get("seeders", 0)

            option = discord.SelectOption(
                label=f"{idx}. {title[:90]}",
                description=f"{indexer} • {seeders} seeds",
                value=str(idx - 1),  # Use index as value
            )
            options.append(option)

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
        )

        self.results = results
        self.on_select = on_select

    async def callback(self, interaction: Interaction):
        """Handle selection"""
        try:
            selected_idx = int(self.values[0])
            selected_result = self.results[selected_idx]

            if self.on_select:
                result = self.on_select(interaction, selected_result, selected_idx)
                # Handle both sync and async callbacks
                if hasattr(result, "__await__"):
                    await result

        except Exception as e:
            logger.error(f"Error in search result select: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing selection",
                ephemeral=True,
            )


class SearchResultsView(ui.View):
    """View containing search results dropdown"""

    def __init__(
        self,
        results: List[dict],
        on_select: Optional[Callable] = None,
        timeout: int = 300,
    ):
        """
        Initialize search results view

        Args:
            results: List of search result dicts
            on_select: Callback when result selected
            timeout: How long view stays active (seconds)
        """
        super().__init__(timeout=timeout)
        self.results = results
        self.selected_result = None

        select = SearchResultSelect(
            results,
            on_select=self._on_select,
        )
        self.add_item(select)
        self.on_select = on_select

    async def _on_select(self, interaction: Interaction, result: dict, idx: int):
        """Internal select handler"""
        self.selected_result = result
        await interaction.response.defer()

        if self.on_select:
            result_coro = self.on_select(interaction, result, idx)
            # Handle both sync and async callbacks
            if hasattr(result_coro, "__await__"):
                await result_coro

        self.stop()


class PaginatedView(ui.View):
    """View for paginated content"""

    def __init__(
        self,
        pages: List[Embed],
        timeout: int = 300,
    ):
        """
        Initialize paginated view

        Args:
            pages: List of Discord Embeds
            timeout: How long view stays active (seconds)
        """
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        """Update button states based on current page"""
        is_first = self.current_page == 0
        is_last = self.current_page >= len(self.pages) - 1

        self.children[0].disabled = is_first  # Previous button
        self.children[1].disabled = is_last   # Next button

    @ui.button(label="⬅️", style=discord.ButtonStyle.gray)
    async def previous_page(self, interaction: Interaction, button: ui.Button):
        """Go to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(
                embed=self.pages[self.current_page], view=self
            )
        else:
            await interaction.response.defer()

    @ui.button(label="➡️", style=discord.ButtonStyle.gray)
    async def next_page(self, interaction: Interaction, button: ui.Button):
        """Go to next page"""
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(
                embed=self.pages[self.current_page], view=self
            )
        else:
            await interaction.response.defer()

    @ui.button(label="❌", style=discord.ButtonStyle.red)
    async def close_pages(self, interaction: Interaction, button: ui.Button):
        """Close pagination"""
        await interaction.response.defer()
        self.stop()


class ConfirmView(ui.View):
    """Simple Yes/No confirmation view"""

    def __init__(
        self,
        on_confirm: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
        timeout: int = 300,
    ):
        """
        Initialize confirmation view

        Args:
            on_confirm: Callback on confirm (can be async)
            on_cancel: Callback on cancel (can be async)
            timeout: How long view stays active (seconds)
        """
        super().__init__(timeout=timeout)
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.result = None

    @ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: ui.Button):
        """Confirm button"""
        try:
            self.result = True

            if self.on_confirm:
                result = self.on_confirm(interaction)
                if hasattr(result, "__await__"):
                    await result

            await interaction.response.defer()
            self.stop()

        except Exception as e:
            logger.error(f"Error in confirm button: {e}")
            await interaction.response.send_message(
                "❌ An error occurred",
                ephemeral=True,
            )

    @ui.button(label="No", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        """Cancel button"""
        try:
            self.result = False

            if self.on_cancel:
                result = self.on_cancel(interaction)
                if hasattr(result, "__await__"):
                    await result

            await interaction.response.defer()
            self.stop()

        except Exception as e:
            logger.error(f"Error in cancel button: {e}")
            await interaction.response.send_message(
                "❌ An error occurred",
                ephemeral=True,
            )


class RoleCheckView(ui.View):
    """View that checks if user has required role"""

    def __init__(
        self,
        required_role: str,
        timeout: int = 300,
    ):
        """
        Initialize role check view

        Args:
            required_role: Role name required to interact
            timeout: How long view stays active (seconds)
        """
        super().__init__(timeout=timeout)
        self.required_role = required_role

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Check if user has required role"""
        user_roles = [role.name for role in interaction.user.roles]

        if self.required_role not in user_roles and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                f"❌ You need the `{self.required_role}` role to use this button",
                ephemeral=True,
            )
            return False

        return True


class AdminApprovalView(RoleCheckView):
    """Approval view with admin role check"""

    def __init__(
        self,
        required_role: str = "Admin",
        on_approve: Optional[Callable] = None,
        on_deny: Optional[Callable] = None,
        timeout: int = 600,
    ):
        """
        Initialize admin approval view

        Args:
            required_role: Admin role required
            on_approve: Callback on approve
            on_deny: Callback on deny
            timeout: How long view stays active (seconds)
        """
        super().__init__(required_role=required_role, timeout=timeout)
        self.on_approve = on_approve
        self.on_deny = on_deny
        self.result = None

        # Add approval buttons
        self.add_item(ApprovalButton(self, is_approve=True))
        self.add_item(ApprovalButton(self, is_approve=False))

    async def handle_approve(self, interaction: Interaction):
        """Handle approval"""
        try:
            if self.on_approve:
                result = self.on_approve(interaction)
                if hasattr(result, "__await__"):
                    await result

            self.result = "approved"
            self.stop()

        except Exception as e:
            logger.error(f"Error handling approval: {e}")
            raise

    async def handle_deny(self, interaction: Interaction):
        """Handle denial"""
        try:
            if self.on_deny:
                result = self.on_deny(interaction)
                if hasattr(result, "__await__"):
                    await result

            self.result = "denied"
            self.stop()

        except Exception as e:
            logger.error(f"Error handling denial: {e}")
            raise


class ApprovalButton(ui.Button):
    """Individual approval/denial button"""

    def __init__(self, view: AdminApprovalView, is_approve: bool):
        """
        Initialize button

        Args:
            view: Parent AdminApprovalView
            is_approve: True for approve, False for deny
        """
        if is_approve:
            super().__init__(label="✅ Approve", style=discord.ButtonStyle.green)
            self.is_approve = True
        else:
            super().__init__(label="❌ Deny", style=discord.ButtonStyle.red)
            self.is_approve = False

        self.view = view

    async def callback(self, interaction: Interaction):
        """Handle button click"""
        try:
            # Role check is done by view's interaction_check
            if self.is_approve:
                await self.view.handle_approve(interaction)
                await interaction.response.defer()
            else:
                await self.view.handle_deny(interaction)
                await interaction.response.defer()

        except Exception as e:
            logger.error(f"Error in approval button callback: {e}")
            await interaction.response.send_message(
                "❌ An error occurred processing your response",
                ephemeral=True,
            )
