import discord
from discord.ext import commands
from cogs.natgame.__db import supabase
from cogs.natgame.__utils_level import ensure_nation_level, add_nation_exp


class NationLevel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="level", aliases=["lvl"])
    async def show_level(self, ctx):
        """Hiển thị level và exp của quốc gia"""
        user_id = str(ctx.author.id)

        # Lấy nation
        nation_res = supabase.table("nations") \
            .select("id, name") \
            .eq("owner_id", user_id) \
            .single().execute()

        if not nation_res.data:
            return await ctx.reply("❌ Bạn chưa có quốc gia. Dùng `!gameregister` trước.")

        nation_id = nation_res.data["id"]
        nation_name = nation_res.data["name"]

        # Đảm bảo có level record
        level_data = ensure_nation_level(supabase, nation_id)

        level = level_data["level"]
        exp = level_data["exp"]
        exp_needed = level * 100
        progress_pct = (exp / exp_needed) * 100

        # Tạo progress bar
        filled = int(progress_pct / 10)
        empty = 10 - filled
        progress_bar = "█" * filled + "░" * empty

        embed = discord.Embed(
            title=f"📊 Level Quốc Gia - {nation_name}",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Level",
            value=f"**{level}** ⭐",
            inline=True
        )

        embed.add_field(
            name="EXP",
            value=f"**{exp}** / {exp_needed}",
            inline=True
        )

        embed.add_field(
            name="Progress",
            value=f"`{progress_bar}` {progress_pct:.1f}%",
            inline=False
        )

        # Benefits theo level
        benefits = []
        if level >= 3:
            benefits.append("✅ Hải quân đã mở khóa")
        if level >= 5:
            benefits.append("✅ Không quân đã mở khóa")
        if level >= 10:
            benefits.append("✅ Slot phòng tuyến +1")

        if benefits:
            embed.add_field(
                name="Phúc lợi",
                value="\n".join(benefits),
                inline=False
            )

        # Next unlocks
        next_unlocks = []
        if level < 3:
            next_unlocks.append(f"Level 3: Mở khóa Hải quân")
        if level < 5:
            next_unlocks.append(f"Level 5: Mở khóa Không quân")

        if next_unlocks:
            embed.add_field(
                name="Sắp mở khóa",
                value="\n".join(next_unlocks),
                inline=False
            )

        await ctx.reply(embed=embed)

    @commands.command(name="addexp", aliases=["xp"])
    @commands.is_owner()  # Chỉ owner mới dùng được (debug)
    async def add_exp_command(self, ctx, amount: int):
        """Thêm exp cho quốc gia (debug command)"""
        user_id = str(ctx.author.id)

        nation_res = supabase.table("nations") \
            .select("id") \
            .eq("owner_id", user_id) \
            .single().execute()

        if not nation_res.data:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        nation_id = nation_res.data["id"]
        leveled_up, new_level = add_nation_exp(supabase, nation_id, amount)

        if leveled_up:
            await ctx.reply(f"🎉 **LEVEL UP!** Bạn đã đạt level **{new_level}**!")
        else:
            await ctx.reply(f"✅ Đã thêm **{amount}** EXP!")


async def setup(bot):
    await bot.add_cog(NationLevel(bot))
