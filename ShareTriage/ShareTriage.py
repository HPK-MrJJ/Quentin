import re
from redbot.core import commands, Config
import discord

URL_RE = re.compile(
    r"(https?://[^\s]+)", 
    flags=re.IGNORECASE
)

# Remove tracking parameters like si=
TRACKING_PARAMS = {"si", "sp", "share", "feature", "fbclid", "igsh", "si"}
# (Add or remove params as needed)


class ShareTriage(commands.Cog):
    """Fallback share-fixing system."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=84693112)
        self.config.register_guild(triage=False)

    # ─────────────────────────────────────────────
    # TOGGLE COMMANDS
    # ─────────────────────────────────────────────
    @commands.group()
    @commands.admin_or_permissions(manage_guild=True)
    async def triage(self, ctx):
        """Enable/disable emergency share triage."""
        pass

    @triage.command()
    async def on(self, ctx):
        await self.config.guild(ctx.guild).triage.set(True)
        await ctx.send("✔ Triage mode **enabled** — I’ll sanitize shared links.")

    @triage.command()
    async def off(self, ctx):
        await self.config.guild(ctx.guild).triage.set(False)
        await ctx.send("✖ Triage mode **disabled**.")

    # ─────────────────────────────────────────────
    # TRIAGE MESSAGE LISTENER
    # ─────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        # Ignore bots, DMs, and messages without URLs
        if message.author.bot or not message.guild:
            return

        guild_config = await self.config.guild(message.guild).triage()
        if not guild_config:
            return

        urls = URL_RE.findall(message.content)
        if not urls:
            return

        cleaned_any = False
        cleaned_content = message.content

        # Clean each URL
        for url in urls:
            if "?si=" in url or "&si=" in url or "?share" in url:
                cleaned_any = True
                cleaned = self.clean_url(url)
                cleaned_content = cleaned_content.replace(url, cleaned)

        if not cleaned_any:
            return  # Nothing needed

        # Delete original message
        try:
            await message.delete()
        except discord.Forbidden:
            return

        # Repost corrected content
        final_text = f"**From {message.author.mention}:**\n{cleaned_content}"

        await message.channel.send(final_text)

    # ─────────────────────────────────────────────
    # URL CLEANING
    # ─────────────────────────────────────────────
    def clean_url(self, url: str) -> str:
        """
        Remove tracking/share parameters from a URL
        e.g. ?si=xxxxx or &si=xxxxx or &feature=share
        """
        if "?" not in url:
            return url

        base, query = url.split("?", 1)

        # Break params apart
        parts = []
        for param in query.split("&"):
            key = param.split("=")[0].lower()
            if key not in TRACKING_PARAMS:
                parts.append(param)

        if not parts:
            return base

        return base + "?" + "&".join(parts)
