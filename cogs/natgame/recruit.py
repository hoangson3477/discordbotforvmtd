import discord
from discord.ext import commands
from postgrest.exceptions import APIError

from cogs.natgame.__db import supabase


class Recruit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="recruit")
    async def recruit(self, ctx):
        user_id = str(ctx.author.id)

        try:
            res = (
                supabase
                .rpc("nation_recruit", {"p_user": user_id})
                .execute()
            )
        except APIError as e:
            msg = str(e)

            if "cooldown" in msg:
                # Lấy thời gian cooldown còn lại
                user_id = str(ctx.author.id)
                nation = supabase.table("nations") \
                    .select("last_recruit_at") \
                    .eq("owner_id", user_id) \
                    .single().execute().data

                if nation and nation.get("last_recruit_at"):
                    from datetime import datetime, timedelta, timezone
                    last_recruit = datetime.fromisoformat(nation["last_recruit_at"].replace("Z", "+00:00"))
                    next_recruit = last_recruit + timedelta(hours=1)
                    now = datetime.now(timezone.utc)

                    if now < next_recruit:
                        remain = next_recruit - now
                        hours, remainder = divmod(int(remain.total_seconds()), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        await ctx.reply(
                            f"⏳ **Đang trong thời gian chờ**\n"
                            f"Còn lại: **{hours}h {minutes}m {seconds}s**\n"
                            f"Tuyển tiếp lúc: <t:{int(next_recruit.timestamp())}:t>"
                        )
                    else:
                        await ctx.reply("⏳ Bạn đã tuyển quân rồi. Vui lòng đợi thêm.")
                else:
                    await ctx.reply("⏳ Bạn đã tuyển quân rồi. Vui lòng đợi thêm.")
            elif "nation not found" in msg:
                await ctx.reply("Bạn chưa có quốc gia. Dùng `!gameregister`.")
            elif "population too low" in msg:
                await ctx.reply("Dân số quá thấp để tuyển quân.")
            elif "money not enough" in msg:
                await ctx.reply("Không đủ tiền để tuyển quân.")
            else:
                await ctx.reply("Có lỗi xảy ra khi recruit.")
                raise
            return

        data = res.data[0]

        embed = discord.Embed(
            title="Tuyển quân thành công",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Kết quả",
            value=(
                f"Số lính mới: **{data['recruited']:,}** quân\n"
                f"Tiền tiêu: **{data['money_spent']:,}**"
            ),
            inline=False
        )

        embed.add_field(
            name="Quân đội",
            value=f"Quân lực (Lục quân) hiện tại: **{data['army_after']:,}**",
            inline=False
        )

        embed.add_field(
            name="Sau recruit",
            value=(
                f"Dân số: **{data['population_after']:,}**\n"
                f"Ngân khố: **{data['money_after']:,}**"
            ),
            inline=False
        )

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Recruit(bot))