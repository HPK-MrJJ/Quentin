import os
import time
import gzip
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

import aiofiles
import aiohttp
import asyncio
from discord.ext import tasks
from redbot.core import commands, Config

class Name_Finder(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=69311230, force_registration=True)
        # Register guild-specific settings
        self.config.register_guild(
            alerts_channel_id=0,
            owner_id=0,
        )
      
        # Start the loop task
        self.send_daily_message.start()

    def cog_unload(self):
        self.send_daily_message.cancel()

    async def download_and_process_xml(channel, url):
        temp_path = None
        owner_id = await self.config.guild(guild).owner_id()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={'User-Agent': 'kakastania'}) as response:
                    if response.status == 200:
                        with gzip.GzipFile(fileobj=BytesIO(response.read())) as gzipped_file:
                            xml_text = gzipped_file.read()
                        
                        # Parse XML content
                        root = ET.fromstring(xml_text)
                        
                        # Create a temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp_file:
                            tmp_file.write(ET.tostring(root))
                            temp_path = tmp_file.name  # Store the temporary file path
        
                        print(f"XML file downloaded and saved temporarily at {temp_path}")
                        
                        tree = ET.parse(temp_path)
                        root = tree.getroot()
                        loom_nations = []
                        for nation in root.findall(".//NATION"):
                            if (nation.find("LASTACTIVITY").text == "27 days ago" or nation.find("LASTACTIVITY").text == "59 days ago") and int(nation.find("POPULATION").text) < 1000:
                                loom_nations.append(nation.find("NAME").text)
                        print(f"This will take {len(loom_nations)*(1/600)} hours.")
                        foundables = []
                        async with aiofiles.open("available_nations.txt", "w") as file:
                            for i,name in enumerate(loom_nations):
                                print(f"{i+1} of {len(loom_nations)}")
                                if await check_nation_foundability(name):
                                    await file.write(f"{name}\n")
                        try:
                            await channel.send(file=discord.File("available_nations.txt"))
                            await channel.send(f"{owner_id}")
                        finally:
                            if os.path.exists("available_nations.txt"):
                                os.remove("available_nations.txt")
        
                    else:
                        print(f'Failed to fetch dump from NationStates with status {response.status}')
    
        except Exception as e:
            print(f'An error occurred: {e}')
    
        finally:
            # Clean up the temporary file
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"Temporary file {temp_path} has been removed.")

    @tasks.loop(time=datetime.time(hour=6))
    # @tasks.loop(minutes=1)
    async def send_daily_message(self):
        try:
            for guild in self.bot.guilds:  # Loop through all guilds the bot is part of
                channel_id = await self.config.guild(guild).alerts_channel_id()
                owner_id = await self.config.guild(guild).owner_id()
                channel = self.bot.get_channel(channel_id)
                
                if channel:
                    if owner_id != 0:
                        date = (datetime.now() - timedelta(days=1)).replace(year=(datetime.now() - timedelta(days=1)).year - 5).strftime("%Y-%m-%d")
                        output_file = f'data/{date}-Nations.xml'
                        try:
                            await download_and_save_xml(channel, f'https://www.nationstates.net/archive/nations/{date}-nations-xml.gz')
                        except Exception as e:
                            return
                    else:
                        print("Please set the owner ID so that I can ping you.")
                else:
                    print(f"Please set the alerts channel id for guild: {guild.name}.")
        except asyncio.CancelledError:
            print("Winding down the daily message task...")
            raise
        except Exception as e:
            print(f"An error occured in the daily message task loop that makes me want to cry: {e}")

    async def check_nation_foundability(nation_name):
        await asyncio.sleep(6)  # Async sleep for 6 seconds between requests
        url = "https://www.nationstates.net/template-overall=none/page=boneyard"
        data = {"nation": nation_name, "submit": "1"}
        headers = {"User-Agent": "kakastania"}
    
        # Encode the data to URL-encoded format
        data_encoded = urllib.parse.urlencode(data).encode("utf-8")
    
        # Make an asynchronous HTTP POST request with aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data_encoded, headers=headers) as response:
                response_text = await response.text()
    
        # Check if the response contains the desired message
        return "Available! This name may be used to found a new nation." in response_text

    @commands.is_owner()
    @commands.command()
    async def set_channel_id(self, ctx, id: int):
        """Set the alerts channel ID for the guild."""
        await self.config.guild(ctx.guild).alerts_channel_id.set(id)
        await ctx.send("Alerts channel set.")

    @commands.is_owner()
    @commands.command()
    async def set_owner_id(self, ctx, id: int):
        """Set the owner id"""
        await self.config.guild(ctx.guild).owner_id.set(id)
        await ctx.send("Owner ID set.")        

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()
