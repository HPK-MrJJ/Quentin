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
import tempfile

import aiopytesseract

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

        # Register config with role IDs instead of role objects
        self.config.register_guild(
            quests_channel_id=None,
            quests_role_id=None,
            quest_count=0,
            current_quest=None,
            faction_roles={},
            faction_scores={},
        )

    @commands.Cog.listener()
    async def on_ready(self):
        """Run role setup when bot is ready."""
        self.send_daily_message_task.start()
        self.score_quests_task.start()

    def cog_unload(self):
        self.send_daily_message_task.cancel()  # Stop the task if the cog is unloaded

    async def ocr(self, url):
        suffix = os.path.splitext(url.split('?')[0])[1] or ".img"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                async with aiofiles.open(temp_path, 'wb') as f:
                    await f.write(await resp.read())

        text = await aiopytesseract.image_to_string(temp_path)
        os.remove(temp_path)
        return text

    @tasks.loop(hours=25)
    # @tasks.loop(minutes=1)
    async def send_daily_message_task(self):
        await self.send_daily_message()

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
                        await self.config.guild(guild).quest_count.set(quest_count+1)
                        await self.config.guild(guild).current_quest.set(duple[0])
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
        
    @send_daily_message_task.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready() 

    @tasks.loop(hours=25)
    async def score_quests_task(self):
        await self.score_quests()

    async def score_quests(self):
        """start the scoring process if there are quests to score"""
        for guild in self.bot.guilds:
            count = await self.config.guild(guild).quest_count()
            channel_id = await self.config.guild(guild).quests_channel_id()
            if count > 0:
                await self.fetch_messages(channel_id, guild)

    @score_quests_task.before_loop
    async def before_score_quest(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(86400)

    async def fetch_messages(self, channel_id, guild):
        """get the messages that need scoring and send them to the scoring method"""
        channel = self.bot.get_channel(channel_id)
        last_quest = datetime.now() - timedelta(hours=23, minutes=59)
        current_quest = await self.config.guild(guild).current_quest()
    
        async for message in channel.history(after=last_quest):
            if await self.scored(guild, message, str(current_quest)):
                await message.add_reaction("✅")
            else:
                await message.add_reaction("❌")

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
        
        pattern = r'2048 (\d+)\|'
        match = re.search(pattern, image_contents)
    
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

            if '🧭' in contents:
                dkp += 1
            if '⭐' in contents:
                dkp += 1
            if '🚩' in contents:
                dkp += 1
            if '🔤' in contents:
                dkp += 1
            if '👫' in contents:
                dkp += 1
            if '🪙' in contents:
                dkp += 1
            if '🗣️' in contents:
                dkp += 1
            if '📐' in contents:
                dkp += 1
            if '🏙️' in contents:
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

        pattern = r'HI (\d+) '
        match = re.search(pattern, image_contents)

        if match:
            score_raw = match.group(1)
            
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

        pattern = r'(\d+)m'
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

        pattern = r'was (\d+)'
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

            score_str = match.group(1)
            if score.isdigit():
                score = int(score_str)

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

        wins = ["🟩🟩🟩🟩","🟨🟨🟨🟨","🟪🟪🟪🟪", "🟦🟦🟦🟦"]

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
            score= int(score)
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

        pattern = r'FINAL SCORE\n([\d,]+)'

        match = re.search(pattern, image_contents)

        if match:
            score = int("".join(match.group(1).split(",")))
            if score > 50000:
                dkp = 20
            elif score > 20000:
                dkp = 10
            else:
                dkp = 5
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
        
        if highest_fruit == "Peach":
            dkp = 3
        elif highest_fruit == "Pineapple":
            dkp = 5
        elif highest_fruit == "Melon":
            dkp = 7
        elif highest_fruit == "Watermelon":
            dkp = 10
        else:
            dkp = 1

        truth = await find_faction(dkp, guild, message)

        return truth 

    async def find_faction(self, dkp, guild, message):
        roles = await self.config.guild(guild).faction_roles()
        scores = await self.config.guild(guild).faction_scores()
        user_role = None
        for role in roles.values():
            if role in message.author.roles:
                user_role = role
                break

        if user_role:
            original_score = scores[user_role.name]
            await self.config.guild(guild).faction_scores.set(scores | {user_role.name: original_score + dkp})
            return True
        else:
            return False
        
    @is_owner_overridable()
    @commands.command()
    async def set_quest_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for daily quests."""
        await self.config.guild(ctx.guild).quests_channel_id.set(channel.id)  
        await ctx.send(f"Quests channel set to {channel.mention}")
    
    @is_owner_overridable()
    @commands.command()
    async def set_role(self, ctx, role: discord.Role):
        """Set the role for daily messages."""
        await self.config.guild(ctx.guild).quests_role_id.set(role.id) 
        await ctx.send(f"Quests role ID set to {role.mention}.")
        
    @is_owner_overridable()
    @commands.command() 
    async def create_faction(self, ctx, role: discord.Role):
        roles_raw = await self.config.guild(ctx.guild).faction_roles()
        scores = await self.config.guild(ctx.guild).faction_scores()

        roles = {int(k): v for k, v in roles_raw.items()}

        if role.id not in roles:
            roles[role.id] = {'name': role.name}
            scores[role.id] = 0

            await self.config.guild(ctx.guild).faction_roles.set(roles)
            await self.config.guild(ctx.guild).faction_scores.set(scores)

            await ctx.send("Faction added. Here's the ones I have:")
        else:
            await ctx.send("I already have a faction by that name. Here's the ones I have:")

        for role_id, role_info in roles.items():
            role_name = role_info['name']
            role_obj = ctx.guild.get_role(role_id)
            if role_obj:
                await ctx.send(f"{role_name}: {role_obj.mention}")
            else:
                await ctx.send(f"{role_name}: (Role not found)")

    @is_owner_overridable()
    @commands.command()
    async def list_factions(self, ctx):
        """Lists all registered factions."""
        roles_raw = await self.config.guild(ctx.guild).faction_roles()
        if not roles_raw:
            await ctx.send("No factions have been created yet.")
            return

        roles = {int(k): v for k, v in roles_raw.items()}

        for role_id, role_data in roles.items():
            role_name = role_data.get("name", "Unknown")
            role_obj = ctx.guild.get_role(role_id)
            if role_obj:
                await ctx.send(f"{role_name}: {role_obj.mention}")
            else:
                await ctx.send(f"{role_name}: (Role not found)")

    @is_owner_overridable()
    @commands.command()
    async def remove_faction(self, ctx, role: discord.Role):
        """Removes a faction."""
        roles_raw = await self.config.guild(ctx.guild).faction_roles()
        scores = await self.config.guild(ctx.guild).faction_scores()

        roles = {int(k): v for k, v in roles_raw.items()}
        scores = {int(k): v for k, v in scores.items()}

        if role.id in roles:
            del roles[role.id]
            del scores[role.id]
            await self.config.guild(ctx.guild).faction_roles.set(roles)
            await self.config.guild(ctx.guild).faction_scores.set(scores)
            await ctx.send(f"Faction `{role.name}` removed.")
        else:
            await ctx.send("Faction not found.")

    @is_owner_overridable()
    @commands.command()
    async def score_now(self, ctx):
        """Forces the scoring to start (end the day)"""
        await self.score_quests()

    @is_owner_overridable()
    @commands.command()
    async def new_quest(self, ctx):
        """Force sends a new quest -- new day"""
        await self.send_daily_message()

    @is_owner_overridable()
    @commands.command()
    async def show_scores(self, ctx):
        """Shows the scores for each faction"""
        score_log = await self.config.guild(ctx.guild).faction_scores()
        message = ""
        for faction, score in score_log:
            message += f"**{faction}**: {score} DKP"
        ctx.send(message)

    @commands.Cog.listener()
    async def on_message(self, message):
        if len(message.content) == 0:
          return
        
        first_char = message.content[0]
        if message.author.bot or not first_char.isalpha():
          return
