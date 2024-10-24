import os
import random
import asyncio
from datetime, import datetime, timedelta

import re
import pandas as pd
import aiohttp
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
            current_quest=None,
            api_key=None
            ferelden=discord.utils.get(ctx.guild.roles, name='Ferelden'),
            anderfels=discord.utils.get(ctx.guild.roles, name='Anderfels'),
            nevarra=discord.utils.get(ctx.guild.roles, name='Nevarra'),
            orlais=discord.utils.get(ctx.guild.roles, name='Orlais'),
            tevinter=discord.utils.get(ctx.guild.roles, name='Tevinter'),
            ferelden_score=0,
            anderfels_score=0,
            nevarra_score=0,
            orlais_score=0,
            tevinter_score=0,
            score_log=[]
        )
        self.send_daily_message.start()

    def cog_unload(self):
        self.send_daily_message.cancel()  # Stop the task if the cog is unloaded

    async def ocr(self, url):
        url = 'https://api.ocr.space/parse/image'
        api_key = await self.config.guild(guild).api_key()
        
        # Payload for the OCR API
        payload = {
            'apikey': api_key,
            'url': url,
            'language': 'eng',
            'isOverlayRequired': False,
        }
    
        # Making the async request
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload) as response:
                if response.status != 200:
                    raise Exception(f"Error: API request failed with status code {response.status}")
                
                # Parse the JSON response
                result = await response.json()
                
                if result['IsErroredOnProcessing']:
                    raise Exception(result['ErrorMessage'][0])
    
                return result['ParsedResults']

    @tasks.loop(time=datetime.time(hour=18))
    # @tasks.loop(minutes=1)
    async def send_daily_message(self):
        print("Executing quest task")
        try:
            for guild in self.bot.guilds:  
                channel_id = await self.config.guild(guild).quests_channel_id()
                role_id = await self.config.guild(guild).quests_role_id() 
                quest_count = await self.config.guild(guild).quest_count()
                api_key = await self.config.guild(guild).api_key()
    
                channel = self.bot.get_channel(channel_id)
                if api_key:
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
                else:
                    print("Please set the OCR API key.")
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
        await self.bot.wait_until_ready() 

    @score_quests.before_loop
    async def before_score_quest(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=datetime.time(hour=17, minute=59))
    async def score_quests(self):
        """start the scoring process if there are quests to score"""
        for guild in self.bot.guilds:
            self.config.guild(guild).score_log.set([]) # clear the score log before starting each scoring cycle
            count = await self.config.guild(guild).quest_count()
            channel_id = await self.config.guild(guild).quests_channel_id()
            if count > 0:
                self.fetch_messages(channel_id, guild)

    async def fetch_messages(self, channel_id, guild):
        """get the messages that need scoring and send them to the scoring method"""
        channel = self.bot.get_channel(channel_id)
        last_quest = datetime.now() - timedelta(hours=23, minutes=59)
        current_quest = await self.config.guild(guild).current_quest()
        async for message in channel.history(after=last_quest):
            if self.scored(guild, message, str(current_quest)): #the scored method scores the message and returns true if it scored, otherwise false
                await self.bot.add_reaction(message, :white_check_mark:)

    async def scored(guild, message: discord.Message, quest_name: str):
        """direct the program to the right method to score the quest of the day"""
        quest_name = lower(quest_name)
        if quest_name == '2048':
            return self.number_game_score(guild, message)
        elif quest_name == 'worldle':
            return self.worLdle_score(guild, message)
        elif 'globle' in quest_name: # score globle and globle-capital the same way
            return self.globle_score(guild, message)
        elif quest_name == 'dinosaur game':
            return self.dino_score(guild, message)
        elif quest_name == 'edge surfer':
            return self.edge_surf_score(guild, message)
        elif quest_name == 'hole.io':
            return self.holeio_score(guild, message)
        elif quest_name == 'agar.io':
            return self.agario_score(guild, message)
        elif quest_name == 'slither.io':
            return self.slitherio_score(guild, message)
        elif quest_name == 'wordle':
            return self.wordle_score(guild, message)
        elif quest_name == 'spelling bee':
            return self.spell_bee_score(guild, message)
        elif quest_name == 'connections':
            return self.connections_score(guild, message)
        elif quest_name == 'semantle':
            return self.semantle_score(guild, message)
        elif quest_name == 'tetr.io':
            return self.tetrio_score(guild, message)
        elif quest_name == 'suika game':
            return self.suika_score(guild, message)
        elif quest_name == 'bandle':
            return self.bandle_score(guild, message)
        else:
            return False

    async def number_game_score(self, guild: discord.Guild, message: discord.Message):
        dkp = 0
        attachments = message.attachments
        if len(attachments) != 1:
            return False
        image = attachments[0]
        image_contents = self.ocr(attachment.url)
        
        pattern = r'SCORE\r\n([0-9]+)'
        match = re.search(pattern, text)
    
        if match:
            score = int(match)
            if score < 2500:
                dkp = 3
            elif score < 5000:
                dkp = 5
            else:
                dkp = 10
                
            f = await self.config.guild(guild).ferelden()
            a = await self.config.guild(guild).anderfels()
            n = await self.config.guild(guild).nevarra()
            o = await self.config.guild(guild).orlais()
            t = await self.config.guild(guild).tevinder()
    
            if f in message.author.roles:
                await self.count_score('ferelden', dkp, guild)
                return True
            elif a in message.author.roles:
                await self.count_score('anderfels', dkp, guild)
                return True
            elif n in message.author.roles:
                await self.count_score('nevarra', dkp, guild)
                return True
            elif o in message.author.roles:
                await self.count_score('orlais', dkp, guild)
                return True
            elif t in message.author.roles:
                await self.count_score('tevinder', dkp, guild)
                return True
            else:
                return False
                
        else:
            return False

    async def worLdle_score(self, guild: discord.Guild, message: discord.Message):
        dkp = 0
        contents = message.content
        
        pattern = r'\)\s(\d)/6\s\('
        match = re.search(pattern, content)
        
        if match:
            score = int(match.group(1))
            if score == 1:
                dkp = 10
            elif score == 2 or score == 3:
                dkp = 5
            else:
                dkp = 2

            if ':compass:' in contents:
                dkp += 1
            if ':star:' in contents:
                dkp += 1
            if ':triangular_flag_on_post:' in contents:
                dkp += 1
            if ':abc:' in contents:
                dkp += 1
            if ':couple:' in contents:
                dkp += 1
            if ':coin:' in contents:
                dkp += 1
            if ':speaking_head:' in contents:
                dkp += 1
            if ':triangular_ruler:' in contents:
                dkp += 1
            if ':cityscapes:' in contents:
                dkp += 1
                
            f = await self.config.guild(guild).ferelden()
            a = await self.config.guild(guild).anderfels()
            n = await self.config.guild(guild).nevarra()
            o = await self.config.guild(guild).orlais()
            t = await self.config.guild(guild).tevinder()
    
            if f in message.author.roles:
                await self.count_score('ferelden', dkp, guild)
                return True
            elif a in message.author.roles:
                await self.count_score('anderfels', dkp, guild)
                return True
            elif n in message.author.roles:
                await self.count_score('nevarra', dkp, guild)
                return True
            elif o in message.author.roles:
                await self.count_score('orlais', dkp, guild)
                return True
            elif t in message.author.roles:
                await self.count_score('tevinder', dkp, guild)
                return True
            else:
                return False
                
        else:
            return False

    async def globle_score(self, guild: discord.Guild, message: discord.Message):
        dkp = 0
        content = message.content

        pattern = r'_square:\s*=\s*(\d+)'
        match = re.search(pattern, content)

        if match:
            
            score = int(match.group(1))
            if score <= 5:
                dkp = 5
            elif score <= 10:
                dkp = 3
            else:
                dkp = 1

            f = await self.config.guild(guild).ferelden()
            a = await self.config.guild(guild).anderfels()
            n = await self.config.guild(guild).nevarra()
            o = await self.config.guild(guild).orlais()
            t = await self.config.guild(guild).tevinder()
    
            if f in message.author.roles:
                await self.count_score('ferelden', dkp, guild)
                return True
            elif a in message.author.roles:
                await self.count_score('anderfels', dkp, guild)
                return True
            elif n in message.author.roles:
                await self.count_score('nevarra', dkp, guild)
                return True
            elif o in message.author.roles:
                await self.count_score('orlais', dkp, guild)
                return True
            elif t in message.author.roles:
                await self.count_score('tevinder', dkp, guild)
                return True
            else:
                return False
                
        else:
            return False

    async def count_score(faction, score, guild):
        if faction == 'ferelden':
            faction_score = await self.config.guild(guild).ferelden_score()
            await self.config.guild(guild).ferelden_score.set(faction_score + dkp)
        elif faction == 'anderfels':
            faction_score = await self.config.guild(guild).anderfels_score()
            await self.config.guild(guild).anderfels_score.set(faction_score + dkp)
        elif faction == 'nevarra':
            faction_score = await self.config.guild(guild).nevarra_score()
            await self.config.guild(guild).nevarra_score.set(faction_score + dkp)
        elif faction == 'orlais':
            faction_score = await self.config.guild(guild).orlais_score()
            await self.config.guild(guild).orlais_score.set(faction_score + dkp)
        elif faction == 'tevinder':
            faction_score = await self.config.guild(guild).tevinder_score()
            await self.config.guild(guild).tevinder_score.set(faction_score + dkp)
            
        score_log = await self.config.guild(guild).score_log()
        score_log.append(f"Added {dkp} points for {faction} from {message.author}.")
        await self.config.guils(guild).score_log.set(score_log)
        
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

    @is_owner_overridable()
    @commands.command()
    async def set_key(self, ctx, key: str):
        """Set the api key for the OCR API."""
        await self.config.guild(ctx.guild).api_key.set(key)
        await ctx.send("API Key set.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if len(message.content) == 0:
          return
        
        first_char = message.content[0]
        if message.author.bot or not first_char.isalpha():
          return
