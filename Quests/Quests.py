import os
import random
import datetime
import asyncio

import pandas as pd
import aiofiles
import discord
from discord.ext import tasks

from redbot.core import commands, Config

def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False
    return commands.permissions_check(predicate)
    
class Quests(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=69312578, force_registration=True)
        self.config.register_guild(
            quests_channel_id=None,
            quests_role_id=None
        )
        self.send_daily_message.start()

    def cog_unload(self):
        self.send_daily_message.cancel()  # Stop the task if the cog is unloaded

    # @tasks.loop(time=datetime.time(hour=18))
    @tasks.loop(minutes=1)
    async def send_daily_message(self):
        print("Executing quest task")
        try:
            for guild in self.bot.guilds:  
                channel_id = await self.config.guild(guild).quests_channel_id()
                role_id = await self.config.guild(guild).quests_role_id()  # Fixed
    
                channel = self.bot.get_channel(channel_id)  # This line should be inside the loop
                if channel:
                    if role_id:
                        message = await self.write_quest()
                        await channel.send(message)
                    else:
                        print("Please set the quests role id.")
                else:
                    print("Please set the quests channel id.")
        except asynchio.CancelledError:
            print("Winding down the quest task.")
            raise
        except Exception as e:
            print(f"An error occured somewhere that makes me want to cry: {e}.")

    async def write_quest(self):
        """generate a quest announcement depending on the day and return it as a string to be sent by the bot"""
        day = datetime.datetime.now().strftime("%A").lower()
        games_by_day = pd.read_csv(os.path.join(os.path.dirname(__file__), "games-by-day.csv"))
        game_choices = games_by_day[day].dropna()
        game = game_choices.iloc[random.randint(0, len(game_choices)-1)]
        desc_locs = pd.read_csv(os.path.join(os.path.dirname(__file__), "games-to-descs.csv"))
        all_games = desc_locs['Game']
        all_locs = os.path.join(os.path.dirname(__file__), desc_locs['description location'])
        loc = os.path.join(os.path.dirname(__file__), all_locs[all_games.index(game)])
        quest = ""
        async with aiofiles.open(loc, mode='r') as file:
            quest = await file.read()  # Fixed the quest assignment logic

        return quest
        
    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()  # Wait until the bot is ready

    @is_owner_overridable()
    @commands.command()
    async def set_quest_channel_id(self, ctx, id: int):
        """Set the channel ID for daily quests."""
        await self.config.guild(ctx.guild).quests_channel_id.set(id)  # Fixed
        await ctx.send(f"Quests channel set.")

    @is_owner_overridable()
    @commands.command()
    async def set_role_id(self, ctx, id: str):
        """Set the role ID for daily messages."""
        await self.config.guild(ctx.guild).quests_role_id.set(id)  # Fixed
        await ctx.send(f"Quests role ID set.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if len(message.content) == 0:
          return
        first_char = message.content[0]
        ctx = await self.bot.get_context(message)
        if message.author.bot or not first_char.isalpha():
          return
