from .Name_Finder import Name_Finder


async def setup(bot):
    await bot.add_cog(Name_Finder(bot))
