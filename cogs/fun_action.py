import discord
from discord.ext import commands
import asyncio
import random
import logging

from config import SupabaseConfig, logger

class MarryView(discord.ui.View):
    def __init__(self, proposer, target, save_callback):
        super().__init__(timeout=60)
        self.proposer = proposer
        self.target = target
        self.save_callback = save_callback
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "Bạn không phải người được cầu hôn 😐",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Đồng ý 💍", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True

        # GỌI HÀM LƯU DATABASE
        await self.save_callback(self.proposer.id, self.target.id)

        await interaction.response.edit_message(
            content=f"💍 {self.proposer.mention} và {self.target.mention} đã trở thành vợ chồng hợp pháp!",
            view=None
        )
        self.stop()

    @discord.ui.button(label="Từ chối 💔", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.edit_message(
            content=f"{self.target.mention} đã từ chối lời cầu hôn của {self.proposer.mention} 😭",
            view=None
        )
        self.stop()

class FunActions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = SupabaseConfig.validate_main()

    def get_target(self, ctx):
        if not ctx.message.mentions:
            return None
        return ctx.message.mentions[0]

    def check_target(self, ctx, target):
        if not target:
            return "Bạn phải tag người trước 😐"
        if target == ctx.author:
            return "Tự làm với bản thân luôn à? 🤨"
        return None

    # -------- OLD COMMANDS --------

    @commands.command(name="kiss")
    async def kiss(self, ctx):
        target = self.get_target(ctx)
        err = self.check_target(ctx, target)
        if err:
            return await ctx.reply(err)

        msgs = [
            f"{ctx.author.mention} hôn {target.mention} 😘",
            f"{target.mention} vừa bị {ctx.author.mention} hôn lén!",
            f"{ctx.author.mention} trao nụ hôn cho {target.mention} 💋"
        ]
        await ctx.send(random.choice(msgs))

    @commands.command(name="hug")
    async def hug(self, ctx):
        target = self.get_target(ctx)
        err = self.check_target(ctx, target)
        if err:
            return await ctx.reply(err)

        msgs = [
            f"{ctx.author.mention} ôm {target.mention} thật chặt 🤗",
            f"{target.mention} được {ctx.author.mention} ôm ấm áp",
            f"{ctx.author.mention} chạy tới ôm {target.mention}"
        ]
        await ctx.send(random.choice(msgs))

    @commands.command(name="slap")
    async def slap(self, ctx):
        target = self.get_target(ctx)
        err = self.check_target(ctx, target)
        if err:
            return await ctx.reply(err)

        msgs = [
            f"{ctx.author.mention} tát {target.mention} một cái đau điếng 🖐️",
            f"{target.mention} vừa ăn cú vả từ {ctx.author.mention} 💥",
            f"{ctx.author.mention} vả {target.mention} không trượt phát nào!"
        ]
        await ctx.send(random.choice(msgs))

    @commands.command(name="bully")
    async def bully(self, ctx):
        target = self.get_target(ctx)
        err = self.check_target(ctx, target)
        if err:
            return await ctx.reply(err)

        msgs = [
            f"{ctx.author.mention} đang bắt nạt {target.mention} 😈",
            f"{target.mention} bị {ctx.author.mention} trêu suốt ngày!",
            f"{ctx.author.mention} không tha cho {target.mention} hôm nay!"
        ]
        await ctx.send(random.choice(msgs))

    # -------- NEW COMMANDS --------

    @commands.command(name="pat")
    async def pat(self, ctx):
        target = self.get_target(ctx)
        err = self.check_target(ctx, target)
        if err:
            return await ctx.reply(err)

        msgs = [
            f"{ctx.author.mention} xoa đầu {target.mention} 😊",
            f"{target.mention} được {ctx.author.mention} vỗ đầu",
            f"{ctx.author.mention} pat pat {target.mention}!"
        ]
        await ctx.send(random.choice(msgs))

    @commands.command(name="poke")
    async def poke(self, ctx):
        target = self.get_target(ctx)
        err = self.check_target(ctx, target)
        if err:
            return await ctx.reply(err)

        msgs = [
            f"{ctx.author.mention} chọc {target.mention} 👉",
            f"{target.mention} bị {ctx.author.mention} poke liên tục!",
            f"{ctx.author.mention} lén chọc {target.mention} một cái"
        ]
        await ctx.send(random.choice(msgs))

    @commands.command(name="bite")
    async def bite(self, ctx):
        target = self.get_target(ctx)
        err = self.check_target(ctx, target)
        if err:
            return await ctx.reply(err)

        msgs = [
            f"{ctx.author.mention} cắn {target.mention} một cái 🐺",
            f"{target.mention} bị {ctx.author.mention} cắn!",
            f"{ctx.author.mention} cắn trộm {target.mention}"
        ]
        await ctx.send(random.choice(msgs))

    @commands.command(name="punch")
    async def punch(self, ctx):
        target = self.get_target(ctx)
        err = self.check_target(ctx, target)
        if err:
            return await ctx.reply(err)

        msgs = [
            f"{ctx.author.mention} đấm {target.mention} 💢",
            f"{target.mention} lãnh cú đấm từ {ctx.author.mention}!",
            f"{ctx.author.mention} tung cú đấm vào {target.mention} 🥊"
        ]
        await ctx.send(random.choice(msgs))

    @commands.command(name="ship")
    async def ship(self, ctx):
        mentions = ctx.message.mentions

        if len(mentions) == 0:
            return await ctx.reply("Tag 2 người để ship nhé 💞")
        
        if len(mentions) == 1:
            user1 = ctx.author
            user2 = mentions[0]
        else:
            user1, user2 = mentions[0], mentions[1]

        # random % hợp nhau
        percent = random.randint(0, 100)

        # tạo progress bar bằng emoji
        filled = percent // 10
        empty = 10 - filled
        bar = "🟥" * filled + "⬜" * empty

        # text theo mức độ
        if percent < 20:
            status = "Toang rồi 💀"
        elif percent < 40:
            status = "Khó nha 😭"
        elif percent < 60:
            status = "Tạm ổn 😐"
        elif percent < 80:
            status = "Khá hợp đó 😳"
        else:
            status = "Chân ái luôn 💍"

        msg = (
            f"💞 **Ship cặp đôi** 💞\n"
            f"{user1.mention} ❤️ {user2.mention}\n\n"
            f"Độ hợp nhau: **{percent}%**\n"
            f"{bar}\n"
            f"{status}"
        )

        await ctx.send(msg)

    @commands.command(name="marry")
    async def marry(self, ctx):
        if not ctx.message.mentions:
            return await ctx.reply("Bạn phải tag người muốn cầu hôn 💍")

        target = ctx.message.mentions[0]

        # check người cầu hôn đã có vợ/chồng chưa
        check_self = self.supabase.table("marriages") \
            .select("*") \
            .or_(f"user1.eq.{ctx.author.id},user2.eq.{ctx.author.id}") \
            .execute()

        if check_self.data:
            return await ctx.reply("Bạn đã có vợ/chồng rồi 💀")

        # check người bị cầu hôn
        check_target = self.supabase.table("marriages") \
            .select("*") \
            .or_(f"user1.eq.{target.id},user2.eq.{target.id}") \
            .execute()

        if check_target.data:
            return await ctx.reply("Người này đã có chủ rồi 😭")


        if target == ctx.author:
            return await ctx.reply("Bạn không thể tự cưới mình 😐")

        if target.bot:
            return await ctx.reply("Bạn định cưới bot à? 🤨")

        async def save_to_db(user1_id, user2_id):
            # kiểm tra đã cưới chưa
            check = self.supabase.table("marriages") \
                .select("*") \
                .or_(f"user1.eq.{user1_id},user2.eq.{user1_id},user1.eq.{user2_id},user2.eq.{user2_id}") \
                .execute()

            if check.data:
                return  # đã có người kết hôn rồi → không lưu nữa

            # lưu cặp đôi
            self.supabase.table("marriages").insert({
                "user1": user1_id,
                "user2": user2_id
            }).execute()

        view = MarryView(ctx.author, target, save_to_db)

        msg = (
            f"💍 {target.mention}, bạn có đồng ý cưới {ctx.author.mention} không?\n"
            f"Bạn có 60 giây để trả lời!"
        )

        sent = await ctx.send(msg, view=view)

        await view.wait()

        if view.value is None:
            await sent.edit(
                content="⏰ Lời cầu hôn đã hết hạn...",
                view=None
            )

    @commands.command(name="couplelist")
    async def couplelist(self, ctx):
        # lấy toàn bộ dữ liệu marriages
        res = self.supabase.table("marriages").select("*").execute()
        data = res.data

        if not data:
            return await ctx.reply("Server chưa có cặp đôi nào 💔")

        lines = []
        guild = ctx.guild

        for row in data:
            user1_id = int(row["user1"])
            user2_id = int(row["user2"])

            member1 = guild.get_member(user1_id)
            member2 = guild.get_member(user2_id)

            # nếu 1 trong 2 người đã rời server
            name1 = member1.display_name if member1 else f"User {user1_id}"
            name2 = member2.display_name if member2 else f"User {user2_id}"

            lines.append(f"💍 {name1} ❤️ {name2}")

        embed = discord.Embed(
            title="💞 Danh sách cặp đôi trong server",
            description="\n".join(lines),
            color=discord.Color.pink()
        )

        embed.set_footer(text=f"Tổng cộng: {len(lines)} cặp")

        await ctx.send(embed=embed)

    @commands.command(name="partner")
    async def partner(self, ctx):
        res = self.supabase.table("marriages") \
            .select("*") \
            .or_(f"user1.eq.{ctx.author.id},user2.eq.{ctx.author.id}") \
            .execute()

        data = res.data

        if not data:
            return await ctx.reply("Bạn chưa kết hôn với ai 💔")

        row = data[0]
        partner_id = row["user2"] if row["user1"] == ctx.author.id else row["user1"]

        member = ctx.guild.get_member(int(partner_id))
        name = member.display_name if member else f"User {partner_id}"

        await ctx.send(f"💍 Bạn đang kết hôn với **{name}**")

    @commands.command(name="divorce")
    async def divorce(self, ctx):
        # tìm xem người dùng có kết hôn chưa
        res = self.supabase.table("marriages") \
            .select("*") \
            .or_(f"user1.eq.{ctx.author.id},user2.eq.{ctx.author.id}") \
            .execute()

        data = res.data

        if not data:
            return await ctx.reply("Bạn có cưới ai đâu mà đòi ly hôn 😐")

        row = data[0]
        partner_id = row["user2"] if row["user1"] == ctx.author.id else row["user1"]

        # xoá khỏi DB
        self.supabase.table("marriages") \
            .delete() \
            .or_(f"user1.eq.{ctx.author.id},user2.eq.{ctx.author.id}") \
            .execute()

        member = ctx.guild.get_member(int(partner_id))
        name = member.display_name if member else f"User {partner_id}"

        await ctx.send(f"💔 {ctx.author.mention} đã ly hôn với **{name}**")

async def setup(bot):
    await bot.add_cog(FunActions(bot))
