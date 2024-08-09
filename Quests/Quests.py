from redbot.core import commands, Config
import discord
from discord.ext import tasks
import pandas as pd
from datetime import datetime
import pytz
import random

def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False
    return red_commands.permissions_check(predicate)
    
class Roles(red_commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=69312578, force_registration=True)
        self.config.register_guild(quests_channel_id=None)

    def cog_unload(self):
        self.send_daily_message.cancel()  # Stop the task if the cog is unloaded

    @tasks.loop(time=datetime.time(hour=12, tzinfo=pytz.timezone('America/New_York')))
    async def send_daily_message(self):
        # Replace CHANNEL_ID with the ID of the channel you want to send the message to
        channel = self.bot.get_channel(self.config.quests_channel_id())
        if channel:
            message = write_quest()
            await channel.send(message)
        else:
            print("Please set the quests channel id.")
            
    async def write_quest():
        """generate a quest announcement depending on the day and return it as a string to be sent by the bot"""
        day = datetime.now().strftime("%A").lower()
        games_by_day = pd.read_excel("games-by-day.csv")
        game_choices = games_by_day[day]
        game = game_choices[random.randint(0,len(games_choices)-1)]
        desc_locs = pd.read_excel("games-to-descs.csv)
        all_games = desc_locs['Game']
        all_locs = desc_locs['description location']
        loc = all_locs[all_games.index(game)]
        quest = ""
        with open(loc) as file:
            content_list = quest+=line for line in file.readlines()

        return quest
        
    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()  # Wait until the bot is ready

    @is_owner_overridable
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
