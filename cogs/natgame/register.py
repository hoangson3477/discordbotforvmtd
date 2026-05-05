import discord
from discord.ext import commands
from cogs.natgame.__db import supabase

class NatGameRegister(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="gameregister")
    async def game_register(self, ctx, *, nation_name: str):
        user_id = ctx.author.id

        # 1. Kiểm tra user đã có quốc gia chưa
        existing = supabase.table("nations") \
            .select("id") \
            .eq("owner_id", user_id) \
            .execute()

        if existing.data:
            await ctx.send("Bạn đã có quốc gia rồi, không thể tạo thêm.")
            return

        # 2. Tạo quốc gia mới
        data = {
            "owner_id": user_id,
            "name": nation_name,
            "money": 1000,
            "population": 100
            # 'army' sẽ lấy default = 10 từ schema
        }

        result = supabase.table("nations").insert(data).execute()

        if result.data:
            await ctx.send(
                f"Đã thành lập quốc gia **{nation_name}**!\n"
                f"Tiền: 1000\n"
                f"Dân số: 100\n"
                f"Quân đội: 10"
            )
        else:
            await ctx.send("Có lỗi xảy ra khi tạo quốc gia.")

async def setup(bot):
    await bot.add_cog(NatGameRegister(bot))
