import os
import random
from datetime import datetime

import pandas as pd
import pytz
import aiofiles
import discord
from discord.ext import tasks

from redbot.core import commands, Config

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

    @tasks.loop(time=datetime.time(hour=18, tzinfo=pytz.timezone('America/New_York')))
    async def send_daily_message(self):
        channel_id = await self.config.quests_channel_id()
        channel = self.bot.get_channel(channel_id)
        if channel:
            message = await write_quest()
            await channel.send(message)
        else:
            print("Please set the quests channel id.")
            
    async def write_quest():
        """generate a quest announcement depending on the day and return it as a string to be sent by the bot"""
        day = datetime.now().strftime("%A").lower()
        games_by_day = pd.read_csv(os.path.join(os.path.dirname(__file__), "games-by-day.csv"))
        game_choices = games_by_day[day].dropna()
        game = game_choices.iloc[random.randint(0,len(game_choices)-1)]
        desc_locs = pd.read_csv(os.path.join(os.path.dirname(__file__), "games-to-descs.csv"))
        all_games = desc_locs['Game']
        all_locs = os.path.join(os.path.dirname(__file__), desc_locs['description location'])
        loc = all_locs[all_games.index(game)]
        quest = ""
        async with aiofiles.open(loc, mode='r') as file:
            for line in file.readlines():
                quest = await file.read()

        return quest
        
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
