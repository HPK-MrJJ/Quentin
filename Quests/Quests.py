import os
import random
import asyncio
from datetime, import datetime, timedelta

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
            quests_role_id=None,
            quest_count=0,
            current_quest=None
        )
        self.send_daily_message.start()

    def cog_unload(self):
        self.send_daily_message.cancel()  # Stop the task if the cog is unloaded

    @tasks.loop(time=datetime.time(hour=18))
    # @tasks.loop(minutes=1)
    async def send_daily_message(self):
        print("Executing quest task")
        try:
            for guild in self.bot.guilds:  
                channel_id = await self.config.guild(guild).quests_channel_id()
                role_id = await self.config.guild(guild).quests_role_id() 
                quest_count = await self.config.guild(guild).quest_count()
    
                channel = self.bot.get_channel(channel_id)  
                if channel:
                    if role_id:
                        duple = await self.write_quest()
                        message = duple[1]
                        await channel.send(f"<@&{role_id}>\n{message}")
                        await self.config.guild(ctx.guild).quests_count.set(quest_count+1)
                        await self.config.guild(ctx.guild).current_quest.set(duple[0])
                    else:
                        print("Please set the quests role id.")
                else:
                    print("Please set the quests channel id.")
        except asyncio.CancelledError:
            print("Winding down the quest task.")
            raise
        except Exception as e:
            print(f"An error occured somewhere that makes me want to cry: {e}.")

    async def write_quest(self):
        """Generate a quest announcement depending on the day and return it as a string to be sent by the bot"""
        day = datetime.now().strftime("%A").lower()
        
        # Read the games for the day
        games_by_day = pd.read_csv(os.path.join(os.path.dirname(__file__), "games-by-day.csv"))
        game_choices = games_by_day[day].dropna()
        game = game_choices.iloc[random.randint(0, len(game_choices) - 1)]  # Choose a random game
        
        # Read the descriptions
        desc_locs = pd.read_csv(os.path.join(os.path.dirname(__file__), "games-to-descs.csv"))
        
        # Get the location corresponding to the chosen game
        game_index = desc_locs[desc_locs['Game'] == game].index[0]
        description_location = desc_locs.at[game_index, 'description location']
        
        # Build the full path to the description file
        loc = os.path.join(os.path.dirname(__file__), description_location)
        
        # Read the quest description from the file
        quest = ""
        async with aiofiles.open(loc, mode='r') as file:
            quest = await file.read()
    
        return [game, quest]
        
    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()  # Wait until the bot is ready

    @tasks.loop(time=datetime.time(hour=17, minute=59))
    async def score_quests(self):
        """go through all the messages posted in the quest channel since the last quest was posted
        and score them based off of whatever the quest was and react with :white_check_mark: to the ones scored.
        Then store the scores temporarily in a config by username, faction, score and post a txt of that list of scores in the quests channel.
        After the txt is posted, use the config to add the scores from each player to their respective faction (need some more configs to store faction scores),
        Then clear the config."""
        for guild in self.bot.guilds:
            count = await self.config.guild(guild).quest_count()
            channel_id = await self.config.guild(guild).quests_channel_id()
            if count > 0:
                self.fetch_messages(channel_id)

    async def fetch_messages(self, channel_id):
        """get the messages that need scoring and send them to the scoring method"""
        channel = self.bot.get_channel(channel_id)
        last_quest = datetime.now() - timedelta(hours=23, minutes=59)
        current_quest = await self.config.guild(guild).current_quest()
        async for message in channel.history(after=last_quest):
            if self.scored(message, str(current_quest)): #the scored method scores the message and returns true if it scored, otherwise false
                await self.bot.add_reaction(message, :white_check_mark:)

    async def scored(message: discord.Message, quest_name: str):
        """direct the program to the right method to score the quest of the day"""
        quest_name = lower(quest_name)
        if quest_name == '2048':
            return self.number_game_score(message)
        elif quest_name == 'worLdle':
            return self.worLdle_score(message)
        elif quest_name == 'globle':
            return self.globle_score(message)
        elif quest_name == 'globle-capitals':
            return self.globleC_score(message)
        elif quest_name == 'map-game':
            return self.map_game_score(message)
        elif quest_name == 'dinosaur game':
            return self.dino_score(message)
        elif quest_name == 'edge surfer':
            return self.edge_surf_score(message)
        elif quest_name == 'hole.io':
            return self.holeio_score(message)
        elif quest_name == 'agar.io':
            return self.agario_score(message)
        elif quest_name == 'slither.io':
            return self.slitherio_score(message)
        elif quest_name == 'wordle':
            return self.wordle_score(message)
        elif quest_name == 'spelling bee':
            return self.spell_bee_score(message)
        elif quest_name == 'connections':
            return self.connections_score(message)
        elif quest_name == 'semantle':
            return self.semantle_score(message)
        elif quest_name == 'tetr.io':
            return self.tetrio_score(message)
        elif quest_name == 'suika game':
            return self.suika_score(message)
        elif quest_name == 'bandle':
            return self.bandle_score(message)
        else:
            print("Yer about to get some mad errors, bro.")

    async def number_game_score(message: discord.Message):
        # so it begins

    @is_owner_overridable()
    @commands.command()
    async def set_quest_channel_id(self, ctx, id: int):
        """Set the channel ID for daily quests."""
        await self.config.guild(ctx.guild).quests_channel_id.set(id)  
        await ctx.send(f"Quests channel set.")

    @is_owner_overridable()
    @commands.command()
    async def set_role_id(self, ctx, id: str):
        """Set the role ID for daily messages."""
        await self.config.guild(ctx.guild).quests_role_id.set(id) 
        await ctx.send(f"Quests role ID set.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if len(message.content) == 0:
          return
        
        first_char = message.content[0]
        if message.author.bot or not first_char.isalpha():
          return
