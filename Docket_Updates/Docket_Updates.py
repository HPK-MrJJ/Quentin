import os
import json
import datetime
import asyncio

import aiohttp
import aiofiles
import pytz

from discord.ext import tasks
from redbot.core import commands, Config

class Docket_Updates(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=69318888, force_registration=True)
        # Register guild-specific settings
        self.config.register_guild(
            alerts_channel_id=0,
            dates_by_case={},
            auth_token=""
        )
        # Start the loop task
        self.send_daily_message.start()

    def cog_unload(self):
        self.send_daily_message.cancel()

    async def fetch_url(self, session, url, headers=None):
        async with session.get(url, headers=headers) as response:
            return await response.text()

    async def send_long_message(self, channel, content):
        """Splits a long message into chunks that fit within Discord's 2000 character limit and sends them."""
        if len(content) <= 2000:
            await channel.send(content)
        else:
            # Split message into chunks of 2000 characters or less
            for i in range(0, len(content), 2000):
                await channel.send(content[i:i+2000])

    @tasks.loop(time=datetime.time(hour=12, tzinfo=pytz.timezone('America/New_York')))
    # @tasks.loop(minutes=1)
    async def send_daily_message(self):
        print("Executing daily task")
        for guild in self.bot.guilds:  # Loop through all guilds the bot is part of
            channel_id = await self.config.guild(guild).alerts_channel_id()
            auth_token = await self.config.guild(guild).auth_token()
            channel = self.bot.get_channel(channel_id)
            
            if channel:
                if auth_token:
                    new_stuff = await self.get_info(guild)
                    if new_stuff:
                        await self.send_long_message(channel, new_stuff)
                else:
                    print(f"Please set the token for guild: {guild.name}")
            else:
                print(f"Please set the alerts channel id for guild: {guild.name}.")

    async def get_info(self, guild):
        ret = ""
        ids = []
        auth_token = await self.config.guild(guild).auth_token()
        if not auth_token:
            return None
        
        headers = {
            "Authorization": f"Token {auth_token}"
        }
        async with aiofiles.open(os.path.join(os.path.dirname(__file__), 'interesting_cases.txt'), mode='r') as file:
            ids = [line.strip() for line in await file.readlines()]

        async with aiohttp.ClientSession() as session:
            all_cases = []
            for id in ids:
                try:
                    all_cases.append(self.fetch_url(session, f"https://www.courtlistener.com/api/rest/v3/dockets/{id}/", headers=headers))
                except Exception as e:
                    print(f"Error fetching case {id}: {e}")  # Log error
            responses = await asyncio.gather(*all_cases)

        dates_by_case = await self.config.guild(guild).dates_by_case()
        for response in responses:
            data = json.loads(response)
            case_id = data['id']
            date_last_filing = data['date_last_filing']
            
            if case_id in dates_by_case:
                date1 = datetime.datetime.strptime(date_last_filing, "%Y-%m-%d")
                date2 = datetime.datetime.strptime(dates_by_case[case_id], "%Y-%m-%d")
                if date1 > date2:
                    ret += f"{data['case_name']} has new docket activity!\n"
            else:
                # For first-time run, add all cases as having new activity
                dates_by_case[case_id] = date_last_filing
                ret += f"{data['case_name']} has new docket activity (first-time update)!\n"


        # Save updated case dates
        await self.config.guild(guild).dates_by_case.set(dates_by_case)

        owner = await self.bot.get_owner()
        owner_id = owner.id
        
        return f"<@{owner_id}>{ret}" if ret else None

    @commands.is_owner()
    @commands.command()
    async def docket_update(self, ctx):
        """Send a message with the most recent docket entry from each case, ignoring stored dates."""
        guild = ctx.guild
        channel_id = await self.config.guild(guild).alerts_channel_id()
        auth_token = await self.config.guild(guild).auth_token()
        channel = self.bot.get_channel(channel_id)
        
        if not channel:
            await ctx.send("Alerts channel is not set. Please set the alerts channel ID.")
            return
        
        if not auth_token:
            await ctx.send("Auth token is not set. Please set the auth token.")
            return
        
        new_stuff = await self.get_most_recent_docket_entries(guild)
        
        if new_stuff:
            await self.send_long_message(channel, new_stuff)
        else:
            await ctx.send("No updates found or there was an error.")
    
    async def get_most_recent_docket_entries(self, guild):
        """Fetch the most recent docket entry from each case."""
        ret = ""
        ids = []
        auth_token = await self.config.guild(guild).auth_token()
        if not auth_token:
            return None
        
        headers = {
            "Authorization": f"Token {auth_token}"
        }
        async with aiofiles.open(os.path.join(os.path.dirname(__file__), 'interesting_cases.txt'), mode='r') as file:
            ids = [line.strip() for line in await file.readlines()]
    
        async with aiohttp.ClientSession() as session:
            all_cases = [self.fetch_url(session, f"https://www.courtlistener.com/api/rest/v3/dockets/{id}/", headers=headers) for id in ids]
            responses = await asyncio.gather(*all_cases)
            
        owner = await self.bot.get_owner()
        owner_id = owner.id
        
        for response in responses:
            data = json.loads(response)
            case_name = data.get('case_name', 'Unknown Case')
            date_last_filing = data.get('date_last_filing', 'Unknown Date')
            ret += f"Case: {case_name}\nLast Filing Date: {date_last_filing}\n\n"
    
        return f"<@{owner_id}>{ret}" if ret else None

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()

    @commands.is_owner()
    @commands.command()
    async def set_channel_id(self, ctx, id: int):
        """Set the alerts channel ID for the guild."""
        await self.config.guild(ctx.guild).alerts_channel_id.set(id)
        await ctx.send("Alerts channel set.")

    @commands.is_owner()
    @commands.command()
    async def set_token(self, ctx, token: str):
        """Set the authentication token for the court listener API."""
        await self.config.guild(ctx.guild).auth_token.set(token)
        await ctx.send("Token set.")
