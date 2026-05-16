import discord
from discord.ext import commands
import os
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://dmvzxsbptahdfefclsru.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def one(res) -> dict | None:
    """Lấy phần tử đầu tiên từ kết quả Supabase, hoặc None nếu không có.
    Dùng thay cho maybe_single() vì maybe_single() trả về None object khi không có row.
    """
    return res.data[0] if res.data else None


def get_gang_by_name(guild_id: str, name: str) -> dict | None:
    res = (
        supabase.table("gangs")
        .select("*")
        .eq("guild_id", guild_id)
        .eq("name", name)
        .limit(1)
        .execute()
    )
    return one(res)


def get_gang_of_user(guild_id: str, user_id: str) -> tuple[dict | None, dict | None]:
    """Trả về (gang_row, member_row) hoặc (None, None)."""
    mem_res = (
        supabase.table("gang_members")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    member_row = one(mem_res)
    if not member_row:
        return None, None

    gang_res = (
        supabase.table("gangs")
        .select("*")
        .eq("id", member_row["gang_id"])
        .eq("guild_id", guild_id)
        .limit(1)
        .execute()
    )
    gang_row = one(gang_res)
    return (gang_row, member_row) if gang_row else (None, None)


def get_led_gang(guild_id: str, user_id: str) -> dict | None:
    """Trả về gang row nếu user_id là leader, ngược lại None."""
    res = (
        supabase.table("gangs")
        .select("*")
        .eq("guild_id", guild_id)
        .eq("leader_id", user_id)
        .limit(1)
        .execute()
    )
    return one(res)


def get_members_of_gang(gang_id: str) -> list[dict]:
    res = (
        supabase.table("gang_members")
        .select("*")
        .eq("gang_id", gang_id)
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────

class Gang(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invites: dict[str, str] = {}  # user_id -> gang_name

    # ── CREATE GANG ──────────────────────────
    @commands.command()
    async def creategang(self, ctx, *, name: str):
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        gang, _ = get_gang_of_user(guild_id, user_id)
        if gang:
            return await ctx.send("❌ Bạn đã ở trong một gang!")

        if get_gang_by_name(guild_id, name):
            return await ctx.send("❌ Gang đã tồn tại!")

        gang_res = (
            supabase.table("gangs")
            .insert({"guild_id": guild_id, "name": name, "leader_id": user_id})
            .execute()
        )
        gang_id = gang_res.data[0]["id"]

        supabase.table("gang_members").insert(
            {"gang_id": gang_id, "user_id": user_id, "rank_name": "Leader"}
        ).execute()

        await ctx.send(f"🔥 Đã tạo gang **{name}**!")

    # ── GANG INFO ────────────────────────────
    @commands.command()
    async def ganginfo(self, ctx, *, name: str = None):
        guild_id = str(ctx.guild.id)

        if not name:
            gang, _ = get_gang_of_user(guild_id, str(ctx.author.id))
            if not gang:
                return await ctx.send("❌ Bạn không thuộc gang nào.")
        else:
            gang = get_gang_by_name(guild_id, name)
            if not gang:
                return await ctx.send("❌ Không tìm thấy gang.")

        members = get_members_of_gang(gang["id"])

        embed = discord.Embed(title=f"🏴 Gang: {gang['name']}", color=discord.Color.red())

        leader = await self.bot.fetch_user(int(gang["leader_id"]))
        embed.add_field(name="Leader", value=leader.mention, inline=False)

        ranks: dict[str, list[str]] = {}
        for m in members:
            ranks.setdefault(m["rank_name"], []).append(m["user_id"])

        role_text = ""
        for rank, uids in ranks.items():
            mentions = []
            for uid in uids:
                user = await self.bot.fetch_user(int(uid))
                mentions.append(user.mention)
            role_text += f"**{rank}**: {', '.join(mentions)}\n"

        embed.add_field(name="Chức vụ", value=role_text or "Không có", inline=False)
        embed.set_footer(text=f"Tổng thành viên: {len(members)}")
        await ctx.send(embed=embed)

    # ── INVITE ───────────────────────────────
    @commands.command()
    async def invite(self, ctx, member: discord.Member):
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        gang = get_led_gang(guild_id, user_id)
        if not gang:
            return await ctx.send("❌ Chỉ Leader mới được mời.")

        target_id = str(member.id)
        existing = (
            supabase.table("gang_members")
            .select("id")
            .eq("gang_id", gang["id"])
            .eq("user_id", target_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return await ctx.send("❌ Người này đã trong gang.")

        self.invites[target_id] = gang["name"]
        await ctx.send(f"📩 Đã gửi lời mời vào gang **{gang['name']}** cho {member.mention}")

    @commands.command()
    async def accept(self, ctx):
        user_id = str(ctx.author.id)

        if user_id not in self.invites:
            return await ctx.send("❌ Bạn không có lời mời nào.")

        guild_id = str(ctx.guild.id)

        existing_gang, _ = get_gang_of_user(guild_id, user_id)
        if existing_gang:
            return await ctx.send("❌ Bạn đã thuộc một gang khác rồi.")

        gang_name = self.invites[user_id]
        gang = get_gang_by_name(guild_id, gang_name)
        if not gang:
            return await ctx.send("❌ Gang không còn tồn tại.")

        supabase.table("gang_members").insert(
            {"gang_id": gang["id"], "user_id": user_id, "rank_name": "Member"}
        ).execute()

        del self.invites[user_id]
        await ctx.send(f"🎉 Bạn đã tham gia gang **{gang_name}**!")

    # ── ADD RANK ─────────────────────────────
    @commands.command()
    async def addrank(self, ctx, *, role_name: str):
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        gang = get_led_gang(guild_id, user_id)
        if not gang:
            return await ctx.send("❌ Chỉ Leader mới tạo chức vụ.")

        members = get_members_of_gang(gang["id"])
        if role_name in {m["rank_name"] for m in members}:
            return await ctx.send("❌ Rank đã tồn tại.")

        await ctx.send(
            f"✅ Rank **{role_name}** đã được tạo. "
            f"Dùng `!setrank @member {role_name}` để gán thành viên."
        )

    # ── SET RANK ─────────────────────────────
    @commands.command()
    async def setrank(self, ctx, member: discord.Member, *, role_name: str):
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        gang = get_led_gang(guild_id, user_id)
        if not gang:
            return await ctx.send("❌ Chỉ Leader mới gán chức vụ.")

        target_id = str(member.id)
        mem_res = (
            supabase.table("gang_members")
            .select("*")
            .eq("gang_id", gang["id"])
            .eq("user_id", target_id)
            .limit(1)
            .execute()
        )
        mem_row = one(mem_res)
        if not mem_row:
            return await ctx.send("❌ Người này không thuộc gang.")

        supabase.table("gang_members").update({"rank_name": role_name}).eq(
            "id", mem_row["id"]
        ).execute()

        await ctx.send(f"🔰 Đã gán {member.mention} thành **{role_name}**")

    # ── LEAVE ────────────────────────────────
    @commands.command()
    async def leavegang(self, ctx):
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        gang, member_row = get_gang_of_user(guild_id, user_id)
        if not gang:
            return await ctx.send("❌ Bạn không thuộc gang nào.")

        if gang["leader_id"] == user_id:
            return await ctx.send("❌ Leader không thể rời gang. Hãy chuyển quyền trước.")

        supabase.table("gang_members").delete().eq("id", member_row["id"]).execute()
        await ctx.send("🚪 Bạn đã rời gang.")

    # ── GANG LIST ────────────────────────────
    @commands.command()
    async def ganglist(self, ctx):
        guild_id = str(ctx.guild.id)

        gangs_res = (
            supabase.table("gangs")
            .select("id, name")
            .eq("guild_id", guild_id)
            .execute()
        )
        if not gangs_res.data:
            return await ctx.send("❌ Server chưa có gang.")

        gang_counts = []
        for g in gangs_res.data:
            count_res = (
                supabase.table("gang_members")
                .select("id", count="exact")
                .eq("gang_id", g["id"])
                .execute()
            )
            gang_counts.append((g["name"], count_res.count or 0))

        gang_counts.sort(key=lambda x: x[1], reverse=True)

        text = "\n".join(
            f"{i}. **{name}** - {cnt} thành viên"
            for i, (name, cnt) in enumerate(gang_counts, start=1)
        )

        embed = discord.Embed(
            title="📜 Danh sách Gang (Top đông thành viên)",
            description=text,
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    # ── DELETE GANG ──────────────────────────
    @commands.command()
    async def deletegang(self, ctx):
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        gang = get_led_gang(guild_id, user_id)
        if not gang:
            return await ctx.send("❌ Chỉ Leader mới được xoá gang.")

        await ctx.send(
            f"⚠ Bạn chắc chắn muốn xoá gang **{gang['name']}**?\n"
            "Gõ `confirm` trong 15 giây để xác nhận."
        )

        def check(m):
            return (
                m.author == ctx.author
                and m.channel == ctx.channel
                and m.content.lower() == "confirm"
            )

        try:
            await self.bot.wait_for("message", timeout=15, check=check)
        except Exception:
            return await ctx.send("❌ Hết thời gian. Đã huỷ xoá gang.")

        supabase.table("gangs").delete().eq("id", gang["id"]).execute()
        self.invites = {uid: g for uid, g in self.invites.items() if g != gang["name"]}
        await ctx.send(f"💥 Gang **{gang['name']}** đã bị xoá.")

    # ── RENAME RANK ──────────────────────────
    @commands.command()
    async def renamerank(self, ctx, old_name: str, new_name: str):
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        gang = get_led_gang(guild_id, user_id)
        if not gang:
            return await ctx.send("❌ Chỉ Leader mới được sửa rank.")

        members = get_members_of_gang(gang["id"])
        if not any(m["rank_name"] == old_name for m in members):
            return await ctx.send("❌ Rank cũ không tồn tại.")
        if any(m["rank_name"] == new_name for m in members):
            return await ctx.send("❌ Rank mới đã tồn tại.")

        supabase.table("gang_members").update({"rank_name": new_name}).eq(
            "gang_id", gang["id"]
        ).eq("rank_name", old_name).execute()

        await ctx.send(f"✅ Đã đổi rank **{old_name}** thành **{new_name}**")

    # ── DELETE RANK ──────────────────────────
    @commands.command()
    async def deleterank(self, ctx, *, role_name: str):
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        gang = get_led_gang(guild_id, user_id)
        if not gang:
            return await ctx.send("❌ Chỉ Leader mới được xoá rank.")

        if role_name in ("Leader", "Member"):
            return await ctx.send("❌ Không thể xoá rank mặc định.")

        members = get_members_of_gang(gang["id"])
        if not any(m["rank_name"] == role_name for m in members):
            return await ctx.send("❌ Rank không tồn tại.")

        supabase.table("gang_members").update({"rank_name": "Member"}).eq(
            "gang_id", gang["id"]
        ).eq("rank_name", role_name).execute()

        await ctx.send(f"🗑 Đã xoá rank **{role_name}**, thành viên chuyển về Member.")


async def setup(bot):
    await bot.add_cog(Gang(bot))


# ─────────────────────────────────────────────
# SQL SCHEMA (chạy trong Supabase SQL Editor)
# ─────────────────────────────────────────────
#
# create table gangs (
#   id         uuid primary key default gen_random_uuid(),
#   guild_id   text not null,
#   name       text not null,
#   leader_id  text not null,
#   unique(guild_id, name)
# );
#
# create table gang_members (
#   id        uuid primary key default gen_random_uuid(),
#   gang_id   uuid references gangs(id) on delete cascade,
#   user_id   text not null,
#   rank_name text not null default 'Member',
#   unique(gang_id, user_id)
# );
#
# create index on gangs(guild_id);
# create index on gang_members(gang_id);
# create index on gang_members(user_id);