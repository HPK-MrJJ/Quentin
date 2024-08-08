import discord
from redbot.core import commands as commands

def is_owner_overridable():
    # Similar to @commands.is_owner()
    # Unlike that, however, this check can be overridden with core Permissions
    def predicate(ctx):
        return False
    return red_commands.permissions_check(predicate)
    
class Roles(red_commands.Cog):

  def __init__(self, bot):
        self.bot = bot

  @commands.Cog.listener()
  async def on_message(self, message):
      if len(message.content) == 0:
          return
      first_char = message.content[0]
      ctx = await self.bot.get_context(message)
      if message.author.bot or not first_char.isalpha():
          return
