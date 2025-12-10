from .serverwrapped import ServerWrapped

async def setup(bot):
    await bot.add_cog(ServerWrapped(bot))
