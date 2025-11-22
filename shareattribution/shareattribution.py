import discord
from redbot.core import commands, Config

class ShareAttribution(commands.Cog):
    """Track deleted music/share messages and repost the sender."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=92837462873)
        self.config.register_global(log_channel=None)

    # ----- Commands -----

    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(name="setsharelog")
    async def set_share_log(self, ctx, channel: discord.TextChannel):
        """Set the message-delete log channel to monitor."""
        await self.config.log_channel.set(channel.id)
        await ctx.send(f"Share attribution log channel set to: {channel.mention}")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(name="clearsharelog")
    async def clear_share_log(self, ctx):
        """Clear the log channel."""
        await self.config.log_channel.set(None)
        await ctx.send("Share attribution log channel cleared.")

    # ----- Listener -----

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        log_channel_id = await self.config.log_channel()
        if not log_channel_id:
            return

        # Not the log channel → ignore
        if message.channel.id != log_channel_id:
            return

        # Must contain an embed
        if not message.embeds:
            return

        embed = message.embeds[0]

        # We only care about "Message Deleted" embeds
        if embed.title != "Message Deleted":
            return

        # Extract fields
        user_field = next((f for f in embed.fields if f.name.lower() == "user:"), None)
        channel_field = next((f for f in embed.fields if f.name.lower() == "channel:"), None)

        if not user_field or not channel_field:
            return

        # Username (may include the mention)
        username_raw = user_field.value.strip()

        # Channel value looks like "# classic-alt-progressive [#classic-alt-progressive]"
        channel_name = channel_field.value.split("[")[0].strip().lstrip("#").strip()
        target_channel = discord.utils.get(message.guild.text_channels, name=channel_name)

        if not target_channel:
            return  # Channel might not exist

        # Send attribution:
        await target_channel.send(f"From {username_raw}")
