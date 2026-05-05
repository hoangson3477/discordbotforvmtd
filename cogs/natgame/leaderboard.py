"""
NATGAME Leaderboard System
"""
import discord
from discord.ext import commands
from cogs.natgame.__db import supabase


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="nationtop", aliases=["top", "ngtop"])
    async def nation_top(self, ctx):
        """BXH Top 10 quốc gia theo Level"""
        # Lấy top nations join với nation_levels
        top = supabase.table("nations") \
            .select("name, owner_id, money, nation_levels(level, exp)") \
            .order("nation_levels.level", desc=True) \
            .limit(10) \
            .execute().data

        if not top:
            return await ctx.reply("❌ Chưa có quốc gia nào.")

        embed = discord.Embed(
            title="🏆 BXH Quốc Gia - Top Level",
            color=discord.Color.gold()
        )

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        lines = []
        for i, n in enumerate(top):
            level_data = n.get("nation_levels", {})
            level = level_data.get("level", 1) if level_data else 1
            exp = level_data.get("exp", 0) if level_data else 0
            medal = medals[i] if i < 10 else f"{i+1}."
            lines.append(
                f"{medal} **{n['name']}** | Level {level} ({exp} EXP)"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text="Dùng !richlist để xem BXH theo tiền | !wartop theo war thắng")

        await ctx.reply(embed=embed)

    @commands.command(name="richlist", aliases=["rich", "ngmoney"])
    async def rich_list(self, ctx):
        """BXH Top 10 quốc gia giàu nhất"""
        top = supabase.table("nations") \
            .select("name, money, population, army") \
            .order("money", desc=True) \
            .limit(10) \
            .execute().data

        if not top:
            return await ctx.reply("❌ Chưa có quốc gia nào.")

        embed = discord.Embed(
            title="💰 BXH Quốc Gia Giàu Nhất",
            color=discord.Color.green()
        )

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        lines = []
        for i, n in enumerate(top):
            medal = medals[i] if i < 10 else f"{i+1}."
            lines.append(
                f"{medal} **{n['name']}** | {n['money']:,} 💰"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text="Tổng giá trị: Quân đội + Dân số + Tiền mặt")

        await ctx.reply(embed=embed)

    @commands.command(name="wartop", aliases=["wartop"])
    async def war_top(self, ctx):
        """BXH Top 10 theo số war thắng"""
        # Đếm số war thắng của mỗi nation
        # wars table có winner_nation_id
        wars = supabase.table("wars") \
            .select("winner_nation_id, nations!wars_winner_nation_id_fkey(name)") \
            .not_.is_("winner_nation_id", "null") \
            .execute().data

        if not wars:
            return await ctx.reply("❌ Chưa có war nào kết thúc.")

        # Count wins per nation
        win_counts = {}
        for w in wars:
            nation_id = w.get("winner_nation_id")
            nation_name = w.get("nations", {}).get("name", "Unknown")
            if nation_id:
                if nation_id not in win_counts:
                    win_counts[nation_id] = {"name": nation_name, "wins": 0}
                win_counts[nation_id]["wins"] += 1

        # Sort by wins
        sorted_wins = sorted(
            win_counts.items(),
            key=lambda x: x[1]["wins"],
            reverse=True
        )[:10]

        embed = discord.Embed(
            title="⚔️ BXH Chiến Thắng",
            color=discord.Color.dark_red()
        )

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        lines = []
        for i, (nation_id, data) in enumerate(sorted_wins):
            medal = medals[i] if i < 10 else f"{i+1}."
            lines.append(
                f"{medal} **{data['name']}** | {data['wins']} chiến thắng 🏆"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text="Tính cả PvP và PVE")

        await ctx.reply(embed=embed)

    @commands.command(name="gamestats", aliases=["ngstats"])
    async def game_stats(self, ctx):
        """Thống kê tổng quan game"""
        # Tổng số quốc gia
        nations_count = len(supabase.table("nations").select("id", count="exact").execute().data)

        # Tổng quân số
        total_army = supabase.table("nations").select("army").execute().data
        total_soldiers = sum(n.get("army", 0) for n in total_army)

        # Tổng số war đang diễn ra
        active_wars = len(supabase.table("wars").select("id").eq("status", "active").execute().data)

        # Quốc gia lớn nhất (theo tổng quân)
        biggest = supabase.table("nations") \
            .select("name, army, navy, airforce") \
            .order("army", desc=True) \
            .limit(1).execute().data

        embed = discord.Embed(
            title="📊 Thống Kê NATGAME",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Tổng quan",
            value=(
                f"🌍 Quốc gia: **{nations_count}**\n"
                f"⚔️ War đang diễn ra: **{active_wars}**\n"
                f"💂 Tổng quân số: **{total_soldiers:,}**"
            ),
            inline=False
        )

        if biggest:
            b = biggest[0]
            total = b.get("army", 0) + b.get("navy", 0) + b.get("airforce", 0)
            embed.add_field(
                name="Quốc gia mạnh nhất",
                value=f"**{b['name']}** với {total:,} quân",
                inline=False
            )

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
