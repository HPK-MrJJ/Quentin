import re
from redbot.core import commands, Config
import discord

URL_RE = re.compile(r"(https?://[^\s]+)", flags=re.IGNORECASE)

TRACKING_PARAMS = {
    "si", "sp", "share", "feature", "fbclid", "igsh", "utm_source",
    "utm_medium", "utm_campaign"
}

class ShareTriage(commands.Cog):
    """Fallback link cleaner when NoDoxx is down."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_guild(triage=False)

    # ─────────────────────────────────────────────
    # TOGGLE
    # ─────────────────────────────────────────────
    @commands.group()
    @commands.admin_or_permissions(manage_guild=True)
    async def triage(self, ctx):
        """Enable/disable fallback link cleaning."""
        pass

    @triage.command()
    async def on(self, ctx):
        await self.config.guild(ctx.guild).triage.set(True)
        await ctx.send("✔ Triage mode enabled.")

    @triage.command()
    async def off(self, ctx):
        await self.config.guild(ctx.guild).triage.set(False)
        await ctx.send("✖ Triage mode disabled.")

    # ─────────────────────────────────────────────
    # LISTENER
    # ─────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        if message.author.bot or not message.guild:
            return

        triage_enabled = await self.config.guild(message.guild).triage()
        if not triage_enabled:
            return  # ← YES, defaults OFF

        urls = URL_RE.findall(message.content)
        if not urls:
            return

        cleaned_any = False
        cleaned_content = message.content

        for url in urls:
            cleaned = self.clean_url(url)
            if cleaned != url:
                cleaned_any = True
                cleaned_content = cleaned_content.replace(url, cleaned)

        if not cleaned_any:
            return

        # Remove original
        try:
            await message.delete()
        except discord.Forbidden:
            return

        # Repost cleaned version ONLY — your other cog handles attribution
        await message.channel.send(cleaned_content)

    # ─────────────────────────────────────────────
    # URL CLEANER
    # ─────────────────────────────────────────────
    def clean_url(self, url: str) -> str:
        """
        Removes tracking params like ?si=… &si=… etc.
        Keeps the rest of the URL as-is.
        """
        if "?" not in url:
            return url

        base, query = url.split("?", 1)
        new_params = []

        for p in query.split("&"):
            key = p.split("=")[0].lower()
            if key not in TRACKING_PARAMS:
                new_params.append(p)

        # No params left?
        if not new_params:
            return base

        return base + "?" + "&".join(new_params)
