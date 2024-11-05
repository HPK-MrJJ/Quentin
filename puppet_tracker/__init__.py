from .puppet_tracker import puppet_tracker


async def setup(bot):
    await bot.add_cog(puppet_tracker(bot))
