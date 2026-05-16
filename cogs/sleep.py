import discord
from discord.ext import commands
import asyncio

class SleepCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sleeping_users = {}  # {user_id: message}

    @commands.command(name="ngủ", aliases=["ngu", "sleep", "ngu"])
    async def ngu(self, ctx, *, lý_do: str = None):
        """Đi ngủ và đặt trạng thái ngủ cho bản thân."""
        user = ctx.author

        if user.id in self.sleeping_users:
            await ctx.send(f"😴 {user.mention} đang ngủ ròi óooooo! Dậy đi cậu oiiii~")
            return

        # Lưu trạng thái ngủ
        self.sleeping_users[user.id] = lý_do or "đang ngủ như con mel lun"

        embed = discord.Embed(
            title="💤 Đi Ngủ Thôi!",
            description=f"{user.mention} đã đi ngủ như một con mồn lèo ròi~  Đừng làm phiền con mel nhé!",
            color=discord.Color.dark_blue()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        if lý_do:
            embed.add_field(name="📝 Lý do", value=lý_do, inline=False)
        embed.set_footer(text="Gõ !dậy để thức dậy | Nhắn tin vào sẽ tự động báo đang ngủ")

        await ctx.send(embed=embed)

        # Cố gắng đổi nickname (cần quyền)
        try:
            original_nick = user.display_name
            new_nick = f"😴 {original_nick[:28]}"
            await user.edit(nick=new_nick)
        except discord.Forbidden:
            pass  # Không có quyền đổi nick thì thôi

    @commands.command(name="dậy", aliases=["day", "thức", "thuc", "wake"])
    async def day(self, ctx):
        """Thức dậy, xóa trạng thái ngủ."""
        user = ctx.author

        if user.id not in self.sleeping_users:
            await ctx.send(f"☀️ {user.mention} đang thức rồi mà, chưa ngủ thì dậy kiểu gì 😄")
            return

        del self.sleeping_users[user.id]

        embed = discord.Embed(
            title="☀️ Dậy Rồi!",
            description=f"{user.mention} đã thức dậy! Chào buổi sáng~ (hoặc buổi gì đó 😄)",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        await ctx.send(embed=embed)

        # Khôi phục nickname
        try:
            nick = user.nick
            if nick and nick.startswith("😴 "):
                await user.edit(nick=nick[3:] or None)
        except discord.Forbidden:
            pass

    @commands.command(name="ngủchưa", aliases=["nguai", "sleeping"])
    async def ngu_chua(self, ctx, member: discord.Member = None):
        """Kiểm tra xem ai đó có đang ngủ không."""
        if member is None:
            # Liệt kê tất cả đang ngủ
            if not self.sleeping_users:
                await ctx.send("✅ Không có ai đang ngủ cả!")
                return

            embed = discord.Embed(
                title="😴 Danh Sách Đang Ngủ",
                color=discord.Color.dark_blue()
            )
            for uid, reason in self.sleeping_users.items():
                member_obj = ctx.guild.get_member(uid)
                name = member_obj.display_name if member_obj else f"User {uid}"
                embed.add_field(name=f"💤 {name}", value=reason, inline=False)
            await ctx.send(embed=embed)
        else:
            if member.id in self.sleeping_users:
                reason = self.sleeping_users[member.id]
                await ctx.send(f"😴 {member.mention} đang ngủ nè! ({reason})")
            else:
                await ctx.send(f"☀️ {member.mention} đang thức đấy!")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Tự động trả lời khi có người mention người đang ngủ."""
        if message.author.bot:
            return

        # Nếu chính người đang ngủ gõ tin nhắn -> nhắc nhở
        if message.author.id in self.sleeping_users:
            if not message.content.startswith(("!dậy", "!day", "!thức", "!wake")):
                reason = self.sleeping_users[message.author.id]
                await message.channel.send(
                    f"😴 {message.author.mention} ơi, bạn đang ngủ mà ({reason})! Gõ `!dậy` nếu muốn thức.",
                    delete_after=10
                )
            return

        # Nếu mention người đang ngủ
        for mentioned in message.mentions:
            if mentioned.id in self.sleeping_users:
                reason = self.sleeping_users[mentioned.id]
                await message.channel.send(
                    f"🤫 Psst! {mentioned.display_name} đang ngủ rồi~ ({reason})\n"
                    f"Nhắn tin sau nhé {message.author.mention}!",
                    delete_after=15
                )


async def setup(bot):
    await bot.add_cog(SleepCog(bot))