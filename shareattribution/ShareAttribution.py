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

        if not message.embeds:
            return

        embed = message.embeds[0]

        # ---- DEBUG PRINTS ----
        print("==== NEW EMBED DETECTED ====")
        print("Title:", embed.title)
        print("Fields:")
        for f in embed.fields:
            print(" -", repr(f.name), ":", repr(f.value))
        print("============================")

        # Try looser matching:
        title = (embed.title or "").lower()
        if "deleted" not in title:
            return

        # Find anything containing "user"
        user_field = next(
            (f for f in embed.fields if "user" in f.name.lower()),
            None
        )

        # Find anything containing "channel"
        channel_field = next(
            (f for f in embed.fields if "channel" in f.name.lower()),
            None
        )

        if not user_field or not channel_field:
            print("User or Channel field NOT found.")
            return

        username = user_field.value.strip()

        # Channel field may contain multiple formats
        raw = channel_field.value
        cleaned_name = raw.split("[")[0].strip().lstrip("#").strip()
        cleaned_name = cleaned_name.replace(" ", "-")

        target_channel = discord.utils.get(message.guild.text_channels, name=cleaned_name)

        if not target_channel:
            print("Target channel not found:", cleaned_name)
            return

        await target_channel.send(f"From {username}")
