from discord.ext import tasks
from redbot.core import commands

class Name_Finder(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
      
        # Start the loop task
        self.send_daily_message.start()

    def cog_unload(self):
        self.send_daily_message.cancel()

    @tasks.loop(time=datetime.time(hour=6))
    # @tasks.loop(minutes=1)
    async def send_daily_message(self):
          # take over the world

    @send_daily_message.before_loop
    async def before_send_daily_message(self):
        await self.bot.wait_until_ready()
