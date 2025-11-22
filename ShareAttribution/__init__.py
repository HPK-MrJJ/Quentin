from .shareattribution import shareattribution

async def setup(bot):
    await bot.add_cog(shareattribution(bot))
