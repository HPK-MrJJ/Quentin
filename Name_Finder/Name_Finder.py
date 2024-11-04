import os
import gzip
import tempfile
import logging
from datetime import datetime, timedelta
from io import BytesIO
import urllib.parse
import xml.etree.ElementTree as ET

import aiofiles
import aiohttp
import asyncio
from discord.ext import tasks
from redbot.core import commands, Config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    async def download_and_process_xml(self, guild, channel, url):
        """Download XML data, process it, and send results if conditions are met."""
        temp_path = None
        owner_id = await self.config.guild(guild).owner_id()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={'User-Agent': 'kakastania'}) as response:
                    if response.status == 200:
                        # Read and decompress response content
                        with gzip.GzipFile(fileobj=BytesIO(await response.read())) as gzipped_file:
                            xml_text = gzipped_file.read()

                        # Parse XML content
                        root = ET.fromstring(xml_text)

                        # Create a temporary file to store the XML data
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp_file:
                            tmp_file.write(ET.tostring(root))
                            temp_path = tmp_file.name  # Store the temporary file path
                        
                        logger.info(f"XML file downloaded and saved temporarily at {temp_path}")
                        
                        # Re-parse the XML data for processing
                        tree = ET.parse(temp_path)
                        root = tree.getroot()
                        loom_nations = []

                        # Find nations matching specific criteria
                        for nation in root.findall(".//NATION"):
                            last_activity = nation.find("LASTACTIVITY").text
                            population = int(nation.find("POPULATION").text)
                            if last_activity in {"27 days ago", "59 days ago"} and population < 1000:
                                loom_nations.append(nation.find("NAME").text)

                        logger.info(f"This will take {len(loom_nations)*(1/600)} hours.")

                        foundables = []
                        async with aiofiles.open("available_nations.txt", "w") as file:
                            for i, name in enumerate(loom_nations):
                                logger.info(f"{i+1} of {len(loom_nations)}")
                                if await self.check_nation_foundability(name):
                                    await file.write(f"{name}\n")

                        try:
                            await channel.send(file=discord.File("available_nations.txt"))
                            await channel.send(f"{owner_id}")
                        finally:
                            if os.path.exists("available_nations.txt"):
                                os.remove("available_nations.txt")

                    else:
                        logger.error(f'Failed to fetch dump from NationStates with status {response.status}')
    
        except asyncio.CancelledError:
            logger.info("Task was cancelled.")
            raise
        except Exception as e:
            logger.error(f'An error occurred: {e}')
    
        finally:
            # Clean up the temporary file
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
                logger.info(f"Temporary file {temp_path} has been removed.")

    @tasks.loop(time=datetime.time(hour=6))
    async def send_daily_message(self):
        """Loop task to send a daily message."""
        try:
            for guild in self.bot.guilds:
                channel_id = await self.config.guild(guild).alerts_channel_id()
                owner_id = await self.config.guild(guild).owner_id()
                channel = self.bot.get_channel(channel_id)
                
                if channel:
                    if owner_id != 0:
                        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                        url = f'https://www.nationstates.net/archive/nations/{date}-nations-xml.gz'
                        try:
                            await self.download_and_process_xml(guild, channel, url)
                        except Exception as e:
                            logger.error(f"Error during XML download and processing: {e}")
                    else:
                        logger.warning("Please set the owner ID so that I can ping you.")
                else:
                    logger.warning(f"Please set the alerts channel id for guild: {guild.name}.")
        except asyncio.CancelledError:
            logger.info("Winding down the daily message task...")
            raise
        except Exception as e:
            logger.error(f"An error occurred in the daily message task loop: {e}")

    async def check_nation_foundability(self, nation_name):
        """Check if a nation name is available for founding."""
        await asyncio.sleep(6)  # Async sleep to manage request rate
        url = "https://www.nationstates.net/template-overall=none/page=boneyard"
        data = {"nation": nation_name, "submit": "1"}
        headers = {"User-Agent": "kakastania"}

        data_encoded = urllib.parse.urlencode(data).encode("utf-8")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data_encoded, headers=headers) as response:
                response_text = await response.text()

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
        """Set the owner ID for the guild."""
        await self.config.guild(ctx.guild).owner_id.set(id)
        await ctx.send("Owner ID set.")        

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
