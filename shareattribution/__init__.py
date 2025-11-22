from .ShareAttribution import ShareAttribution

async def setup(bot):
    await bot.add_cog(ShareAttribution(bot))
