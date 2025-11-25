from .ShareTriage import ShareTriage

async def setup(bot):
    await bot.add_cog(ShareTriage(bot))
