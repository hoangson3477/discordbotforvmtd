import discord
from discord.ext import commands
import json
import os

DATA_FILE = "gang_data.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


class Gang(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invites = {}  # user_id: gang_name

    # =========================
    # CREATE GANG
    # =========================
    @commands.command()
    async def creategang(self, ctx, *, name: str):
        data = load_data()
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        if guild_id not in data:
            data[guild_id] = {}

        # check đã trong gang chưa
        for gang in data[guild_id].values():
            if user_id in gang["members"]:
                return await ctx.send("❌ Bạn đã ở trong một gang!")

        if name in data[guild_id]:
            return await ctx.send("❌ Gang đã tồn tại!")

        data[guild_id][name] = {
            "leader": user_id,
            "roles": {
                "Leader": [user_id],
                "Member": []
            },
            "members": [user_id]
        }

        save_data(data)
        await ctx.send(f"🔥 Đã tạo gang **{name}**!")

    # =========================
    # GANG INFO
    # =========================
    @commands.command()
    async def ganginfo(self, ctx, *, name: str = None):
        data = load_data()
        guild_id = str(ctx.guild.id)

        if guild_id not in data:
            return await ctx.send("❌ Server chưa có gang nào.")

        if not name:
            # tìm gang của user
            for g_name, gang in data[guild_id].items():
                if str(ctx.author.id) in gang["members"]:
                    name = g_name
                    break

        if name not in data[guild_id]:
            return await ctx.send("❌ Không tìm thấy gang.")

        gang = data[guild_id][name]

        embed = discord.Embed(title=f"🏴 Gang: {name}", color=discord.Color.red())
        leader = await self.bot.fetch_user(int(gang["leader"]))
        embed.add_field(name="Leader", value=leader.mention, inline=False)

        role_text = ""
        for role, members in gang["roles"].items():
            mentions = []
            for m in members:
                member = await self.bot.fetch_user(int(m))
                mentions.append(member.mention)
            role_text += f"**{role}**: {', '.join(mentions) if mentions else 'Không ai'}\n"

        embed.add_field(name="Chức vụ", value=role_text, inline=False)
        embed.set_footer(text=f"Tổng thành viên: {len(gang['members'])}")

        await ctx.send(embed=embed)

    # =========================
    # INVITE
    # =========================
    @commands.command()
    async def invite(self, ctx, member: discord.Member):
        data = load_data()
        guild_id = str(ctx.guild.id)

        if guild_id not in data:
            return await ctx.send("❌ Không có gang nào.")

        for name, gang in data[guild_id].items():
            if gang["leader"] == str(ctx.author.id):
                if str(member.id) in gang["members"]:
                    return await ctx.send("❌ Người này đã trong gang.")
                self.invites[str(member.id)] = name
                return await ctx.send(f"📩 Đã gửi lời mời vào gang **{name}** cho {member.mention}")

        await ctx.send("❌ Chỉ Leader mới được mời.")

    @commands.command()
    async def accept(self, ctx):
        user_id = str(ctx.author.id)

        if user_id not in self.invites:
            return await ctx.send("❌ Bạn không có lời mời nào.")

        data = load_data()
        guild_id = str(ctx.guild.id)

        # 🔴 CHECK đã ở gang nào chưa
        for gang in data.get(guild_id, {}).values():
            if user_id in gang["members"]:
                return await ctx.send("❌ Bạn đã thuộc một gang khác rồi.")

        gang_name = self.invites[user_id]

        if gang_name not in data[guild_id]:
            return await ctx.send("❌ Gang không còn tồn tại.")

        data[guild_id][gang_name]["members"].append(user_id)
        data[guild_id][gang_name]["roles"]["Member"].append(user_id)

        save_data(data)
        del self.invites[user_id]

        await ctx.send(f"🎉 Bạn đã tham gia gang **{gang_name}**!")

    # =========================
    # ADD ROLE
    # =========================
    @commands.command()
    async def addrank(self, ctx, *, role_name: str):
        data = load_data()
        guild_id = str(ctx.guild.id)

        for gang in data.get(guild_id, {}).values():
            if gang["leader"] == str(ctx.author.id):
                if role_name in gang["roles"]:
                    return await ctx.send("❌ Role đã tồn tại.")
                gang["roles"][role_name] = []
                save_data(data)
                return await ctx.send(f"✅ Đã tạo chức vụ **{role_name}**")

        await ctx.send("❌ Chỉ Leader mới tạo chức vụ.")

    # =========================
    # SET ROLE
    # =========================
    @commands.command()
    async def setrank(self, ctx, member: discord.Member, *, role_name: str):
        data = load_data()
        guild_id = str(ctx.guild.id)

        for gang in data.get(guild_id, {}).values():
            if gang["leader"] == str(ctx.author.id):
                if role_name not in gang["roles"]:
                    return await ctx.send("❌ Role không tồn tại.")
                if str(member.id) not in gang["members"]:
                    return await ctx.send("❌ Người này không thuộc gang.")

                # remove khỏi role cũ
                for r in gang["roles"]:
                    if str(member.id) in gang["roles"][r]:
                        gang["roles"][r].remove(str(member.id))

                gang["roles"][role_name].append(str(member.id))
                save_data(data)
                return await ctx.send(f"🔰 Đã gán {member.mention} thành **{role_name}**")

        await ctx.send("❌ Chỉ Leader mới gán chức vụ.")

    # =========================
    # LEAVE
    # =========================
    @commands.command()
    async def leavegang(self, ctx):
        data = load_data()
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        for name, gang in data.get(guild_id, {}).items():
            if user_id in gang["members"]:
                if gang["leader"] == user_id:
                    return await ctx.send("❌ Leader không thể rời gang. Hãy chuyển quyền trước.")

                gang["members"].remove(user_id)
                for r in gang["roles"]:
                    if user_id in gang["roles"][r]:
                        gang["roles"][r].remove(user_id)

                save_data(data)
                return await ctx.send("🚪 Bạn đã rời gang.")

        await ctx.send("❌ Bạn không thuộc gang nào.")

    # =========================
    # LIST (SORT BY MEMBER COUNT DESC)
    # =========================
    @commands.command()
    async def ganglist(self, ctx):
        data = load_data()
        guild_id = str(ctx.guild.id)

        if guild_id not in data or not data[guild_id]:
            return await ctx.send("❌ Server chưa có gang.")

        gangs = data[guild_id]

        # 🔥 sort theo số thành viên giảm dần
        sorted_gangs = sorted(
            gangs.items(),
            key=lambda x: len(x[1]["members"]),
            reverse=True
        )

        text = ""
        for i, (name, gang) in enumerate(sorted_gangs, start=1):
            text += f"{i}. **{name}** - {len(gang['members'])} thành viên\n"

        embed = discord.Embed(
            title="📜 Danh sách Gang (Top đông thành viên)",
            description=text,
            color=discord.Color.gold()
        )

        await ctx.send(embed=embed)

    # =========================
    # DELETE GANG
    # =========================
    @commands.command()
    async def deletegang(self, ctx):
        data = load_data()
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        if guild_id not in data:
            return await ctx.send("❌ Server chưa có gang nào.")

        for name, gang in list(data[guild_id].items()):
            if gang["leader"] == user_id:

                confirm_msg = await ctx.send(
                    f"⚠ Bạn chắc chắn muốn xoá gang **{name}**?\n"
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
                except:
                    return await ctx.send("❌ Hết thời gian. Đã huỷ xoá gang.")

                # Xoá gang
                del data[guild_id][name]

                # Xoá invite còn tồn
                self.invites = {
                    uid: g for uid, g in self.invites.items() if g != name
                }

                save_data(data)

                return await ctx.send(f"💥 Gang **{name}** đã bị xoá.")

        await ctx.send("❌ Chỉ Leader mới được xoá gang.")

    # =========================
    # RENAME RANK (ALLOW LEADER RENAME)
    # =========================
    @commands.command()
    async def renamerank(self, ctx, old_name: str, new_name: str):
        data = load_data()
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        for gang in data.get(guild_id, {}).values():
            if gang["leader"] == user_id:

                if old_name not in gang["roles"]:
                    return await ctx.send("❌ Rank cũ không tồn tại.")

                if new_name in gang["roles"]:
                    return await ctx.send("❌ Rank mới đã tồn tại.")

                # 🔴 đảm bảo leader vẫn nằm trong rank leader
                if old_name == "Leader":
                    # đổi key nhưng vẫn giữ danh sách thành viên
                    gang["roles"][new_name] = gang["roles"].pop(old_name)

                    save_data(data)
                    return await ctx.send(
                        f"👑 Đã đổi tên rank Leader thành **{new_name}**"
                    )

                # rank thường
                gang["roles"][new_name] = gang["roles"].pop(old_name)

                save_data(data)
                return await ctx.send(
                    f"✅ Đã đổi rank **{old_name}** thành **{new_name}**"
                )

        await ctx.send("❌ Chỉ Leader mới được sửa rank.")

    # =========================
    # DELETE RANK
    # =========================
    @commands.command()
    async def deleterank(self, ctx, *, role_name: str):
        data = load_data()
        guild_id = str(ctx.guild.id)
        user_id = str(ctx.author.id)

        for gang in data.get(guild_id, {}).values():
            if gang["leader"] == user_id:

                if role_name not in gang["roles"]:
                    return await ctx.send("❌ Rank không tồn tại.")

                if role_name in ["Leader", "Member"]:
                    return await ctx.send("❌ Không thể xoá rank mặc định.")

                # chuyển toàn bộ member về Member
                for m in gang["roles"][role_name]:
                    gang["roles"]["Member"].append(m)

                del gang["roles"][role_name]

                save_data(data)
                return await ctx.send(f"🗑 Đã xoá rank **{role_name}**")

        await ctx.send("❌ Chỉ Leader mới được xoá rank.")

async def setup(bot):
    await bot.add_cog(Gang(bot))