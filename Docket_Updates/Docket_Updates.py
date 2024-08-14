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
        self.config = Config.get_conf(self, identifier=69318888, force_registration=True)
        self.config.register_guild(quests_channel_id=None)

    @tasks.loop(time=datetime.time(hour=12, tzinfo=pytz.timezone('America/New_York')))
    async def send_daily_message(self):
        channel_id = await self.config.quests_channel_id()
        channel = self.bot.get_channel(channel_id)
        if channel:
            new_stuff = await get_info()
            if new_stuff:
                await channel.send(new_stuff)
        else:
            print("Please set the quests channel id.")

    async def get_info():
        # soon to be written

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()  # Wait until the bot is ready

    @is_owner_overridable()
    @commands.command()
    async def set_channel_id(self, ctx, id: int):
        """Set the channel ID for daily messages."""
        await self.config.quests_channel_id.set(id)  # Save the channel ID to config
        await ctx.send(f"Quests channel set.")
         
    @commands.Cog.listener()
    async def on_message(self, message):
        if len(message.content) == 0:
            return
        first_char = message.content[0]
        ctx = await self.bot.get_context(message)
        if message.author.bot or not first_char.isalpha():
            return
