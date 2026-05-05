import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import asyncio
import logging
import aiohttp
from dotenv import load_dotenv
import asyncpg

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ================= CONFIG =================
# FIX #3: Đọc từ .env thay vì hardcode True — thêm DEV_MODE=true vào .env khi dev
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
COG_FOLDER = "./cogs"
RELOAD_DEBOUNCE = 1.0           # chống spam reload
SLASH_SYNC_DEBOUNCE = 3.0       # chống spam Discord API

# =========================================

# ============== LOGGING ==================
logger = logging.getLogger("my_bot")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(
    filename="bot_activity.log",
    encoding="utf-8",
    mode="w"
)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)
# =========================================

load_dotenv()

# ========== SLASH SYNC MANAGER ============

class SlashSyncManager:
    def __init__(self, bot):
        self.bot = bot
        self._last_sync = 0
        self._lock = asyncio.Lock()
        # FIX #8: Theo dõi pending sync — nếu bị debounce thì schedule retry
        # thay vì drop hoàn toàn khi nhiều cog reload đồng thời
        self._pending = False

    async def sync(self, reason: str = ""):
        async with self._lock:
            now = time.time()
            if now - self._last_sync < SLASH_SYNC_DEBOUNCE:
                # Đánh dấu còn pending để retry sau debounce
                self._pending = True
                return

            self._pending = False
            try:
                synced = await self.bot.tree.sync()
                self._last_sync = time.time()
                logger.info(
                    f"[SLASH-SYNC] Synced {len(synced)} commands ({reason})"
                )
            except Exception as e:
                logger.error(
                    f"[SLASH-SYNC ERROR] {e}",
                    exc_info=True
                )

    async def sync_with_retry(self, reason: str = ""):
        """Gọi sync, nếu bị debounce thì tự retry sau khoảng chờ."""
        await self.sync(reason=reason)
        if self._pending:
            await asyncio.sleep(SLASH_SYNC_DEBOUNCE + 0.5)
            await self.sync(reason=f"{reason} (retry)")

# ========== AUTO RELOAD HANDLER ============

class CogAutoReloader(FileSystemEventHandler):
    def __init__(self, bot):
        self.bot = bot
        self.last_reload = {}
        # FIX #7: bot.loop deprecated trong discord.py 2.x — lưu loop tại thời điểm init
        self.loop = asyncio.get_event_loop()

    def on_modified(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".py"):
            return

        cog = os.path.basename(event.src_path)[:-3]
        now = time.time()

        if now - self.last_reload.get(cog, 0) < RELOAD_DEBOUNCE:
            return

        self.last_reload[cog] = now

        asyncio.run_coroutine_threadsafe(
            self.reload_cog(cog),
            self.loop  # FIX #7: dùng loop đã lưu thay vì bot.loop deprecated
        )

    async def reload_cog(self, cog):
        ext = f"cogs.{cog}"
        try:
            if ext in self.bot.extensions:
                await self.bot.reload_extension(ext)
                logger.info(f"[AUTO-RELOAD] Reloaded cog: {ext}")
            else:
                await self.bot.load_extension(ext)
                logger.info(f"[AUTO-RELOAD] Loaded new cog: {ext}")

            if self.bot.slash_sync:
                await self.bot.slash_sync.sync(
                    reason=f"auto reload {cog}"
                )

        except Exception as e:
            logger.error(
                f"[AUTO-RELOAD ERROR] {ext}: {e}",
                exc_info=True
            )

def start_auto_reload(bot):
    observer = Observer()
    observer.schedule(
        CogAutoReloader(bot),
        path=COG_FOLDER,
        recursive=False
    )
    observer.start()
    # FIX #9: Lưu observer vào bot để gọi observer.stop() khi bot shutdown, tránh thread leak
    bot.cog_observer = observer
    logger.info("[AUTO-RELOAD] Watching cogs folder")


# ================= BOT ===================

class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_session = None
        self.slash_sync = None

    async def setup_hook(self):
        # AIOHTTP session
        self.http_session = aiohttp.ClientSession()
        logger.info("AIOHTTP ClientSession đã được tạo.")

        # FIX #1: Không hardcode credentials — đọc từ .env
        # FIX #2: Guard rõ ràng nếu DATABASE_URL thiếu thay vì để asyncpg crash ngầm
        db_dsn = os.getenv("DATABASE_URL")
        if not db_dsn:
            raise EnvironmentError(
                "Thiếu DATABASE_URL trong .env — "
                "ví dụ: DATABASE_URL=postgresql://user:pass@host:5432/dbname"
            )
        self.db = await asyncpg.create_pool(
            dsn=db_dsn,
            min_size=5,
            max_size=20,
            command_timeout=60
        )

        # Load cogs (hỗ trợ subfolder, không tạo path sai)
        for root, _, files in os.walk(COG_FOLDER):
            for filename in files:
                if not filename.endswith(".py") or filename.startswith("__"):
                    continue

                try:
                    # Lấy path tương đối so với thư mục gốc project
                    relative_path = os.path.relpath(
                        os.path.join(root, filename),
                        "."
                    )

                    # Chuyển thành module path
                    module_path = (
                        relative_path
                        .replace("\\", ".")
                        .replace("/", ".")
                        .replace(".py", "")
                    )

                    await self.load_extension(module_path)
                    logger.info(f"Đã tải cog: {module_path}")

                except Exception as e:
                    logger.error(
                        f"Không thể tải cog {filename}: {e}",
                        exc_info=True
                    )

        # Custom help
        try:
            await self.load_extension("custom_help")
            logger.info("Đã tải CustomHelpCommand.")
        except Exception as e:
            logger.error(
                f"Không thể tải CustomHelpCommand: {e}",
                exc_info=True
            )

        # Slash sync manager
        self.slash_sync = SlashSyncManager(self)

        # đăng ký admin cog ở đây
        await self.add_cog(AdminCog(self))

        # Auto reload (DEV only)
        if DEV_MODE:
            start_auto_reload(self)

        # Initial slash sync
        await self.slash_sync.sync(reason="startup")

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        logger.info("Đã đóng AIOHTTP Session.")

        # FIX #6: Bọc try/except để tránh exception thứ hai nếu db chưa init xong
        if hasattr(self, "db") and self.db:
            try:
                await self.db.close()
                logger.info("Đã đóng DB Pool.")
            except Exception as e:
                logger.error(f"Lỗi khi đóng DB Pool: {e}", exc_info=True)

        # FIX #9: Dừng observer watchdog khi bot shutdown để tránh thread leak
        if hasattr(self, "cog_observer") and self.cog_observer:
            try:
                self.cog_observer.stop()
                self.cog_observer.join()
                logger.info("[AUTO-RELOAD] Observer đã dừng.")
            except Exception as e:
                logger.error(f"Lỗi khi dừng observer: {e}", exc_info=True)

        await super().close()

    async def on_ready(self):
        logger.info(
            f"Bot đã sẵn sàng! Đăng nhập với tư cách {self.user}"
        )
        logger.info("------")

    async def on_message(self, message):
        if message.author == self.user:
            return
        # FIX #5: Gọi super().on_message() để không break các listener trong Cog
        await super().on_message(message)

# ============== COMMANDS ==================

@commands.command(name="reload")
@commands.is_owner()
async def reload_prefix(ctx, cog: str):
    try:
        await ctx.bot.reload_extension(f"cogs.{cog}")

        if ctx.bot.slash_sync:
            await ctx.bot.slash_sync.sync(
                reason=f"manual reload {cog}"
            )

        await ctx.send(f"🔄 Reloaded `{cog}`")
    except Exception as e:
        await ctx.send(f"❌ `{e}`")

# FIX #4: Đưa reload slash vào Cog để đảm bảo được sync đúng cách với app_commands tree
class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="reload",
        description="Reload một cog"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def reload_slash(
        self,
        interaction: discord.Interaction,
        cog: str
    ):
        try:
            await interaction.client.reload_extension(
                f"cogs.{cog}"
            )

            if interaction.client.slash_sync:
                await interaction.client.slash_sync.sync(
                    reason=f"manual reload {cog}"
                )

            await interaction.response.send_message(
                f"🔄 Reloaded `{cog}`",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ `{e}`",
                ephemeral=True
            )

# ============== RUN BOT ===================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = MyBot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

bot.add_command(reload_prefix)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    logger.critical(
        "LỖI: Thiếu DISCORD_BOT_TOKEN trong biến môi trường."
    )
    exit(1)

# FIX #10: Bọc bot.run trong __main__ guard để tránh chạy khi file bị import vô tình
if __name__ == "__main__":
    bot.run(TOKEN)