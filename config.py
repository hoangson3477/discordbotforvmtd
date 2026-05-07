"""
Centralized configuration for all cogs
"""
import os
import logging
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# ================= LOGGING =================
logger = logging.getLogger("my_bot")

# ================= SUPABASE CONFIG =================
class SupabaseConfig:
    """Centralized Supabase configuration"""
    
    # Main database (for most cogs)
    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://dmvzxsbptahdfefclsru.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    
    # Natgame database (separate project)
    NATGAME_SUPABASE_URL = os.getenv("NATGAME_SUPABASE_URL")
    NATGAME_SUPABASE_KEY = os.getenv("NATGAME_SUPABASE_KEY")
    
    @classmethod
    def validate_main(cls):
        """Validate main Supabase credentials"""
        if not cls.SUPABASE_KEY:
            raise EnvironmentError("[Config] Thiếu SUPABASE_KEY trong .env")
        return create_client(cls.SUPABASE_URL, cls.SUPABASE_KEY)
    
    @classmethod
    def validate_natgame(cls):
        """Validate Natgame Supabase credentials"""
        if not cls.NATGAME_SUPABASE_URL or not cls.NATGAME_SUPABASE_KEY:
            raise EnvironmentError("[Config] Thiếu NATGAME_SUPABASE_URL hoặc NATGAME_SUPABASE_KEY trong .env")
        return create_client(cls.NATGAME_SUPABASE_URL, cls.NATGAME_SUPABASE_KEY)

# ================= GOOGLE SHEETS CONFIG =================
class GoogleSheetsConfig:
    """Google Sheets configuration"""
    
    SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    CREDENTIALS_FILE = os.getenv("GOOGLE_SHEET_CREDENTIALS_FILE")
    CREDENTIALS_B64 = os.getenv("GOOGLE_SHEET_CREDENTIALS_B64")
    
    @classmethod
    def validate(cls):
        """Validate Google Sheets config"""
        if not cls.SHEET_ID:
            logger.warning("[Config] Không tìm thấy GOOGLE_SHEET_ID")
        return cls.SHEET_ID is not None

# ================= ROBLOX CONFIG =================
class RobloxConfig:
    """Roblox API configuration"""
    
    API_KEY = os.getenv("ROBLOX_OPENCLOUD_API_KEY")
    
    @classmethod
    def validate(cls):
        """Validate Roblox config"""
        return cls.API_KEY is not None

# ================= DISCORD CONFIG =================
class DiscordConfig:
    """Discord bot configuration"""
    
    TOKEN = os.getenv("DISCORD_TOKEN")
    DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
    
    @classmethod
    def validate(cls):
        """Validate Discord config"""
        if not cls.TOKEN:
            raise EnvironmentError("[Config] Thiếu DISCORD_TOKEN trong .env")
        return cls.TOKEN

# ================= VALIDATION =================
def validate_all():
    """Validate all required configurations"""
    try:
        SupabaseConfig.validate_main()
        SupabaseConfig.validate_natgame()
        DiscordConfig.validate()
        logger.info("[Config] All configurations validated successfully")
        return True
    except EnvironmentError as e:
        logger.error(f"[Config] Validation failed: {e}")
        return False
