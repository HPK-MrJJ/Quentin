import gzip
import aiofiles
import aiohttp
from io import BytesIO
import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import time
import tempfile
import os

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
                                if check_nation_foundability(name):
                                    await file.write(f"{name}\n")
                        try:
                            await channel.send(file=discord.File("available_nations.txt"))
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
                channel = self.bot.get_channel(channel_id)
                
                if channel:
                    date = (datetime.now() - timedelta(days=1)).replace(year=(datetime.now() - timedelta(days=1)).year - 5).strftime("%Y-%m-%d")
                    output_file = f'data/{date}-Nations.xml'
                    try:
                        await download_and_save_xml(channel, f'https://www.nationstates.net/archive/nations/{date}-nations-xml.gz')
                    except Exception as e:
                        return
                else:
                    print(f"Please set the alerts channel id for guild: {guild.name}.")
        except asyncio.CancelledError:
            print("Winding down the daily message task...")
            raise
        except Exception as e:
            print(f"An error occured in the daily message task loop that makes me want to cry: {e}")
        

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()
