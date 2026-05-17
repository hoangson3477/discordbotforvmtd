# cogs/roblox_group.py

import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
from supabase import create_client, Client
import rblxopencloud

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://dmvzxsbptahdfefclsru.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

ARMY_GROUP_ID = 11329100
DIVISION_GROUP_ID = 12750636
OPEN_CLOUD_API_KEY = os.getenv("ROBLOX_OPENCLOUD_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ==========================
# WHITELIST HELPERS (Supabase)
# ==========================

async def has_whitelist_permission(command_name: str):
    def predicate_factory(command_name):
        async def predicate(ctx: commands.Context):
            user_id = ctx.author.id
            role_ids = [r.id for r in ctx.author.roles]

            # Check user whitelist
            res = supabase.table("whitelist") \
                .select("id") \
                .eq("command", command_name) \
                .eq("type", "user") \
                .eq("discord_id", user_id) \
                .execute()
            if res.data:
                return True

            # Check role whitelist
            if role_ids:
                res = supabase.table("whitelist") \
                    .select("id") \
                    .eq("command", command_name) \
                    .eq("type", "role") \
                    .in_("discord_id", role_ids) \
                    .execute()
                if res.data:
                    return True

            return False
        return predicate

    return commands.check(predicate_factory(command_name))

def wl_check(command_name: str):
    async def predicate(ctx: commands.Context):
        user_id = ctx.author.id
        role_ids = [r.id for r in ctx.author.roles]

        res = supabase.table("whitelist") \
            .select("id") \
            .eq("command", command_name) \
            .eq("type", "user") \
            .eq("discord_id", user_id) \
            .execute()
        if res.data:
            return True

        if role_ids:
            res = supabase.table("whitelist") \
                .select("id") \
                .eq("command", command_name) \
                .eq("type", "role") \
                .in_("discord_id", role_ids) \
                .execute()
            if res.data:
                return True

        return False

    return commands.check(predicate)


# ==========================
# ROBLOX BLOCKING HELPERS
# ==========================

def _do_promote(group, user_id: int):
    member = group.fetch_member(user_id)
    if not member:
        return None, None, "not_member"
    current_role = member.fetch_role()
    roles = sorted(group.list_roles(), key=lambda r: r.rank)
    next_role = next((r for r in roles if r.rank > current_role.rank), None)
    if not next_role:
        return current_role, None, "max_rank"
    group.update_member(user_id, role_id=next_role.id)
    return current_role, next_role, "ok"

def _do_demote(group, user_id: int):
    member = group.fetch_member(user_id)
    if not member:
        return None, None, "not_member"
    current_role = member.fetch_role()
    roles = sorted(group.list_roles(), key=lambda r: r.rank)
    prev_role = next((r for r in reversed(roles) if r.rank < current_role.rank), None)
    if not prev_role:
        return current_role, None, "min_rank"
    group.update_member(user_id, role_id=prev_role.id)
    return current_role, prev_role, "ok"

def _do_acpreq(division_group, user_id: int):
    existing = division_group.fetch_member(user_id)
    if existing:
        return "already_member"
    target = None
    for req in division_group.list_join_requests():
        if req.user_id == user_id:
            target = req
            break
    if not target:
        return "no_request"
    division_group.accept_join_request(user_id)
    return "ok"


# ==========================
# COG
# ==========================

class Prode(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = rblxopencloud.Group(ARMY_GROUP_ID, api_key=OPEN_CLOUD_API_KEY)
        self.division_group = rblxopencloud.Group(DIVISION_GROUP_ID, api_key=OPEN_CLOUD_API_KEY)

    async def fetch_roblox_user_id(self, username: str) -> int | None:
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {"usernames": [username], "excludeBannedUsers": True}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data.get("data"):
                    return data["data"][0]["id"]
                return None

    # ==========================
    # COMMAND: !promote
    # ==========================

    @commands.command(name="promote")
    @wl_check("promote")
    async def promote(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy Roblox user `{username}`.")

            current_role, next_role, status = await asyncio.to_thread(
                _do_promote, self.group, user_id
            )

            if status == "not_member":
                return await ctx.send(f"❌ `{username}` không ở trong group.")
            if status == "max_rank":
                return await ctx.send(f"ℹ️ `{username}` đã ở rank cao nhất.")

            await ctx.send(f"✅ `{username}` đã được promote **từ {current_role.name} → {next_role.name}**")

    @promote.error
    async def promote_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Bạn không có quyền dùng lệnh này.")
        else:
            await ctx.send(f"❌ Lỗi: `{error}`")
            raise error

    # ==========================
    # COMMAND: !demote
    # ==========================

    @commands.command(name="demote")
    @wl_check("promote")
    async def demote(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy Roblox user `{username}`.")

            current_role, prev_role, status = await asyncio.to_thread(
                _do_demote, self.group, user_id
            )

            if status == "not_member":
                return await ctx.send(f"❌ `{username}` không ở trong group.")
            if status == "min_rank":
                return await ctx.send(f"ℹ️ `{username}` đang ở rank thấp nhất rồi.")

            await ctx.send(f"⬇️ `{username}` đã bị demote **từ {current_role.name} → {prev_role.name}**")

    @demote.error
    async def demote_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Bạn không có quyền dùng lệnh này.")
        else:
            await ctx.send(f"❌ Lỗi: `{error}`")
            raise error

    # ==========================
    # COMMAND: !promotediv
    # ==========================

    @commands.command(name="promotediv")
    @wl_check("promote")
    async def promotediv(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy `{username}`.")

            current_role, next_role, status = await asyncio.to_thread(
                _do_promote, self.division_group, user_id
            )

            if status == "not_member":
                return await ctx.send(f"❌ `{username}` chưa ở trong Division.")
            if status == "max_rank":
                return await ctx.send(f"ℹ️ `{username}` đã ở Division rank cao nhất.")

            await ctx.send(f"✅ `{username}` được thăng cấp đơn vị **từ {current_role.name} → {next_role.name}**")

    @promotediv.error
    async def promotediv_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Bạn không có quyền dùng lệnh này.")
        else:
            await ctx.send(f"❌ Lỗi: `{error}`")
            raise error

    # ==========================
    # COMMAND: !demotediv
    # ==========================

    @commands.command(name="demotediv")
    @wl_check("promote")
    async def demotediv(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy `{username}`.")

            current_role, prev_role, status = await asyncio.to_thread(
                _do_demote, self.division_group, user_id
            )

            if status == "not_member":
                return await ctx.send(f"❌ `{username}` chưa ở trong Division.")
            if status == "min_rank":
                return await ctx.send(f"ℹ️ `{username}` đã ở Division rank thấp nhất.")

            await ctx.send(f"⬇️ `{username}` bị hạ cấp đơn vị **từ {current_role.name} → {prev_role.name}**")

    @demotediv.error
    async def demotediv_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Bạn không có quyền dùng lệnh này.")
        else:
            await ctx.send(f"❌ Lỗi: `{error}`")
            raise error

    # ==========================
    # COMMAND: !acpreq
    # ==========================

    @commands.command(name="acpreq")
    @wl_check("acpreq")
    async def acpreq(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy Roblox user `{username}`.")

            status = await asyncio.to_thread(_do_acpreq, self.division_group, user_id)

            if status == "already_member":
                return await ctx.send(f"ℹ️ `{username}` đã là thành viên của Division rồi.")
            if status == "no_request":
                return await ctx.send(
                    f"❌ Không tìm thấy join request của `{username}` trong Division.\n"
                    f"Họ có thể chưa gửi request, hoặc request đã bị xử lý rồi."
                )

            await ctx.send(f"✅ Đã accept join request của `{username}` vào **Division**!")

    @acpreq.error
    async def acpreq_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Bạn không có quyền dùng lệnh này.")
        else:
            await ctx.send(f"❌ Lỗi: `{error}`")
            raise error

    # ==========================
    # WHITELIST COMMANDS
    # ==========================

    @commands.group(name="wl", invoke_without_command=True)
    @commands.is_owner()
    async def wl(self, ctx):
        await ctx.send(
            "**Whitelist commands:**\n"
            "`!wl addrole <command> @Role`\n"
            "`!wl removerole <command> @Role`\n"
            "`!wl adduser <command> @User`\n"
            "`!wl removeuser <command> @User`\n"
            "`!wl show <command>`"
        )

    @wl.command(name="addrole")
    @commands.is_owner()
    async def wl_addrole(self, ctx, command: str, role: discord.Role):
        supabase.table("whitelist").upsert({
            "command": command,
            "type": "role",
            "discord_id": role.id
        }, on_conflict="command,type,discord_id").execute()
        await ctx.send(f"✅ Đã thêm role **{role.name}** vào whitelist `{command}`")

    @wl.command(name="removerole")
    @commands.is_owner()
    async def wl_removerole(self, ctx, command: str, role: discord.Role):
        supabase.table("whitelist") \
            .delete() \
            .eq("command", command) \
            .eq("type", "role") \
            .eq("discord_id", role.id) \
            .execute()
        await ctx.send(f"🗑️ Đã xoá role **{role.name}** khỏi whitelist `{command}`")

    @wl.command(name="adduser")
    @commands.is_owner()
    async def wl_adduser(self, ctx, command: str, user: discord.Member):
        supabase.table("whitelist").upsert({
            "command": command,
            "type": "user",
            "discord_id": user.id
        }, on_conflict="command,type,discord_id").execute()
        await ctx.send(f"✅ Đã thêm user **{user.display_name}** vào whitelist `{command}`")

    @wl.command(name="removeuser")
    @commands.is_owner()
    async def wl_removeuser(self, ctx, command: str, user: discord.Member):
        supabase.table("whitelist") \
            .delete() \
            .eq("command", command) \
            .eq("type", "user") \
            .eq("discord_id", user.id) \
            .execute()
        await ctx.send(f"🗑️ Đã xoá user **{user.display_name}** khỏi whitelist `{command}`")

    @wl.command(name="show")
    @commands.is_owner()
    async def wl_show(self, ctx, command: str):
        res = supabase.table("whitelist") \
            .select("type,discord_id") \
            .eq("command", command) \
            .execute()

        if not res.data:
            return await ctx.send(f"❌ Lệnh `{command}` chưa có whitelist.")

        roles = [f"<@&{r['discord_id']}>" for r in res.data if r["type"] == "role"]
        users = [f"<@{r['discord_id']}>" for r in res.data if r["type"] == "user"]

        await ctx.send(
            f"📄 **Whitelist `{command}`**\n"
            f"Roles: {', '.join(roles) or 'Không có'}\n"
            f"Users: {', '.join(users) or 'Không có'}"
        )


# ==========================
# SETUP
# ==========================

async def setup(bot: commands.Bot):
    await bot.add_cog(Prode(bot))