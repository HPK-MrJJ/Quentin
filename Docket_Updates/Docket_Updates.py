from redbot.core import commands, Config
import datetime
import asyncio
import json
import aiofiles
import aiohttp
import pytz
from discord.ext import tasks

class Docket_Updates(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=69318888, force_registration=True)
        self.config.register_guild(alerts_channel_id=0)
        self.config.register_guild(dates_by_case={})
        self.config.register_guild(auth_token=0)

    def cog_unload(self):
        self.send_daily_message.cancel()

    async def fetch_url(self, session, url, headers=None):
        async with session.get(url, headers=headers) as response:
            return await response.text()

    @tasks.loop(time=datetime.time(hour=12, tzinfo=pytz.timezone('America/New_York')))
    async def send_daily_message(self):
        channel_id = await self.config.alerts_channel_id()
        auth_token = await self.config.auth_token()
        channel = self.bot.get_channel(channel_id)
        if channel:
            if auth_token:
                new_stuff = await self.get_info()
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
            return None
        
        headers = {
            "Authorization": f"Token {auth_token}"
        }
        async with aiofiles.open("interesting_cases.txt", mode='r') as file:
            ids = [line.strip() for line in await file.readlines()]

        async with aiohttp.ClientSession() as session:
            all_cases = [self.fetch_url(session, f"https://www.courtlistener.com/api/rest/v3/dockets/{id}/", headers=headers) for id in ids]
            responses = await asyncio.gather(*all_cases)

        dates_by_case = await self.config.dates_by_case()
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
                dates_by_case[case_id] = date_last_filing

        return ret if ret else None

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()

    @commands.is_owner()
    @commands.command()
    async def set_channel_id(self, ctx, id: int):
        await self.config.alerts_channel_id.set(id)
        await ctx.send("Alerts channel set.")

    @commands.is_owner()
    @commands.command()
    async def set_token(self, ctx, token: str):
        await self.config.auth_token.set(token)
        await ctx.send("Token set.")
