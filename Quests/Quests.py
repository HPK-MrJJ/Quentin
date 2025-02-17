import os
import numpy as np
import random
import asyncio
from datetime import datetime, timedelta

import re
import cv2
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
            api_key=None,
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

    async def ocr(self, guild, url, max_retries=5, initial_delay=1):
        retry_count = 0
        delay = initial_delay  # Initial delay in seconds

        while retry_count < max_retries:
            try:
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
                    async with session.post("https://api.ocr.space/parse/image", data=payload) as response:
                        if response.status != 200:
                            raise Exception(f"Error: API request failed with status code {response.status}")
                        
                        # Parse the JSON response
                        result = await response.json()
                        
                        if result['IsErroredOnProcessing']:
                            raise Exception(result['ErrorMessage'][0])
                    
                        return result['ParsedText']
            
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise Exception(f"Max retries reached. Last error: {e}")


                status_values = []
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url="https://status.ocr.space/") as response:
                            # Parse the HTML content with BeautifulSoup
                            soup = BeautifulSoup(response.text, 'html.parser')

                            # Find all td elements with the classes "tb_b_right", "tb_b_left", and "tb_b_right"
                            td_elements = soup.find_all('td', class_='tb_b_right')

                            # Extract the text from each td element
                            status_values = [td.get_text(strip=True) for td in td_elements]
                except Exception as e:
                    print("Damn even the front end is down")

                if status_values[0] == 'DOWN' or status_values[1] == 'DOWN':
                    print("One or more of the APIs is down, this may take a while/not work")

                    await self.enter_long_term_wait(self, channel_id = await self.config.guild(guild).quests_channel_id())
                
                print(f"Retry {retry_count}/{max_retries} after error: {e}")
                await asyncio.sleep(delay)  # Exponential backoff
                delay *= 2  # Double the delay for the next retry

    @tasks.loop(hours=25)
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
                            await self.config.guild(guild).quests_count.set(quest_count+1)
                            await self.config.guild(guild).current_quest.set(duple[0])
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
        await asyncio.sleep(86400)

    async def enter_long_term_wait(self, channel_id):
        channel = self.bot.get_channel(channel_id)
        channel.send("Hi there. The OCR API is currently down or experiencing super high latency. It might be a while before I can score these. I'll check every five minutes to see if it is back, and let you know when it comes back.")
        up = False
        while not up:
            try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url="https://status.ocr.space/") as response:
                            # Parse the HTML content with BeautifulSoup
                            soup = BeautifulSoup(response.text, 'html.parser')

                            # Find all td elements with the classes "tb_b_right", "tb_b_left", and "tb_b_right"
                            td_elements = soup.find_all('td', class_='tb_b_right')

                            # Extract the text from each td element
                            status_values = [td.get_text(strip=True) for td in td_elements]
                except Exception e:
                    print("Damn even the front end is down")
            if status_values[0] == 'UP' and status_values[1] == 'UP':
                up = True
            else:
                print("still down, will check again in five min")
                asynchio.sleep(310)
        channel.send("Things are back up again so I will go back to scoring.")

    @tasks.loop(hours=25)
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
            if self.scored(guild, message, str(current_quest)): # the scored method scores the message and returns true if it scored, otherwise false
                await self.bot.add_reaction(message, "✅")
            else:
                await self.bot.add_reaction(message, "❌")

    async def scored(self, guild, message: discord.Message, quest_name: str):
        """direct the program to the right method to score the quest of the day"""
        quest_name = quest_name.lower()
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
        elif quest_name == 'slither.io':
            return self.slitherio_score(guild, message)
        elif quest_name == 'wordle':
            return self.wordle_score(guild, message)
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
        image_contents = await self.ocr(guild, image.url)
        
        pattern = r'SCORE\r\n([0-9]+)'
        match = re.search(pattern, text)
    
        if match:
            score = int(match.group(1))
            if score < 2500:
                dkp = 3
            elif score < 5000:
                dkp = 5
            else:
                dkp = 10

            truth = await find_faction(dkp, guild, message)
                
            return truth
                
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
                
            truth = await find_faction(dkp, guild, message)
                
            return truth
                
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

            truth = await find_faction(dkp, guild, message)
                
            return truth
                
        else:
            return False

    async def dino_score(self, guild: discord.Guild, message: discord.Message):
        dkp = 0
        attachments = message.attachments
        if len(attachments) != 1:
            return False
        image = attachments[0]
        image_contents = await self.ocr(guild, image.url)

        pattern = r'HI\s[a-zA-Z0-9]{5}\s([a-zA-Z0-9]{5})'
        match = re.search(pattern, text)

        if match:
            score_raw = match.group(1)
            if score_raw.isdigit():
                true_score = int(score_raw)
            else:
                if (score_raw[0] == '0' and score_raw[1] == '0') or ((score_raw[0] == 'o' or score_raw[0] == 'O') and (score_raw[1] == 'o' or score_raw[1] == 'O')) :
                    if score_raw[2].isdigit():
                        if int(score-raw[2]) >= 5:
                            dkp = 10
                        else:
                            dkp = 5
                    elif score_raw[2] == 'S' or score_raw[2] == 's':
                        dkp = 10
                    else:
                        dkp = 5
                elif score_raw[1].isdigit():
                    if int(score_raw[1]) > 2:
                        dkp = 20
                    elif int(score_raw[1]) < 2:
                        dkp = 10
                    elif int(score_raw[1]) == 2 and (int(score-raw[2]) >= 5 or (score_raw[2] == 'S' or score_raw[2] == 's')) :
                        dkp = 20
                    else:
                        dkp = 10
                else:
                    if score_raw[1] == 'l' or score_raw[1] == 'I':
                        dkp = 10
                    else:
                        dkp = 20
                        
            truth = await find_faction(dkp, guild, message)
                
            return truth
        
        else:
            return False

    async def edge_surf_score(self, guild: discord.Guild, message: discord.Message):
        dkp = 0
        attachments = message.attachments
        if len(attachments) != 1:
            return False
        image = attachments[0]
        image_contents = await self.ocr(guild, image.url)

        pattern = r'000.*?(\d+)m'
        match = re.search(pattern, image_contents)

        if match:
            score = int(match.group(1))

            if score > 5000:
                dkp = 20
            elif score > 2000:
                dkp = 10
            else:
                dkp = 3

            truth = await find_faction(dkp, guild, message)
                
            return truth
        
        else:
            return False

    async def slitherio_score(self, guild: discord.Guild, message: discord.Message):
        dkp = 0
        attachments = message.attachments
        if len(attachments) != 1:
            return False
        image = attachments[0]
        image_contents = await self.ocr(guild, image.url)

        pattern = r"\b\d+\b"
        match = re.search(pattern, text)

        if match:
            score = int(match.group(1))

            if score > 5000:
                dkp = 20
            elif score > 2500:
                dkp = 10
            else:
                dkp = 5

            truth = await find_faction(dkp, guild, message)
                
            return truth
        
        else:
            return False

    async def wordle_score(self, guild: discord.Guild, message: discord.Message):
        content = message.content

        pattern = r'\s(\w)\/'
        match = re.search(pattern, content)

        if match:

            if score.isdigit():
                score = int(match.group(1))

                if score <= 3:
                    dkp = 10
                else:
                    dkp = 5
            else:
                dkp = 3
        else:
            return False

        truth = await find_faction(dkp, guild, message)

        return truth

    async def connections_score(self, guild: discord.Guild, message: discord.Message):
        content = message.content

        wins = [":green_square::green_square::green_square::green_square:",":yellow_square::yellow_square::yellow_square::yellow_square",""":purple_square::purple_square:
                    :purple_square::purple_square:""", ":blue_square::blue_square::blue_square::blue_square:"]

        num_wins = 0

        for win in wins:
            if win in content:
                num_wins += 1

        if num_wins == 4:
            num_squares = content.count("_square:")
            num_guesses = round(num_squares/4) # there should never need to be rounding but this just prevents errors even in messed up content
            if num_guesses <= 6:
                dkp = 10
            else:
                dkp = 5
        else:
            dkp = 3

        truth = await find_faction(dkp, guild, message)

        return truth

    async def semantle_score(self, guild: discord.Guild, message: discord.Message):
        content = message.content

        pattern = r':white_check_mark:\s*(\d+)\s*Guesses'

        match = re.search(pattern, content)

        if match:
            score = match.group(1)
            if score < 30:
                dkp = 20
            elif score < 50:
                dkp = 10
            else:
                dkp = 3
        else:
            if ":x:" in content:
                dkp = 3
            else:
                return False

        truth = await find_faction(dkp, guild, message)

        return truth

    async def tetrio_score(self, guild: discord.Guild, message: discord.Message):
        dkp = 0
        attachments = message.attachments
        if len(attachments) != 1:
            return False
        image = attachments[0]
        image_contents = await self.ocr(guild, image.url)

        pattern = r'\r\n(\d+(?:,\d+)*)\r\n'

        match = re.search(pattern, image_contents)

        if match:
            score = int("".join(match.group(1).split(",")))
            if score > 50000:
                dkp = 20
            elif score > 20000:
                dkp = 10
            else:
                score = 5
        else:
            return False

        truth = await find_faction(dkp, guild, message)

        return truth

    async def suika_score(self, guild: discord.Guild, message: discord.Message):
        fruit_colors = {
                "Cherry": ([168, 125, 223], [174, 216, 240]),    
                "Strawberry": ([5, 165, 223], [7, 236, 244]),
                "Grape": ([143, 133, 247], [144, 200, 255]),
                "Dekopon": ([16, 156, 255], [18, 198, 255]),  
                "Orange": ([10, 156, 227], [14, 216, 249]),
                "Apple": ([175, 103, 249], [179, 212, 255]),
                "Pear": ([25, 150, 228], [27, 235, 246]),
                "Peach": ([151, 100, 255], [160, 255, 255]),
                "Pineapple": ([23, 235, 242], [29, 244, 255]),
                "Melon": ([40, 163, 248], [56, 240, 255]),
                "Watermelon": ([44, 219, 151], [60, 255, 207]), 
        }
        
        dkp = 0
        attachments = message.attachments
        if len(attachments) != 1:
            return False
        
        image = attachments[0]
        hsv_image = await asyncio.to_thread(cv2.cvtColor, image, cv2.COLOR_BGR2HSV)
    
        highest_fruit = None
        
        for fruit, (lower, upper) in fruit_colors.items():
            lower_bound = np.array(lower, dtype=np.uint8)
            upper_bound = np.array(upper, dtype=np.uint8)

            # Run cv2.inRange in a separate thread
            mask = await asyncio.to_thread(cv2.inRange, hsv_image, lower_bound, upper_bound)

            # Run cv2.findContours in a separate thread
            contours, _ = await asyncio.to_thread(cv2.findContours, mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                highest_fruit = fruit  # Update the highest detected fruit
            else:
                break  # Stop checking further if a fruit is missing
        
        if fruit == "Peach":
            dkp = 3
        elif fruit == "Pineapple":
            dkp = 5
        elif fruit == "Melon":
            dkp = 7
        elif fruit == "Watermelon":
            dkp = 10
        else:
            dkp = 1

        truth = await find_faction(dkp, guild, message)

        return truth
        
    # bandle_score    

    async def find_faction(dkp, guild, message):
        
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
        await self.config.guild(guild).score_log.set(score_log)
        
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
