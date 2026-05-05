"""
NATGAME Shop System
"""
import discord
from discord.ext import commands
from cogs.natgame.__db import supabase
from datetime import datetime, timedelta, timezone

# Shop items definition
SHOP_ITEMS = {
    "infrastructure": {
        "name": "🏗️ Infrastructure",
        "price": 5000,
        "description": "Tăng 20% tốc độ tăng dân số",
        "effect": "pop_growth",
        "value": 0.20,
        "duration": None  # Permanent
    },
    "academy": {
        "name": "🎓 Academy",
        "price": 3000,
        "description": "Tăng 50% EXP gain từ mọi nguồn",
        "effect": "exp_boost",
        "value": 0.50,
        "duration": None
    },
    "fortification": {
        "name": "🏰 Fortification",
        "price": 4000,
        "description": "Tăng 30% sức mạnh phòng thủ",
        "effect": "defense_boost",
        "value": 0.30,
        "duration": None
    },
    "instant_recruit": {
        "name": "⚡ Instant Recruit",
        "price": 1000,
        "description": "Bỏ qua cooldown recruit, tuyển ngay lập tức",
        "effect": "reset_recruit",
        "value": None,
        "duration": None
    },
    "population_boost": {
        "name": "👥 Migration Boost",
        "price": 2000,
        "description": "+100 dân số ngay lập tức",
        "effect": "add_population",
        "value": 100,
        "duration": None
    }
}


class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="shop")
    async def show_shop(self, ctx):
        """Hiển thị danh sách items trong shop"""
        embed = discord.Embed(
            title="🛒 NATGAME Shop",
            description="Dùng `!buy <item> [số_lượng]` để mua",
            color=discord.Color.purple()
        )

        for item_id, item in SHOP_ITEMS.items():
            embed.add_field(
                name=f"{item['name']} - {item['price']:,} 💰",
                value=f"{item['description']}\n`!buy {item_id}`",
                inline=False
            )

        # Hiển thị tiền hiện tại
        user_id = str(ctx.author.id)
        nation = supabase.table("nations").select("money").eq("owner_id", user_id).single().execute().data

        if nation:
            embed.set_footer(text=f"💰 Tiền của bạn: {nation['money']:,}")
        else:
            embed.set_footer(text="❌ Bạn chưa có quốc gia")

        await ctx.reply(embed=embed)

    @commands.command(name="buy")
    async def buy_item(self, ctx, item_id: str, quantity: int = 1):
        """
        Mua item từ shop
        !buy <item_id> [số_lượng]
        VD: !buy infrastructure
        VD: !buy instant_recruit 3
        """
        user_id = str(ctx.author.id)

        # Kiểm tra nation
        nation = supabase.table("nations").select("id, money, population").eq("owner_id", user_id).single().execute().data
        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        # Kiểm tra item hợp lệ
        item_id = item_id.lower()
        if item_id not in SHOP_ITEMS:
            valid_items = ", ".join([f"`{k}`" for k in SHOP_ITEMS.keys()])
            return await ctx.reply(f"❌ Item không hợp lệ.\nCác item hợp lệ: {valid_items}")

        item = SHOP_ITEMS[item_id]
        total_cost = item["price"] * quantity

        # Kiểm tra tiền
        if nation["money"] < total_cost:
            return await ctx.reply(
                f"❌ Không đủ tiền.\n"
                f"Cần: {total_cost:,} 💰\n"
                f"Có: {nation['money']:,} 💰"
            )

        nation_id = nation["id"]
        new_money = nation["money"] - total_cost

        # Áp dụng effect
        effect_text = ""

        if item["effect"] == "reset_recruit":
            # Reset recruit cooldown
            supabase.table("nations").update({
                "last_recruit_at": None,
                "money": new_money
            }).eq("id", nation_id).execute()
            effect_text = "✅ Cooldown recruit đã được reset! Bạn có thể tuyển quân ngay bây giờ."

        elif item["effect"] == "add_population":
            # Thêm dân số
            new_pop = nation["population"] + (item["value"] * quantity)
            supabase.table("nations").update({
                "population": new_pop,
                "money": new_money
            }).eq("id", nation_id).execute()
            effect_text = f"✅ Dân số tăng thêm {item['value'] * quantity:,}! Tổng hiện tại: {new_pop:,}"

        else:
            # Các item permanent effect - lưu vào nation_upgrades table
            # Kiểm tra đã có chưa
            existing = supabase.table("nation_upgrades").select("id, quantity").eq("nation_id", nation_id).eq("upgrade_type", item["effect"]).execute().data

            if existing:
                # Update quantity
                new_qty = existing[0]["quantity"] + quantity
                supabase.table("nation_upgrades").update({
                    "quantity": new_qty
                }).eq("id", existing[0]["id"]).execute()
            else:
                # Insert mới
                supabase.table("nation_upgrades").insert({
                    "nation_id": nation_id,
                    "upgrade_type": item["effect"],
                    "quantity": quantity
                }).execute()

            # Trừ tiền
            supabase.table("nations").update({"money": new_money}).eq("id", nation_id).execute()

            effect_name = {
                "pop_growth": "tốc độ tăng dân",
                "exp_boost": "EXP gain",
                "defense_boost": "sức mạnh phòng thủ"
            }.get(item["effect"], item["effect"])

            effect_text = f"✅ Đã nhận {quantity}x **{effect_name}** boost!"

        embed = discord.Embed(
            title="🛒 Mua hàng thành công!",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Item",
            value=item["name"],
            inline=True
        )

        embed.add_field(
            name="Số lượng",
            value=str(quantity),
            inline=True
        )

        embed.add_field(
            name="Tổng chi phí",
            value=f"{total_cost:,} 💰",
            inline=True
        )

        embed.add_field(
            name="Hiệu ứng",
            value=effect_text,
            inline=False
        )

        embed.add_field(
            name="Tiền còn lại",
            value=f"{new_money:,} 💰",
            inline=False
        )

        await ctx.reply(embed=embed)

    @commands.command(name="upgrades")
    async def show_upgrades(self, ctx):
        """Hiển thị các upgrades đã mua"""
        user_id = str(ctx.author.id)

        nation = supabase.table("nations").select("id, name").eq("owner_id", user_id).single().execute().data
        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        upgrades = supabase.table("nation_upgrades").select("upgrade_type, quantity").eq("nation_id", nation["id"]).execute().data

        if not upgrades:
            return await ctx.reply("🛒 Bạn chưa có upgrade nào. Dùng `!shop` để mua.")

        embed = discord.Embed(
            title=f"🛒 Upgrades - {nation['name']}",
            color=discord.Color.purple()
        )

        effect_names = {
            "pop_growth": "🏗️ Tăng trưởng dân số",
            "exp_boost": "🎓 EXP Boost",
            "defense_boost": "🏰 Phòng thủ"
        }

        for u in upgrades:
            name = effect_names.get(u["upgrade_type"], u["upgrade_type"])
            embed.add_field(
                name=name,
                value=f"Cấp độ: **{u['quantity']}**",
                inline=True
            )

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Shop(bot))
