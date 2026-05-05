"""
NATGAME Spy/Espionage System
"""
import discord
from discord.ext import commands
from cogs.natgame.__db import supabase
import random


class Spy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="spy")
    async def spy_nation(self, ctx):
        """
        Do thám quốc gia khác
        !spy @user
        Tốn 100 money mỗi lần do thám
        """
        if not ctx.message.mentions:
            return await ctx.reply("❌ Cú pháp: `!spy @user`")

        spy_user_id = str(ctx.author.id)
        target_user_id = str(ctx.message.mentions[0].id)

        if spy_user_id == target_user_id:
            return await ctx.reply("❌ Không thể do thám chính mình!")

        SPY_COST = 100

        # Kiểm tra nation của người do thám
        spy_nation = supabase.table("nations").select("id, money, name").eq("owner_id", spy_user_id).single().execute().data
        if not spy_nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        # Kiểm tra tiền
        if spy_nation["money"] < SPY_COST:
            return await ctx.reply(f"❌ Không đủ tiền. Cần {SPY_COST} 💰 để do thám.")

        # Kiểm tra target có nation không
        target_nation = supabase.table("nations").select("id, name, population, money, army, navy, airforce").eq("owner_id", target_user_id).single().execute().data

        if not target_nation:
            return await ctx.reply("❌ Người này chưa có quốc gia.")

        # Trừ tiền
        new_money = spy_nation["money"] - SPY_COST
        supabase.table("nations").update({"money": new_money}).eq("id", spy_nation["id"]).execute()

        # Lấy thêm thông tin
        # Số defense lines
        defenses = supabase.table("defense_lines").select("id", count="exact").eq("nation_id", target_nation["id"]).execute()
        defense_count = len(defenses.data)

        # Số war armies
        war_armies = supabase.table("war_armies").select("id", count="exact").eq("nation_id", target_nation["id"]).execute()
        war_army_count = len(war_armies.data)

        # Level
        level_data = supabase.table("nation_levels").select("level, exp").eq("nation_id", target_nation["id"]).single().execute().data
        level = level_data["level"] if level_data else 1

        # Tính toán sức mạnh tương đối
        total_troops = target_nation.get("army", 0) + target_nation.get("navy", 0) + target_nation.get("airforce", 0)

        if total_troops < 100:
            strength = "🟢 Yếu"
        elif total_troops < 500:
            strength = "🟡 Trung bình"
        elif total_troops < 1000:
            strength = "🟠 Mạnh"
        else:
            strength = "🔴 Rất mạnh"

        # Random spy quality (accuracy of info)
        spy_quality = random.randint(1, 100)

        embed = discord.Embed(
            title=f"🕵️ Báo cáo do thám - {target_nation['name']}",
            description=f"Chi phí: {SPY_COST} 💰 | Chất lượng tin: {spy_quality}%",
            color=discord.Color.dark_purple()
        )

        # Basic info (always accurate)
        embed.add_field(
            name="Thông tin cơ bản",
            value=(
                f"Level: **{level}**\n"
                f"Dân số: **~{target_nation['population']:,}**\n"
                f"Sức mạnh: {strength}"
            ),
            inline=False
        )

        # Military info (slightly inaccurate based on spy quality)
        if spy_quality > 30:
            army_estimate = int(target_nation.get("army", 0) * (0.9 + random.random() * 0.2))
            navy_estimate = int(target_nation.get("navy", 0) * (0.9 + random.random() * 0.2))
            airforce_estimate = int(target_nation.get("airforce", 0) * (0.9 + random.random() * 0.2))

            embed.add_field(
                name="Quân đội (ước tính)",
                value=(
                    f"Lục quân: **~{army_estimate:,}**\n"
                    f"Hải quân: **~{navy_estimate:,}**\n"
                    f"Không quân: **~{airforce_estimate:,}**"
                ),
                inline=True
            )
        else:
            embed.add_field(
                name="Quân đội",
                value="🔍 Không đủ thông tin",
                inline=True
            )

        # Defensive info
        if spy_quality > 50:
            embed.add_field(
                name="Phòng thủ",
                value=f"**{defense_count}** phòng tuyến đang hoạt động",
                inline=True
            )
        else:
            embed.add_field(
                name="Phòng thủ",
                value="🔍 Không rõ",
                inline=True
            )

        # War readiness
        if spy_quality > 70:
            embed.add_field(
                name="Sẵn sàng chiến đấu",
                value=f"**{war_army_count}** tập đoàn quân đang chờ",
                inline=True
            )
        else:
            embed.add_field(
                name="Sẵn sàng chiến đấu",
                value="🔍 Không đủ dữ liệu",
                inline=True
            )

        # Spy advice
        spy_advice = ""
        if total_troops < (spy_nation.get("army", 0) * 0.5):
            spy_advice = "🎯 **Khuyến nghị**: Đối phương yếu hơn bạn nhiều. Có thể tấn công!"
        elif total_troops > (spy_nation.get("army", 0) * 1.5):
            spy_advice = "⚠️ **Cảnh báo**: Đối phương mạnh hơn bạn đáng kể. Cân nhắc phòng thủ!"
        else:
            spy_advice = "📊 **Phân tích**: Sức mạnh tương đương. Cần chiến thuật tốt để thắng."

        embed.add_field(
            name="Đánh giá",
            value=spy_advice,
            inline=False
        )

        embed.set_footer(text=f"💰 Tiền còn lại: {new_money:,}")

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Spy(bot))
