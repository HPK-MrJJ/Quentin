import os
import json
import datetime
import asyncio

import aiohttp
import aiofiles

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
            auth_token="",
            owner_id=0,
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

    @tasks.loop(time=datetime.time(hour=12))
    # @tasks.loop(minutes=1)
    async def send_daily_message(self):
        print("Executing daily task")
        try:
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
        except asyncio.CancelledError:
            print("Winding down the daily message task...")
            raise
        except Exception as e:
            print(f"An error occured in the daily message task loop that makes me want to cry: {e}")

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
            all_cases = [self.fetch_url(session, f"https://www.courtlistener.com/api/rest/v3/dockets/{id}/", headers=headers) for id in ids]
            responses = await asyncio.gather(*all_cases)
    
        # Retrieve the saved dates_by_case from config
        dates_by_case = await self.config.guild(guild).dates_by_case()
        print(f"Loaded dates_by_case for guild: {guild.name}, cases: {dates_by_case}")  # Debugging

        change = False
        for response in responses:
            data = json.loads(response)
            case_id = str(data['id'])
            date_last_filing = data['date_last_filing']
    
            if case_id in dates_by_case:
                date1 = datetime.datetime.strptime(date_last_filing, "%Y-%m-%d")
                date2 = datetime.datetime.strptime(dates_by_case[case_id], "%Y-%m-%d")
                if date1 > date2:
                    ret += f"{data['case_name']}{data['docket_number']} has new docket activity!\n"
                    dates_by_case[case_id] = date1
                    change = True
            else:
                # For first-time run, add all cases as having new activity
                dates_by_case[case_id] = date_last_filing
                ret += f"This is the first time I am seeing {data['case_name']}{data['docket_number']}!\n"
    
        if change:
            # Save the updated dates back into the configuration
            print(f"Saving updated dates for guild: {guild.name}, cases: {dates_by_case}")
            await self.config.guild(guild).dates_by_case.set(dates_by_case)
        else:
            print("I've got nothing new this time around.")
    
        owner_id = await self.config.guild(guild).owner_id()

        if ret:
            if owner_id != 0:
                return f"<@{owner_id}>\n{ret}"
            else:
                return f"{ret}\n\n**Please set an owner ID so I can ping you.**"
        else:
            return "Nothing today, boss."               

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
        
        for response in responses:
            data = json.loads(response)
            case_name = data.get('case_name', 'Unknown Case')
            date_last_filing = data.get('date_last_filing', 'Unknown Date')
            ret += f"Case: {case_name} - {data['docket_number']}\nLast Filing Date: {date_last_filing}\n\n"
    
        owner_id = await self.config.guild(guild).owner_id()

        if ret:
            if owner_id != 0:
                return f"<@{owner_id}>\n{ret}"
            else:
                return f"{ret}\n\n**Please set an owner ID so I can ping you.**"
        else:
            return

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

    @commands.is_owner()
    @commands.command()
    async def set_owner_id(self, ctx, id: int):
        """Set the owner id"""
        await self.config.guild(ctx.guild).owner_id.set(id)
        await ctx.send("Owner ID set.")
