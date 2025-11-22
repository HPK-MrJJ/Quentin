import discord
from redbot.core import commands, Config

class ShareAttribution(commands.Cog):
    """Track deleted music/share messages and repost the sender."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=92837462873)
        self.config.register_global(log_channel=None)
        self.debug_mode = False

    # ----- Commands -----

    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(name="setsharelog")
    async def set_share_log(self, ctx, channel: discord.TextChannel):
        await self.config.log_channel.set(channel.id)
        await ctx.send(f"Log channel set to {channel.mention}")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(name="debugshare")
    async def debug_share(self, ctx):
        """Toggle debug mode to print embed data."""
        self.debug_mode = not self.debug_mode
        await ctx.send(f"Share debug mode: {'ON' if self.debug_mode else 'OFF'}")

    # ----- Listener -----

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        log_channel_id = await self.config.log_channel()
        if not log_channel_id:
            return

        if message.channel.id != log_channel_id:
            return

        if not message.embeds:
            return

        embed = message.embeds[0]
        desc = embed.description or ""

        if self.debug_mode:
            print("\n========== SHARE DEBUG ==========")
            print("Embed description:")
            print(repr(desc))
            print("=================================\n")

        # The logger bot puts everything inside the *description*
        lower = desc.lower()

        # Make sure it's actually a delete log message
        if "message deleted" not in lower:
            return

        # Extract user + channel from description lines
        user = None
        channel_name = None

        for line in desc.splitlines():
            line_lower = line.lower()

            if line_lower.startswith("user:"):
                user = line.split(":", 1)[1].strip()

            if line_lower.startswith("channel:"):
                raw = line.split(":", 1)[1].strip()
                raw = raw.lstrip("#").strip()
                channel_name = raw.replace(" ", "-")

        if not user or not channel_name:
            return

        # Find the actual channel
        target_channel = discord.utils.get(
            message.guild.text_channels,
            name=channel_name
        )

        if not target_channel:
            print("Could not find channel:", channel_name)
            return

        await target_channel.send(f"From {user}")
