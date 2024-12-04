import os
import gzip
import tempfile
import logging
from datetime import datetime, timedelta, time
from io import BytesIO
import urllib.parse
import xml.etree.ElementTree as ET

import aiofiles
import aiohttp
import asyncio
import discord
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
        self.semaphore = asyncio.Semaphore(10) 
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
                async with session.get(url, headers={'User-Agent': 'kakastania'}, allow_redirects=True) as response:
                    if response.status != 200:
                        logger.error(f"Unexpected status code: {response.status}")
                        return
            
                    if response.headers.get('Content-Type') != 'x-gzip':
                        logger.error(f"Unexpected content type for url {url}: {response.headers.get('Content-Type')}")
                        logger.info(f"Response status: {response.status}")
                        logger.debug(f"Response content: {await response.text()}")
                        return
            
                    response_data = await response.read()
                    if response_data.startswith(b'<!'):
                        logger.error("Response appears to be HTML, possibly an error page.")
                        logger.error(response_data[:200].decode('utf-8', errors='ignore'))  # Log the first 200 characters
                        return
            
                    try:
                        with gzip.GzipFile(fileobj=BytesIO(response_data)) as gzipped_file:
                            xml_text = gzipped_file.read()
                    except OSError:
                        logger.error("Response content is not a valid Gzip file.")
                        return
    
                        # Parse XML content
                        root = ET.fromstring(xml_text)
    
                        # Create a temporary file to store the XML data
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp_file:
                            tmp_file.write(ET.tostring(root))
                            temp_path = tmp_file.name  # Store the temporary file path
                        
                        logger.info(f"XML file downloaded and saved temporarily at {temp_path}")
                        
                        # Re-parse the XML data for processing
                        loom_nations = []
    
                        for nation in root.findall(".//NATION"):
                            last_activity = nation.find("LASTACTIVITY").text if nation.find("LASTACTIVITY") is not None else ""
                            population = int(nation.find("POPULATION").text) if nation.find("POPULATION") is not None else 0
    
                            if last_activity in {"27 days ago", "59 days ago"} and population < 1000:
                                loom_nations.append(nation.find("NAME").text)
    
                        if not loom_nations:
                            logger.info("No nations matching the criteria were found.")
                            await channel.send("No nations found that match the criteria.")
                            return
    
                        logger.info(f"This will take {len(loom_nations)*(1/600)} hours.")
    
                        foundables = []
    
                        # Create tasks for each nation
                        tasks = [self.check_nation_foundability(name) for name in loom_nations]
    
                        # Run the tasks with asyncio.gather
                        results = await asyncio.gather(*tasks, return_exceptions=True)
    
                        # Collect successful results
                        for i, (name, result) in enumerate(zip(loom_nations, results)):
                            logger.info(f"{i+1} of {len(loom_nations)} processed")
                            if isinstance(result, Exception):
                                logger.error(f"Error for nation {name}: {result}", exc_info=True)
                            elif result:  # Nation is available
                                foundables.append(name)
    
                        # Write foundable nations to the file
                        file_path = os.path.join(tempfile.gettempdir(), "available_nations.txt")
                        async with aiofiles.open(file_path, "w") as file:
                            for name in foundables:
                                await file.write(f"{name}\n")
    
                        # Send the file to Discord
                        try:
                            await channel.send(file=discord.File(file_path))
                            await channel.send(f"{owner_id}")
                        finally:
                            if os.path.exists(file_path):
                                os.remove(file_path)
    
                    else:
                        logger.error(f'Failed to fetch dump from NationStates with status {response.status}')
                        if channel:
                            await channel.send("Failed to download the XML data. Please try again later.")
        except asyncio.CancelledError:
            logger.info("Task was cancelled.")
            raise
        except Exception as e:
            logger.error(f'An error occurred: {e}', exc_info=True)
            if channel:
                await channel.send("An error occurred while processing nations. Please check the logs.")
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
                logger.info(f"Temporary file {temp_path} has been removed.")

    # @tasks.loop(time=time(hour=6))
    @tasks.loop(hours=3)
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
                        url = f'https://archive.nsupc.dev/file/nsarchive/nations/{date}-nations.xml.gz'
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
        url = "https://www.nationstates.net/template-overall=none/page=boneyard"
        data = {"nation": nation_name, "submit": "1"}
        headers = {"User-Agent": "kakastania"}
    
        data_encoded = urllib.parse.urlencode(data).encode("utf-8")
    
        async with self.semaphore:  # Enforce throttling
            await asyncio.sleep(6)  # Delay to respect API rate limits
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data_encoded, headers=headers) as response:
                    response_text = await response.text()
    
        return "Available! This name may be used to found a new nation." in response_text

    @commands.is_owner()
    @commands.command()
    async def set_channel_id_names(self, ctx, id: int):
        """Set the alerts channel ID for the guild."""
        await self.config.guild(ctx.guild).alerts_channel_id.set(id)
        await ctx.send("Alerts channel set.")

    @commands.is_owner()
    @commands.command()
    async def set_owner_id_names(self, ctx, id: int):
        """Set the owner ID for the guild."""
        await self.config.guild(ctx.guild).owner_id.set(id)
        await ctx.send("Owner ID set.")        

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()
