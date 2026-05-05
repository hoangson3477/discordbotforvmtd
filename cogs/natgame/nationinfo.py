import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone

from cogs.natgame.__db import supabase  # nhớ đúng path cogs

class NationInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="nationinfo", aliases=["nation"])
    async def nationinfo(self, ctx):
        user_id = str(ctx.author.id)

        res = (
            supabase
            .table("nations")
            .select(
                "name, population, money, army, navy, airforce, last_recruit_at"
            )
            .eq("owner_id", user_id)
            .single()
            .execute()
        )

        if not res.data:
            await ctx.reply("❌ Bạn chưa có quốc gia. Dùng `!gameregister` trước.")
            return

        n = res.data

        # ---- cooldown recruit ----
        cooldown_text = "Sẵn sàng"
        if n["last_recruit_at"]:
            last = datetime.fromisoformat(
                n["last_recruit_at"].replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            remain = last + timedelta(hours=1) - now
            if remain.total_seconds() > 0:
                m, s = divmod(int(remain.total_seconds()), 60)
                h, m = divmod(m, 60)
                cooldown_text = f"{h}h {m}m {s}s"

        embed = discord.Embed(
            title=f"Quốc gia: {n['name']}",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="Thông tin cơ bản",
            value=(
                f"Dân số: **{n['population']:,}**\n"
                f"Ngân khố: **{n['money']:,}**"
            ),
            inline=False
        )

        embed.add_field(
            name="Quân đội",
            value=(
                f"Lục quân: **{n['army']:,}**\n"
                f"Hải quân: **{n['navy']:,}**\n"
                f"Không quân: **{n['airforce']:,}**"
            ),
            inline=False
        )

        embed.add_field(
            name="Thời gian chờ gọi nhập ngũ (!recruit)",
            value=f"Cooldown: **{cooldown_text}**",
            inline=False
        )

        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(NationInfo(bot))