import discord
from redbot.core import commands, Config

class ShareAttribution(commands.Cog):
    """Track deleted music/share messages and repost the sender."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=92837462873)
        self.config.register_global(log_channel=None)

    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(name="setsharelog")
    async def set_share_log(self, ctx, channel: discord.TextChannel):
        await self.config.log_channel.set(channel.id)
        await ctx.send(f"Log channel set to {channel.mention}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        log_channel_id = await self.config.log_channel()
        if not log_channel_id:
            return

        if message.channel.id != log_channel_id:
            return

        # no embeds? that's normal for UnbelievaBoat delete logs
        content = message.content or ""
        lower = content.lower()

        # must contain "message deleted"
        if "message deleted" not in lower:
            return

        # Try to extract "User: <value>"
        user = None
        channel_name = None

        lines = content.splitlines()

        for line in lines:
            if line.lower().startswith("user:"):
                user = line.split(":", 1)[1].strip()
            if line.lower().startswith("channel:"):
                # channel name may include # and words with spaces
                raw = line.split(":", 1)[1].strip()
                # remove the leading "#"
                raw = raw.lstrip("#").strip()
                # normalize spaces → hyphens to match Discord channel naming
                channel_name = raw.replace(" ", "-")

        if not user or not channel_name:
            return

        # find the actual channel
        target_channel = discord.utils.get(
            message.guild.text_channels,
            name=channel_name
        )

        if not target_channel:
            print("Could not find channel:", channel_name)
            return

        await target_channel.send(f"From {user}")
