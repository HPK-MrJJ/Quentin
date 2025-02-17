from .Quests import Quests

async def setup(bot):
    await bot.add_cog(Quests(bot))
