from redbot.core import commands, Config
import discord
from discord.ext import tasks
from datetime import datetime
import pytz

class Docket_Updates(red_commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    def cog_unload(self):
        self.send_daily_message.cancel()  # Stop the task if the cog is unloaded

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()  # Wait until the bot is ready

    @commands.Cog.listener()
    async def on_message(self, message):
        if len(message.content) == 0:
            return
        first_char = message.content[0]
        ctx = await self.bot.get_context(message)
        if message.author.bot or not first_char.isalpha():
            return
