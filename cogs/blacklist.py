import discord
from discord.ext import commands
import aiohttp
import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = "https://dmvzxsbptahdfefclsru.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRtdnp4c2JwdGFoZGZlZmNsc3J1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTQ0Mjk2MywiZXhwIjoyMDg1MDE4OTYzfQ.dQjmeH1zafdur4ViwTxJekV86HfkQ1ODQ8Rh4KXPj5A" # dùng service role
ROBLOX_API_KEY = os.getenv("ROBLOX_OPENCLOUD_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

HEADERS = {
    "x-api-key": ROBLOX_API_KEY,
    "Content-Type": "application/json"
}

class RobloxBlacklist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -------------------------
    # Roblox helpers
    # -------------------------
    async def get_user_id(self, username: str):
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {
            "usernames": [username],
            "excludeBannedUsers": False
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if not data["data"]:
                    return None
                return data["data"][0]["id"]

    async def get_user_groups(self, user_id: int):
        url = f"https://groups.roblox.com/v2/users/{user_id}/groups/roles"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                return [g["group"]["id"] for g in data.get("data", [])]

    async def get_group_info(self, group_id: int):
        url = f"https://groups.roblox.com/v1/groups/{group_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

                owner = data.get("owner")
                owner_name = owner["username"] if owner else "Không có"

                return {
                    "id": data["id"],
                    "name": data["name"],
                    "owner": owner_name
                }

    # -------------------------
    # Commands
    # -------------------------

    @commands.command(name="addblacklist")
    @commands.has_permissions(administrator=True)
    async def add_blacklist(self, ctx, group_id: int):
        try:
            supabase.table("roblox_blacklist_groups").insert({
                "group_id": group_id
            }).execute()

            await ctx.reply(f"✅ Đã thêm group `{group_id}` vào blacklist.")
        except Exception as e:
            if "duplicate" in str(e).lower():
                await ctx.reply("⚠️ Group này đã có trong blacklist.")
            else:
                await ctx.reply(f"❌ Lỗi DB: `{e}`")

    @commands.command(name="checkprofile")
    async def check_profile(self, ctx, username: str):
        user_id = await self.get_user_id(username)
        if not user_id:
            return await ctx.reply("❌ Không tìm thấy username Roblox.")

        user_groups = await self.get_user_groups(user_id)

        bl_groups = supabase.table("roblox_blacklist_groups") \
            .select("group_id") \
            .execute() \
            .data

        blacklist_ids = {g["group_id"] for g in bl_groups}
        violated = blacklist_ids.intersection(user_groups)

        embed = discord.Embed(
            title="Roblox Profile Check",
            color=discord.Color.red() if violated else discord.Color.green()
        )
        embed.add_field(name="Username", value=username, inline=False)
        embed.add_field(name="User ID", value=user_id, inline=False)

        if violated:
            embed.add_field(
                name="Vi phạm blacklist",
                value=", ".join(str(g) for g in violated),
                inline=False
            )
        else:
            embed.add_field(
                name="Kết quả",
                value="Không nằm trong group blacklist",
                inline=False
            )

        await ctx.reply(embed=embed)
    
    @commands.command(name="listblacklistgrps")
    async def list_blacklist_groups(self, ctx):
        data = supabase.table("roblox_blacklist_groups") \
            .select("group_id") \
            .order("added_at") \
            .execute() \
            .data

        if not data:
            return await ctx.reply("Danh sách blacklist hiện đang trống.")

        await ctx.reply("Đang lấy thông tin group blacklist...")

        lines = []
        for row in data:
            gid = row["group_id"]
            info = await self.get_group_info(gid)

            if not info:
                lines.append(f"`{gid}` | ❌ Không lấy được thông tin")
                continue

            lines.append(
                f"`{info['id']}` | **{info['name']}** | Owner: {info['owner']}"
            )

        text = "\n".join(lines)

        embed = discord.Embed(
            title="🚫 Danh sách Roblox Group Blacklist",
            description=text,
            color=discord.Color.orange()
        )

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(RobloxBlacklist(bot))
