import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Lấy credentials từ environment variables
SUPABASE_URL = os.getenv("NATGAME_SUPABASE_URL")
SUPABASE_KEY = os.getenv("NATGAME_SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise EnvironmentError(
        "Thiếu NATGAME_SUPABASE_URL hoặc NATGAME_SUPABASE_KEY trong .env"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

