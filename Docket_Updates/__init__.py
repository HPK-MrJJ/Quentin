from redbot.core import commands, Config

class Docket_Updates(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        
        # Initialize the Config object with a unique identifier
        self.config = Config.get_conf(self, identifier=69318888, force_registration=True)
        
        # Registering guild-specific settings
        self.config.register_guild(
            alerts_channel_id=None,  # Stores the ID of the channel to send alerts
            dates_by_case={},        # Dictionary to track dates by case ID
            auth_token=None          # Token used for API requests
        )
        
        # Start the daily message loop
        self.send_daily_message.start()

    def cog_unload(self):
        # Cancel the loop when the cog is unloaded
        self.send_daily_message.cancel()
