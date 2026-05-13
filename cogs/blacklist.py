import discord
from discord.ext import commands
import aiohttp
import logging
import time
from datetime import datetime, timedelta

from config import SupabaseConfig, RobloxConfig, logger

blacklist_logger = logging.getLogger("blacklist")

# Initialize clients
supabase = SupabaseConfig.validate_main()
ROBLOX_API_KEY = RobloxConfig.API_KEY

HEADERS = {
    "x-api-key": ROBLOX_API_KEY,
    "Content-Type": "application/json"
} if ROBLOX_API_KEY else {}

class RobloxBlacklist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Caching system
        self.group_cache = {}  # group_id -> info
        self.user_cache = {}  # username -> user_id
        self.cache_time = {}  # key -> timestamp
        self.CACHE_DURATION = timedelta(hours=1)
        
        # Rate limiting
        self.last_command = {}  # user_id -> timestamp
        self.RATE_LIMIT = 10  # seconds between commands

    # -------------------------
    # Helper methods
    # -------------------------
    def check_rate_limit(self, user_id: int) -> bool:
        """Check if user is rate limited"""
        now = time.time()
        if user_id in self.last_command:
            if now - self.last_command[user_id] < self.RATE_LIMIT:
                return False
        self.last_command[user_id] = now
        return True
    
    def is_cache_valid(self, key: str) -> bool:
        """Check if cache entry is still valid"""
        if key not in self.cache_time:
            return False
        return datetime.now() - self.cache_time[key] < self.CACHE_DURATION
    
    def update_cache(self, key: str, data):
        """Update cache with new data"""
        cache_type = "user" if key.startswith("user_") else "group"
        if cache_type == "user":
            self.user_cache[key] = data
        else:
            self.group_cache[key] = data
        self.cache_time[key] = datetime.now()

    # -------------------------
    # Roblox helpers
    # -------------------------
    async def get_user_id(self, username: str):
        """Get Roblox user ID with caching and error handling"""
        cache_key = f"user_{username}"
        
        # Check cache first
        if cache_key in self.user_cache and self.is_cache_valid(cache_key):
            return self.user_cache[cache_key]
        
        try:
            url = "https://users.roblox.com/v1/usernames/users"
            payload = {
                "usernames": [username],
                "excludeBannedUsers": False
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=HEADERS) as resp:
                    if resp.status != 200:
                        blacklist_logger.warning(f"Roblox API error: {resp.status}")
                        return None
                    
                    data = await resp.json()
                    if not data.get("data"):
                        return None
                    
                    user_id = data["data"][0]["id"]
                    self.update_cache(cache_key, user_id)
                    return user_id
                    
        except Exception as e:
            blacklist_logger.error(f"Error getting user ID for {username}: {e}")
            return None

    async def get_user_groups(self, user_id: int):
        """Get user's Roblox groups with error handling"""
        try:
            url = f"https://groups.roblox.com/v2/users/{user_id}/groups/roles"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        blacklist_logger.warning(f"Roblox groups API error: {resp.status}")
                        return []
                    
                    data = await resp.json()
                    return [g["group"]["id"] for g in data.get("data", [])]
                    
        except Exception as e:
            blacklist_logger.error(f"Error getting user groups for {user_id}: {e}")
            return []

    async def get_group_info(self, group_id: int):
        """Get group info with caching and error handling"""
        cache_key = f"group_{group_id}"
        
        # Check cache first
        if cache_key in self.group_cache and self.is_cache_valid(cache_key):
            return self.group_cache[cache_key]
        
        try:
            url = f"https://groups.roblox.com/v1/groups/{group_id}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        blacklist_logger.warning(f"Roblox group API error: {resp.status}")
                        return None
                    
                    data = await resp.json()

                    owner = data.get("owner")
                    owner_name = owner["username"] if owner else "Không có"

                    group_info = {
                        "id": data["id"],
                        "name": data["name"],
                        "owner": owner_name
                    }
                    
                    self.update_cache(cache_key, group_info)
                    return group_info
                    
        except Exception as e:
            blacklist_logger.error(f"Error getting group info for {group_id}: {e}")
            return None

    # -------------------------
    # Commands
    # -------------------------

    @commands.command(name="addblacklist")
    @commands.has_permissions(administrator=True)
    async def add_blacklist(self, ctx, group_id: int):
        # Rate limiting check
        if not self.check_rate_limit(ctx.author.id):
            return await ctx.reply("⏰ Vui lòng đợi 10 giây trước khi dùng lại.")
        
        # Input validation
        if group_id <= 0:
            return await ctx.reply("❌ Group ID phải là số dương.")
        
        # Check if group exists
        await ctx.reply("🔍 Đang kiểm tra thông tin group...")
        group_info = await self.get_group_info(group_id)
        if not group_info:
            return await ctx.reply("❌ Không tìm thấy group này trên Roblox.")
        
        try:
            supabase.table("roblox_blacklist_groups").insert({
                "group_id": group_id,
                "added_by": str(ctx.author.id),
                "added_at": datetime.utcnow().isoformat()
            }).execute()

            blacklist_logger.info(f"Group {group_id} ({group_info['name']}) added to blacklist by {ctx.author.id}")
            await ctx.reply(f"✅ Đã thêm group **{group_info['name']}** vào blacklist.")
            
        except Exception as e:
            if "duplicate" in str(e).lower():
                await ctx.reply("⚠️ Group này đã có trong blacklist.")
            else:
                blacklist_logger.error(f"Database error in add_blacklist: {e}")
                await ctx.reply("❌ Lỗi database. Vui lòng thử lại.")

    @commands.command(name="checkprofile")
    async def check_profile(self, ctx, username: str):
        # Rate limiting check
        if not self.check_rate_limit(ctx.author.id):
            return await ctx.reply("⏰ Vui lòng đợi 10 giây trước khi dùng lại.")
        
        # Input validation
        if not username or len(username.strip()) == 0:
            return await ctx.reply("❌ Username không được để trống.")
        
        if len(username) > 50:
            return await ctx.reply("❌ Username quá dài (tối đa 50 ký tự).")
        
        await ctx.reply(f"🔍 Đang kiểm tra profile **{username}**...")
        
        try:
            user_id = await self.get_user_id(username)
            if not user_id:
                return await ctx.reply("❌ Không tìm thấy username Roblox.")

            user_groups = await self.get_user_groups(user_id)
            if not user_groups:
                return await ctx.reply(f"ℹ️ User **{username}** không tham gia group nào.")

            # Get blacklist from database
            try:
                bl_groups = supabase.table("roblox_blacklist_groups") \
                    .select("group_id") \
                    .execute() \
                    .data
            except Exception as e:
                blacklist_logger.error(f"Database error in check_profile: {e}")
                return await ctx.reply("❌ Lỗi database. Vui lòng thử lại.")

            blacklist_ids = {g["group_id"] for g in bl_groups}
            violated = blacklist_ids.intersection(user_groups)

            embed = discord.Embed(
                title=f"Roblox Profile Check - {username}",
                color=discord.Color.red() if violated else discord.Color.green(),
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Username", value=username, inline=True)
            embed.add_field(name="🆔 User ID", value=user_id, inline=True)
            embed.add_field(name="🏷️ Total Groups", value=len(user_groups), inline=True)

            if violated:
                embed.add_field(
                    name="🚫 Vi phạm Blacklist",
                    value=f"Group IDs: {', '.join(str(g) for g in violated)}",
                    inline=False
                )
                embed.set_footer(text=f"Kiểm tra bởi {ctx.author.display_name}")
            else:
                embed.add_field(
                    name="✅ Kết quả",
                    value="Không nằm trong group blacklist",
                    inline=False
                )
                embed.set_footer(text=f"Kiểm tra bởi {ctx.author.display_name}")

            await ctx.reply(embed=embed)
            
        except Exception as e:
            blacklist_logger.error(f"Error in check_profile: {e}")
            await ctx.reply("❌ Lỗi khi kiểm tra profile. Vui lòng thử lại.")
    
    @commands.command(name="listblacklistgrps")
    @commands.has_permissions(administrator=True)
    async def list_blacklist_groups(self, ctx):
        # Rate limiting check
        if not self.check_rate_limit(ctx.author.id):
            return await ctx.reply("⏰ Vui lòng đợi 10 giây trước khi dùng lại.")
        
        try:
            # Get blacklist from database
            try:
                data = supabase.table("roblox_blacklist_groups") \
                    .select("group_id") \
                    .order("added_at") \
                    .execute() \
                    .data
            except Exception as e:
                blacklist_logger.error(f"Database error in list_blacklist_groups: {e}")
                return await ctx.reply("❌ Lỗi database. Vui lòng thử lại.")

            if not data:
                return await ctx.reply("Danh sách blacklist hiện đang trống.")

            await ctx.reply(f"🔍 Đang lấy thông tin **{len(data)}** group blacklist...")

            # Batch processing for better performance
            lines = []
            failed_count = 0
            
            for row in data:
                gid = row["group_id"]
                info = await self.get_group_info(gid)

                if not info:
                    lines.append(f"`{gid}` | ❌ Không lấy được thông tin")
                    failed_count += 1
                else:
                    lines.append(
                        f"`{info['id']}` | **{info['name']}** | Owner: {info['owner']}"
                    )

            # Split into multiple embeds if too many groups
            if len(lines) > 25:
                # Pagination for large lists
                pages = []
                for i in range(0, len(lines), 25):
                    page_lines = lines[i:i+25]
                    pages.append("\n".join(page_lines))
                
                for i, page_text in enumerate(pages):
                    embed = discord.Embed(
                        title=f"🚫 Roblox Group Blacklist (Page {i+1}/{len(pages)})",
                        description=page_text,
                        color=discord.Color.orange()
                    )
                    embed.set_footer(
                        text=f"Tổng: {len(data)} groups | Failed: {failed_count} | Page {i+1}/{len(pages)}"
                    )
                    await ctx.reply(embed=embed)
            else:
                # Single embed for smaller lists
                text = "\n".join(lines)
                embed = discord.Embed(
                    title="🚫 Danh sách Roblox Group Blacklist",
                    description=text,
                    color=discord.Color.orange()
                )
                embed.set_footer(
                    text=f"Tổng: {len(data)} groups | Failed: {failed_count}"
                )
                await ctx.reply(embed=embed)

        except Exception as e:
            blacklist_logger.error(f"Error in list_blacklist_groups: {e}")
            await ctx.reply("❌ Lỗi khi lấy danh sách blacklist. Vui lòng thử lại.")


async def setup(bot):
    await bot.add_cog(RobloxBlacklist(bot))
