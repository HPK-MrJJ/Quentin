from .Docket_Updates import Docket_Updates


async def setup(bot):
    await bot.add_cog(Docket_Updates(bot))
