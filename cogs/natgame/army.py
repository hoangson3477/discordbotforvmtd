import discord
from discord.ext import commands

from cogs.natgame.__db import supabase


class Army(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="army")
    async def army(self, ctx):
        user_id = str(ctx.author.id)

        res = (
            supabase
            .table("nations")
            .select("name, army, navy, airforce")
            .eq("owner_id", user_id)
            .single()
            .execute()
        )

        if not res.data:
            await ctx.reply("❌ Bạn chưa có quốc gia. Dùng `!gameregister` trước.")
            return

        n = res.data

        total = n["army"] + n["navy"] + n["airforce"]

        embed = discord.Embed(
            title=f"Quân đội quốc gia: {n['name']}",
            color=discord.Color.dark_red()
        )

        embed.add_field(
            name="Tổng quân số",
            value=f"**{total:,}**",
            inline=False
        )

        embed.add_field(
            name="Lục quân",
            value=f"**{n['army']:,}**",
            inline=True
        )

        embed.add_field(
            name="Hải quân",
            value=f"**{n['navy']:,}**",
            inline=True
        )

        embed.add_field(
            name="Không quân",
            value=f"**{n['airforce']:,}**",
            inline=True
        )

        embed.set_footer(
            text="Đây là quân dự bị (chưa gán vào unit) | !totalarmy để xem tổng quân thực"
        )

        await ctx.reply(embed=embed)

    @commands.command(name="totalarmy", aliases=["ta"])
    async def total_army(self, ctx):
        """Xem tổng quân thực tế (cả dự bị + trong units)"""
        user_id = str(ctx.author.id)

        # Lấy nation
        nation = supabase.table("nations") \
            .select("id, name, army, navy, airforce") \
            .eq("owner_id", user_id) \
            .single().execute().data

        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        nation_id = nation["id"]

        # Lấy tất cả units
        units = supabase.table("military_units") \
            .select("size, branch") \
            .eq("nation_id", nation_id) \
            .execute().data

        # Tính quân trong units
        troops_in_units = sum(u["size"] for u in units)

        # Tổng quân lục thực tế
        total_land_army = nation["army"] + troops_in_units
        total_troops = total_land_army + nation["navy"] + nation["airforce"]

        embed = discord.Embed(
            title=f"📊 Tổng quân lực - {nation['name']}",
            color=discord.Color.dark_red()
        )

        embed.add_field(
            name="Tổng quân số",
            value=f"**{total_troops:,}**",
            inline=False
        )

        embed.add_field(
            name="Lục quân (tổng)",
            value=f"**{total_land_army:,}**\n({troops_in_units:,} trong units + {nation['army']:,} dự bị)",
            inline=False
        )

        embed.add_field(
            name="Hải quân",
            value=f"**{nation['navy']:,}**",
            inline=True
        )

        embed.add_field(
            name="Không quân",
            value=f"**{nation['airforce']:,}**",
            inline=True
        )

        embed.add_field(
            name="Số đơn vị",
            value=f"**{len(units)}** units",
            inline=True
        )

        embed.set_footer(text="Quân trong units đã sẵn sàng chiến đấu!")

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Army(bot))
