import discord
import re
from redbot.core import commands, Config

class ShareAttribution(commands.Cog):
    """Tracks deleted share messages and reposts who sent them."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=92837462873)
        self.config.register_global(log_channel=None)
        self.debug_mode = False

    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(name="setsharelog")
    async def set_share_log(self, ctx, channel: discord.TextChannel):
        await self.config.log_channel.set(channel.id)
        await ctx.send(f"Share log channel set to {channel.mention}")

    @commands.admin_or_permissions(manage_guild=True)
    @commands.command(name="debugshare")
    async def debug_share(self, ctx):
        self.debug_mode = not self.debug_mode
        await ctx.send(f"Share debug mode: {'ON' if self.debug_mode else 'OFF'}")

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

        # Only activate on real delete-log messages
        if "**User:**" not in desc or "**Channel:**" not in desc:
            return

        lines = desc.splitlines()
        user = None
        channel_name = None

        # regex to find text inside backticks: `text`
        backtick_re = re.compile(r"`([^`]+)`")

        for line in lines:
            lower = line.lower()

            if lower.startswith("**user:**"):
                # extract the backticked readable name
                m = backtick_re.search(line)
                if m:
                    user = m.group(1).strip()
                else:
                    # fallback: use entire line
                    user = line.replace("**User:**", "").strip()

            if lower.startswith("**channel:**"):
                m = backtick_re.search(line)
                if m:
                    raw = m.group(1).strip()   # e.g. "[#beyond-the-veil]"
                    raw = raw.strip("[]")      # remove literal square brackets
                    raw = raw.lstrip("#")      # remove the Discord hashtag
                    channel_name = raw.strip() # final clean name


        if not user or not channel_name:
            return

        # find target channel
        target_channel = discord.utils.get(
            message.guild.text_channels,
            name=channel_name
        )

        if not target_channel:
            print("Target channel not found:", channel_name)
            return

        await target_channel.send(f"From {user}")
