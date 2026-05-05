# cogs/roblox_group.py

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
from pathlib import Path
import rblxopencloud

WHITELIST_PATH = Path("config/whitelist.json")

# Thay bằng ID Group Roblox bạn muốn quản lý
ARMY_GROUP_ID = 11329100  
DIVISION_GROUP_ID = 12750636
# Open Cloud API key có quyền đổi rank
OPEN_CLOUD_API_KEY = "d1q1acxgaUeTF34Yw44n5PKT7FeQzM8WalOc/S/OOfl97P3VZXlKaGJHY2lPaUpTVXpJMU5pSXNJbXRwWkNJNkluTnBaeTB5TURJeExUQTNMVEV6VkRFNE9qVXhPalE1V2lJc0luUjVjQ0k2SWtwWFZDSjkuZXlKaGRXUWlPaUpTYjJKc2IzaEpiblJsY201aGJDSXNJbWx6Y3lJNklrTnNiM1ZrUVhWMGFHVnVkR2xqWVhScGIyNVRaWEoyYVdObElpd2lZbUZ6WlVGd2FVdGxlU0k2SW1ReGNURmhZM2huWVZWbFZFWXpORmwzTkRSdU5WQkxWRGRHWlZGNlRUaFhZV3hQWXk5VEwwOVBabXc1TjFBelZpSXNJbTkzYm1WeVNXUWlPaUl6TlRFek1EQTBOalk0SWl3aVpYaHdJam94TnpZM056RTBNamMwTENKcFlYUWlPakUzTmpjM01UQTJOelFzSW01aVppSTZNVGMyTnpjeE1EWTNOSDAuRmxDOVdLbUxUbFRtZkxJWlNrWndCSTEtUzdSTmwwSmJGNXVKMFdTZFpfa2thN2lrM21XQlExYjdnVW83dm5Qb3hfdGpGQ0V1dXlETlF3dmk4Xy1GVHFsaGY5V0ItMUlURnd2enNPeGh2UGlZSGNXZmp5TzZFbUEzX1NUWjRYS1pzSlN0dTFUMFJBbnZwUll6WFk2NUJUQ01lNWg1bUV0MFJmVFFiUzlHTHFvN2NjRTBCNzBweU1NNHNWX3JGNGRRT3dWNUVwdVh6Y1l1YzZtd2Y5Y0hTUGNkMGVMU3NzZ3ZucnBUTENlZWNoV205VjV3bHZqVjJHWDF4RmF1dGNvQ0s1TmluclV3VkQ1U0FrTjBSQVpfLXZEeFRpS0F3ajNDeWxiNHZMRlN1amJVbGZpZ19nWW1rVlplbUJLWlZZR2lrSG12OHlmMElUZElkbkdRQW1NcW5R"


# ==========================
# WHITELIST HELPERS
# ==========================

def load_whitelist():
    if not WHITELIST_PATH.exists():
        return {}
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_whitelist(data):
    WHITELIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WHITELIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def has_whitelist_permission(command_name: str):
    async def predicate(ctx: commands.Context):
        data = load_whitelist()
        entry = data.get(command_name)

        if not entry:
            return False

        # user whitelist
        if ctx.author.id in entry.get("users", []):
            return True

        # role whitelist
        user_roles = {r.id for r in ctx.author.roles}
        allowed_roles = set(entry.get("roles", []))

        return bool(user_roles & allowed_roles)

    return commands.check(predicate)

# ==========================
# COG
# ==========================

class Prode(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.group = rblxopencloud.Group(
            ARMY_GROUP_ID,
            api_key=OPEN_CLOUD_API_KEY
        )

        self.division_group = rblxopencloud.Group(
            DIVISION_GROUP_ID,
            api_key=OPEN_CLOUD_API_KEY
        )

    def get_next_role(self, group, current_role, direction="up"):
        roles = sorted(group.list_roles(), key=lambda r: r.rank)

        if direction == "up":
            for r in roles:
                if r.rank > current_role.rank:
                    return r
        else:
            for r in reversed(roles):
                if r.rank < current_role.rank:
                    return r

        return None

    # --------------------------
    # ROBLOX USER ID
    # --------------------------

    async def fetch_roblox_user_id(self, username: str) -> int | None:
        url = "https://users.roblox.com/v1/usernames/users"
        payload = {
            "usernames": [username],
            "excludeBannedUsers": True
        }

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
    @has_whitelist_permission("promote")
    async def promote(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy Roblox user `{username}`.")

            member = self.group.fetch_member(user_id)
            if not member:
                return await ctx.send(f"❌ `{username}` không ở trong group.")

            current_role = member.fetch_role()
            roles = sorted(self.group.list_roles(), key=lambda r: r.rank)
            next_role = next((r for r in roles if r.rank > current_role.rank), None)

            if not next_role:
                return await ctx.send(f"ℹ️ `{username}` đã ở rank cao nhất.")

            self.group.update_member(user_id, role_id=next_role.id)

            await ctx.send(
                f"✅ `{username}` đã được promote "
                f"**từ {current_role.name} → {next_role.name}**"
            )

    @promote.error
    async def promote_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Bạn không có quyền dùng lệnh này.")

    # ==========================
    # COMMAND: !demote
    # ==========================

    @commands.command(name="demote")
    @has_whitelist_permission("promote")  # dùng chung whitelist với promote
    async def demote(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy Roblox user `{username}`.")

            member = self.group.fetch_member(user_id)
            if not member:
                return await ctx.send(f"❌ `{username}` không ở trong group.")

            current_role = member.fetch_role()

            roles = sorted(self.group.list_roles(), key=lambda r: r.rank)

            prev_role = None
            for r in reversed(roles):
                if r.rank < current_role.rank:
                    prev_role = r
                    break

            if not prev_role:
                return await ctx.send(f"ℹ️ `{username}` đang ở rank thấp nhất rồi.")

            self.group.update_member(user_id, role_id=prev_role.id)

            await ctx.send(
                f"⬇️ `{username}` đã bị demote "
                f"**từ {current_role.name} → {prev_role.name}**"
            )


    @demote.error
    async def demote_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Bạn không có quyền dùng lệnh này.")


    @commands.command(name="promotediv")
    @has_whitelist_permission("promote")
    async def promotediv(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy `{username}`.")

            member = self.division_group.fetch_member(user_id)
            if not member:
                return await ctx.send(f"❌ `{username}` chưa ở trong Division.")

            current_role = member.fetch_role()
            next_role = self.get_next_role(
                self.division_group,
                current_role,
                direction="up"
            )

            if not next_role:
                return await ctx.send(f"ℹ️ `{username}` đã ở Division rank cao nhất.")

            self.division_group.update_member(
                user_id,
                role_id=next_role.id
            )

            await ctx.send(
                f" `{username}` được thăng cấp đơn vị "
                f"**từ {current_role.name} → {next_role.name}**"
            )


    @promotediv.error
    async def promotediv_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Bạn không có quyền dùng lệnh này.")

    @commands.command(name="demotediv")
    @has_whitelist_permission("promote")
    async def demotediv(self, ctx: commands.Context, username: str):
        async with ctx.typing():
            user_id = await self.fetch_roblox_user_id(username)
            if not user_id:
                return await ctx.send(f"❌ Không tìm thấy `{username}`.")

            member = self.division_group.fetch_member(user_id)
            if not member:
                return await ctx.send(f"❌ `{username}` chưa ở trong Division.")

            current_role = member.fetch_role()
            prev_role = self.get_next_role(
                self.division_group,
                current_role,
                direction="down"
            )

            if not prev_role:
                return await ctx.send(f"ℹ️ `{username}` đã ở Division rank thấp nhất.")

            self.division_group.update_member(
                user_id,
                role_id=prev_role.id
            )

            await ctx.send(
                f"`{username}` bị hạ cấp đơn vị "
                f"**từ {current_role.name} → {prev_role.name}**"
            )


    @demotediv.error
    async def demotediv_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Bạn không có quyền dùng lệnh này.")



    # ==========================
    # WHITELIST PREFIX COMMANDS
    # ==========================

    @commands.group(name="wl", invoke_without_command=True)
    @commands.is_owner()
    async def wl(self, ctx):
        await ctx.send(
            "**Whitelist commands:**\n"
            "`!wl addrole <command> @Role`\n"
            "`!wl removerole <command> @Role`\n"
            "`!wl show <command>`"
        )

    @wl.command(name="addrole")
    @commands.is_owner()
    async def wl_addrole(self, ctx, command: str, role: discord.Role):
        data = load_whitelist()
        data.setdefault(command, {"roles": [], "users": []})

        if role.id not in data[command]["roles"]:
            data[command]["roles"].append(role.id)
            save_whitelist(data)

        await ctx.send(
            f"✅ Đã thêm role **{role.name}** vào whitelist `{command}`"
        )

    @wl.command(name="removerole")
    @commands.is_owner()
    async def wl_removerole(self, ctx, command: str, role: discord.Role):
        data = load_whitelist()

        if command in data and role.id in data[command]["roles"]:
            data[command]["roles"].remove(role.id)
            save_whitelist(data)

        await ctx.send(
            f"🗑️ Đã xoá role **{role.name}** khỏi whitelist `{command}`"
        )

    @wl.command(name="show")
    @commands.is_owner()
    async def wl_show(self, ctx, command: str):
        data = load_whitelist()
        entry = data.get(command)

        if not entry:
            return await ctx.send("❌ Lệnh chưa có whitelist.")

        roles = ", ".join(f"<@&{r}>" for r in entry["roles"]) or "Không có"
        users = ", ".join(f"<@{u}>" for u in entry["users"]) or "Không có"

        await ctx.send(
            f"📄 **Whitelist `{command}`**\n"
            f"Roles: {roles}\n"
            f"Users: {users}"
        )

# ==========================
# SETUP
# ==========================

async def setup(bot: commands.Bot):
    await bot.add_cog(Prode(bot))