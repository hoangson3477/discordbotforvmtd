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
OPEN_CLOUD_API_KEY = os.getenv("ROBLOX_OPENCLOUD_API_KEY","d1q1acxgaUeTF34Yw44n5CFfXUlAFnaimkZwW2p5ZQRfVQamZXlKaGJHY2lPaUpTVXpJMU5pSXNJbXRwWkNJNkluTnBaeTB5TURJeExUQTNMVEV6VkRFNE9qVXhPalE1V2lJc0luUjVjQ0k2SWtwWFZDSjkuZXlKaGRXUWlPaUpTYjJKc2IzaEpiblJsY201aGJDSXNJbWx6Y3lJNklrTnNiM1ZrUVhWMGFHVnVkR2xqWVhScGIyNVRaWEoyYVdObElpd2lZbUZ6WlVGd2FVdGxlU0k2SW1ReGNURmhZM2huWVZWbFZFWXpORmwzTkRSdU5VTkdabGhWYkVGR2JtRnBiV3RhZDFjeWNEVmFVVkptVmxGaGJTSXNJbTkzYm1WeVNXUWlPaUl6TlRFek1EQTBOalk0SWl3aVpYaHdJam94TnpjNU1ETXdPREF5TENKcFlYUWlPakUzTnprd01qY3lNRElzSW01aVppSTZNVGMzT1RBeU56SXdNbjAuQkNiWWxwWWlMY0Nha1EtVVhKT3Rtc1hJUHFaN0NGT3FxWlByMHJUbmFiYm9mX2RnZmFKU3FPdldJUzBxR2NQYnE4cWRvcVhVeUtuaVR2TGluaF92QVE2MDdIYjhsOWFFbnh5SzVSUEZKbEpVbnJubHI3VThpZGREaXRLbE5xeXhBSnRNLThjTThLZGswZ1Z0eXlmYmVuMUpKaG1Jd3o3amFfOS1PSUdRV05WM3lYekZvYnZGd0F2V3kxOEF4MFMyajQyVlAzS3NtRXl0TnA4b2duempncGIzeTNCSG9reWxHdHE5LXk5amtTV2NRWEFFMUd2UUFjdFFOQnlDQ2txVUdtQXhLYXJIbkR1NUNvMVJfbTcyRnk1aTJ6dmZGRXFDb1N1Z3BzREtnTWtjZVFrdXJWa3NrWWY4d0dHcXhObi1GdHN0ZnZHVlNqS2E0d1RmY2dzNlhR")

# ==========================
# LOG CHANNELS
# ==========================
LOG_CHANNEL_PROMOTE = 1159862365030977617   # <-- thay bằng channel ID kênh promote
LOG_CHANNEL_DEMOTE  = 1402241366997729351   # <-- thay bằng channel ID kênh demote

# ==========================
# RANK SHORTCUTS (Division)
# key = rank number, value = shortcut
# ==========================
RANK_SHORTCUTS: dict[int, str] = {
    4:   "TSP",
    5:   "JDS",
    6:   "DS",
    7:   "SDS",
    8:   "HDS",
    9:   "LS",
    10:  "B.SGT",
    11:  "B.SGM",
    12:  "BSF",
    13:  "BAS",
}


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ==========================
# WHITELIST HELPERS
# ==========================

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


async def get_max_rank(command_name: str, ctx: commands.Context) -> int | None:
    user_id = ctx.author.id
    role_ids = [r.id for r in ctx.author.roles]
    results = []

    res = supabase.table("whitelist") \
        .select("max_rank") \
        .eq("command", command_name) \
        .eq("type", "user") \
        .eq("discord_id", user_id) \
        .execute()
    results.extend(res.data)

    if role_ids:
        res = supabase.table("whitelist") \
            .select("max_rank") \
            .eq("command", command_name) \
            .eq("type", "role") \
            .in_("discord_id", role_ids) \
            .execute()
        results.extend(res.data)

    if not results:
        return 0

    if any(r["max_rank"] is None for r in results):
        return None

    return max(r["max_rank"] for r in results)


# ==========================
# ROBLOX BLOCKING HELPERS
# ==========================

def _do_promote(group, user_id: int, max_rank: int | None):
    member = group.fetch_member(user_id)
    if not member:
        return None, None, "not_member"
    current_role = member.fetch_role()
    roles = sorted(group.list_roles(), key=lambda r: r.rank)
    next_role = next((r for r in roles if r.rank > current_role.rank), None)
    if not next_role:
        return current_role, None, "max_rank_global"
    if max_rank is not None and next_role.rank > max_rank:
        return current_role, next_role, "no_permission_rank"
    group.update_member(user_id, role_id=next_role.id)
    return current_role, next_role, "ok"

def _do_demote(group, user_id: int, max_rank: int | None):
    member = group.fetch_member(user_id)
    if not member:
        return None, None, "not_member"
    current_role = member.fetch_role()
    roles = sorted(group.list_roles(), key=lambda r: r.rank)
    prev_role = next((r for r in reversed(roles) if r.rank < current_role.rank), None)
    if not prev_role:
        return current_role, None, "min_rank"
    if max_rank is not None and current_role.rank > max_rank:
        return current_role, prev_role, "no_permission_rank"
    group.update_member(user_id, role_id=prev_role.id)
    return current_role, prev_role, "ok"

def _do_acpreq(division_group, user_id: int):
    existing = division_group.fetch_member(user_id)
    if existing:
        return "already_member"
    for req in division_group.list_join_requests():
        if req.id == user_id:
            req.accept()
            return "ok"
    return "no_request"


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

    async def send_log(self, action: str, username: str, current_role, next_role, done_by: discord.Member):
        """Gửi log vào kênh tương ứng. Skip nếu một trong hai rank không có trong RANK_SHORTCUTS."""
        if current_role.rank not in RANK_SHORTCUTS or next_role.rank not in RANK_SHORTCUTS:
            return

        channel_id = LOG_CHANNEL_PROMOTE if action == "promote" else LOG_CHANNEL_DEMOTE
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        from_label = RANK_SHORTCUTS[current_role.rank]
        to_label   = RANK_SHORTCUTS[next_role.rank]
        arrow      = "⬆️" if action == "promote" else "⬇️"

        await channel.send(
            f"{arrow} **{username}**: {from_label} → {to_label} "
            f"| by {done_by.mention}"
        )

    # ==========================
    # COMMAND: !promote
    # ==========================

    @commands.command(name="promote")
    @wl_check("promote")
    async def promote(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            max_rank = await get_max_rank("promote", ctx)
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy Roblox user `{username}`.")

            current_role, next_role, status = await asyncio.to_thread(
                _do_promote, self.group, user_id, max_rank
            )

            if status == "not_member":
                return await ctx.send(f"❌ `{username}` không ở trong group.")
            if status == "max_rank_global":
                return await ctx.send(f"ℹ️ `{username}` đã ở rank cao nhất.")
            if status == "no_permission_rank":
                return await ctx.send(
                    f"❌ Bạn chỉ được promote tới rank **{max_rank}** trở xuống.\n"
                    f"`{username}` sẽ lên **{next_role.name}** (rank {next_role.rank}) — vượt giới hạn."
                )

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
            max_rank = await get_max_rank("promote", ctx)
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy Roblox user `{username}`.")

            current_role, prev_role, status = await asyncio.to_thread(
                _do_demote, self.group, user_id, max_rank
            )

            if status == "not_member":
                return await ctx.send(f"❌ `{username}` không ở trong group.")
            if status == "min_rank":
                return await ctx.send(f"ℹ️ `{username}` đang ở rank thấp nhất rồi.")
            if status == "no_permission_rank":
                return await ctx.send(
                    f"❌ Bạn chỉ được demote người có rank **{max_rank}** trở xuống.\n"
                    f"`{username}` đang ở **{current_role.name}** (rank {current_role.rank}) — vượt giới hạn."
                )

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
            max_rank = await get_max_rank("promote", ctx)
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy `{username}`.")

            current_role, next_role, status = await asyncio.to_thread(
                _do_promote, self.division_group, user_id, max_rank
            )

            if status == "not_member":
                return await ctx.send(f"❌ `{username}` chưa ở trong Division.")
            if status == "max_rank_global":
                return await ctx.send(f"ℹ️ `{username}` đã ở Division rank cao nhất.")
            if status == "no_permission_rank":
                return await ctx.send(
                    f"❌ Bạn chỉ được promote tới rank **{max_rank}** trở xuống.\n"
                    f"`{username}` sẽ lên **{next_role.name}** (rank {next_role.rank}) — vượt giới hạn."
                )

            await ctx.send(f"✅ `{username}` được thăng cấp đơn vị **từ {current_role.name} → {next_role.name}**")
            await self.send_log("promote", username, current_role, next_role, ctx.author)

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
            max_rank = await get_max_rank("promote", ctx)
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy `{username}`.")

            current_role, prev_role, status = await asyncio.to_thread(
                _do_demote, self.division_group, user_id, max_rank
            )

            if status == "not_member":
                return await ctx.send(f"❌ `{username}` chưa ở trong Division.")
            if status == "min_rank":
                return await ctx.send(f"ℹ️ `{username}` đã ở Division rank thấp nhất.")
            if status == "no_permission_rank":
                return await ctx.send(
                    f"❌ Bạn chỉ được demote người có rank **{max_rank}** trở xuống.\n"
                    f"`{username}` đang ở **{current_role.name}** (rank {current_role.rank}) — vượt giới hạn."
                )

            await ctx.send(f"⬇️ `{username}` bị hạ cấp đơn vị **từ {current_role.name} → {prev_role.name}**")
            await self.send_log("demote", username, current_role, prev_role, ctx.author)

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
            "`!wl addrole <command> @Role [max_rank]`\n"
            "`!wl removerole <command> @Role`\n"
            "`!wl adduser <command> @User [max_rank]`\n"
            "`!wl removeuser <command> @User`\n"
            "`!wl show <command>`\n\n"
            "💡 `max_rank` là rank tối đa được phép promote/demote tới. Bỏ trống = không giới hạn."
        )

    @wl.command(name="addrole")
    @commands.is_owner()
    async def wl_addrole(self, ctx, command: str, role: discord.Role, max_rank: int = None):
        supabase.table("whitelist").upsert({
            "command": command,
            "type": "role",
            "discord_id": role.id,
            "max_rank": max_rank
        }, on_conflict="command,type,discord_id").execute()

        limit_text = f"rank tối đa **{max_rank}**" if max_rank is not None else "**không giới hạn**"
        await ctx.send(f"✅ Đã thêm role **{role.name}** vào whitelist `{command}` — {limit_text}")

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
    async def wl_adduser(self, ctx, command: str, user: discord.Member, max_rank: int = None):
        supabase.table("whitelist").upsert({
            "command": command,
            "type": "user",
            "discord_id": user.id,
            "max_rank": max_rank
        }, on_conflict="command,type,discord_id").execute()

        limit_text = f"rank tối đa **{max_rank}**" if max_rank is not None else "**không giới hạn**"
        await ctx.send(f"✅ Đã thêm user **{user.display_name}** vào whitelist `{command}` — {limit_text}")

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
            .select("type,discord_id,max_rank") \
            .eq("command", command) \
            .execute()

        if not res.data:
            return await ctx.send(f"❌ Lệnh `{command}` chưa có whitelist.")

        role_lines = []
        user_lines = []

        for r in res.data:
            limit = f"max rank {r['max_rank']}" if r["max_rank"] is not None else "không giới hạn"
            if r["type"] == "role":
                role_lines.append(f"<@&{r['discord_id']}> ({limit})")
            else:
                user_lines.append(f"<@{r['discord_id']}> ({limit})")

        await ctx.send(
            f"📄 **Whitelist `{command}`**\n"
            f"Roles: {', '.join(role_lines) or 'Không có'}\n"
            f"Users: {', '.join(user_lines) or 'Không có'}"
        )


# ==========================
# SETUP
# ==========================

async def setup(bot: commands.Bot):
    await bot.add_cog(Prode(bot))