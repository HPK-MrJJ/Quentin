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
    
        # ignore bots except logger bot embeds
        if not message.embeds or message.author.bot is False:
            return
    
        embed = message.embeds[0]
    
        # ----- NEW: Ignore "Message Edited" logs -----
        title = (embed.title or "").lower()
        author_name = (embed.author.name or "").lower()
    
        # Only process deleted-message logs
        if "deleted" not in title and "deleted" not in author_name:
            return
        # ---------------------------------------------
    
        # Existing extraction logic below this line
        desc = embed.description or ""
        title_text = embed.title or ""
        fields = " ".join(f"{f.name} {f.value}" for f in embed.fields)
        combined = f"{title_text}\n{desc}\n{fields}"
    
        # Only proceed if the embed contains a link
        if "http://" not in combined and "https://" not in combined:
            return
    
        user_id = None
        channel_id = None
    
        # Find <@123456789>
        m_user = re.search(r"<@!?(\d+)>", combined)
        if m_user:
            user_id = int(m_user.group(1))
    
        # Find <#123456789>
        m_channel = re.search(r"<#(\d+)>", combined)
        if m_channel:
            channel_id = int(m_channel.group(1))
    
        # If we didn't find both, skip
        if not user_id or not channel_id:
            return
    
        target_channel = message.guild.get_channel(channel_id)
        if not target_channel:
            print(f"[sharebot] Channel not found: {channel_id}")
            return
    
        # Build username text if possible
        member = message.guild.get_member(user_id)
        if member:
            from_text = f"From **{member.display_name}**"
        else:
            from_text = f"From <@{user_id}>"
    
        # Send the attribution message
        await target_channel.send(from_text)
