from datetime import datetime
import asyncio
import json
import aiofiles
import aiohttp
import pytz
from discord.ext import tasks
from redbot.core import commands, Config

class Docket_Updates(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=69318888, force_registration=True)
        self.config.register_guild(alerts_channel_id=None)
        self.config.register_guild(dates_by_case = {})
        self.config.register_guild(auth_token=None)

    def cog_unload(self):
        self.send_daily_message.cancel()  # Stop the task if the cog is unloaded
        

    async def fetch_url(session, url, headers=None):
        async with session.get(url,headers=headers) as response:
            return await response.text()

    @tasks.loop(datetime.time(hour=12, tzinfo=pytz.timezone('America/New_York')))
    async def send_daily_message(self):
        channel_id = await self.config.alerts_channel_id()
        auth_token = await self.config.auth_token()
        channel = self.bot.get_channel(channel_id)
        if channel:
            if auth_token:
                new_stuff = await get_info()
                if new_stuff:
                    await channel.send(new_stuff)
            else:
                print("Please set the token")
        else:
            print("Please set the alerts channel id.")

    async def get_info(self):
        ret = ""
        ids = []
        auth_token = await self.config.auth_token()
        if not auth_token:
            print
        headers = {
            "Authorization": f"Token {auth_token}"
        }
        async with aiofiles.open("interesting_cases.txt", mode='r') as file:
            for line in file.readlines():
                ids.append(line.strip())
        async with aiohttp.ClientSession() as session:
            all_cases = [fetch_url(session, f"https://www.courtlistener.com/api/rest/v3/dockets/{id}/",headers=headers) for id in ids]
            responses = await asyncio.gather(*tasks)
        dates_by_case = await self.config.dates_by_case()
        for response in responses:
            data = json.loads(response)
            case_id = data['id']
            date_last_filing = data['date_last_filing']
            if case_id in dates_by_case:
                date1 = datetime.strptime(date_last_filing, "%Y-%m-%d")
                date2 = datetime.strptime(dates_by_case[case_id], "%Y-%m-%d")
                if date1 > date2:
                    ret += f"{data['case_name']} has new docket activity!\n"
            else:
                dates_by_case[case_id] = date_last_filing
        if ret == "":
            return None
        else:
            return ret
                
        

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()  # Wait until the bot is ready

    @is_owner_overridable()
    @commands.command()
    async def set_channel_id(self, ctx, id: int):
        """Set the channel ID for daily messages."""
        await self.config.alerts_channel_id.set(id)  # Save the channel ID to config
        await ctx.send(f"alerts channel set.")

    @is_owner_overridable()
    @commands.command()
    async def set_token(self, ctx, id: int):
        """Set token for api requests."""
        await self.config.auth_token.set(id)  # Save the token to config
        await ctx.send(f"Token set.")
         
    @commands.Cog.listener()
    async def on_message(self, message):
        if len(message.content) == 0:
            return
        first_char = message.content[0]
        ctx = await self.bot.get_context(message)
        if message.author.bot or not first_char.isalpha():
            return
