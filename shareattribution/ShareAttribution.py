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
        """Toggle debug mode to print raw delete-log messages."""
        self.debug_mode = not self.debug_mode
        await ctx.send(f"Share log debug mode: {'ON' if self.debug_mode else 'OFF'}")

    # ----- Listener -----

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        log_channel_id = await self.config.log_channel()
        if not log_channel_id:
            return

        # ignore other channels
        if message.channel.id != log_channel_id:
            return

        # DEBUG PRINTS
        if self.debug_mode:
            print("\n========== SHARE DEBUG ==========")
            print("RAW CONTENT:")
            print(repr(message.content))
            print("EMBEDS:", message.embeds)
            print("ATTACHMENTS:", message.attachments)
            print("=================================\n")

        # we do NOT try to parse until we know the format
        # after debug output, I can write the correct parser
