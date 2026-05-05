import discord
from discord.ext import commands
from cogs.natgame.__db import supabase

class SetWarArmy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setwararmy")
    async def set_war_army(self, ctx, *, raw: str):
        user_id = str(ctx.author.id)

        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 2:
            return await ctx.reply("❌ Cú pháp sai.")

        war_name = parts[0]
        entries = parts[1:]

        # 1️⃣ Nation
        nation = (
            supabase.table("nations")
            .select("*")
            .eq("owner_id", user_id)
            .single()
            .execute()
        ).data

        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        nation_id = nation["id"]

        # 2️⃣ Tạo war army
        war_army = (
            supabase.table("war_armies")
            .insert({
                "nation_id": nation_id,
                "name": war_name
            })
            .execute()
        ).data[0]

        war_army_id = war_army["id"]

        total_loose = 0
        added_units = []

        # 3️⃣ Xử lý entries
        for e in entries:
            if e.startswith("+"):
                total_loose += int(e[1:])
                continue

            unit = (
                supabase.table("military_units")
                .select("*")
                .eq("nation_id", nation_id)
                .eq("name", e)
                .eq("status", "idle")
                .single()
                .execute()
            ).data

            if not unit:
                continue

            # Gán unit
            supabase.table("military_units").update({
                "status": "war",
                "war_army_id": war_army_id
            }).eq("id", unit["id"]).execute()

            supabase.table("war_army_units").insert({
                "war_army_id": war_army_id,
                "unit_id": unit["id"]
            }).execute()

            added_units.append(e)

        # 4️⃣ Trừ quân lẻ
        if total_loose > 0:
            if nation["army"] < total_loose:
                return await ctx.reply("❌ Không đủ quân lẻ.")

            supabase.table("nations").update({
                "army": nation["army"] - total_loose
            }).eq("id", nation_id).execute()

            supabase.table("war_army_units").insert({
                "war_army_id": war_army_id,
                "loose_troops": total_loose
            }).execute()

        await ctx.reply(
            f"**Đã lập tập đoàn quân `{war_name}`**\n"
            f"• Units: {', '.join(added_units) if added_units else 'Không'}\n"
            f"• Quân lẻ: {total_loose}"
        )

    @commands.command(name="listwarmy")
    async def list_war_army(self, ctx):
        """Liệt kê các tập đoàn quân"""
        user_id = str(ctx.author.id)

        nation = supabase.table("nations") \
            .select("id, name") \
            .eq("owner_id", user_id) \
            .single().execute().data

        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        war_armies = supabase.table("war_armies") \
            .select("id, name, status") \
            .eq("nation_id", nation["id"]) \
            .execute().data

        if not war_armies:
            return await ctx.reply("⚔️ Chưa có tập đoàn quân nào. Dùng `!setwararmy` để tạo.")

        embed = discord.Embed(
            title=f"⚔️ Tập đoàn quân - {nation['name']}",
            color=discord.Color.dark_red()
        )

        for wa in war_armies:
            # Lấy units trong war army
            units = supabase.table("war_army_units") \
                .select("unit_id, loose_troops, military_units(name, size)") \
                .eq("war_army_id", wa["id"]) \
                .execute().data

            total_troops = 0
            unit_names = []

            for u in units:
                if u.get("military_units"):
                    total_troops += u["military_units"].get("size", 0)
                    unit_names.append(u["military_units"]["name"])
                elif u.get("loose_troops"):
                    total_troops += u["loose_troops"]

            status_icon = "🟢" if wa["status"] == "preparing" else "⚔️"
            embed.add_field(
                name=f"{status_icon} {wa['name']}",
                value=f"{len(units)} đơn vị | {total_troops:,} quân",
                inline=True
            )

        await ctx.reply(embed=embed)

    @commands.command(name="deletewarmy")
    async def delete_war_army(self, ctx, *, war_name: str):
        """Xóa tập đoàn quân và trả units về idle"""
        user_id = str(ctx.author.id)

        nation = supabase.table("nations") \
            .select("id") \
            .eq("owner_id", user_id) \
            .single().execute().data

        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        # Tìm war army
        war_army = supabase.table("war_armies") \
            .select("id, name") \
            .eq("nation_id", nation["id"]) \
            .eq("name", war_name.strip()) \
            .single().execute().data

        if not war_army:
            return await ctx.reply(f"❌ Không tìm thấy tập đoàn quân **{war_name}**.")

        war_army_id = war_army["id"]

        # Lấy tất cả units để trả về idle
        units = supabase.table("war_army_units") \
            .select("unit_id, loose_troops") \
            .eq("war_army_id", war_army_id) \
            .execute().data

        # Trả units về idle
        total_returned = 0
        for u in units:
            if u.get("unit_id"):
                supabase.table("military_units") \
                    .update({"status": "idle", "war_army_id": None}) \
                    .eq("id", u["unit_id"]) \
                    .execute()
            if u.get("loose_troops"):
                total_returned += u["loose_troops"]

        # Trả quân lẻ về kho nếu có
        if total_returned > 0:
            current_army = supabase.table("nations") \
                .select("army") \
                .eq("id", nation["id"]) \
                .single().execute().data["army"]

            supabase.table("nations") \
                .update({"army": current_army + total_returned}) \
                .eq("id", nation["id"]) \
                .execute()

        # Xóa war_army_units
        supabase.table("war_army_units") \
            .delete() \
            .eq("war_army_id", war_army_id) \
            .execute()

        # Xóa war_army
        supabase.table("war_armies") \
            .delete() \
            .eq("id", war_army_id) \
            .execute()

        await ctx.reply(
            f"✅ Đã giải tán tập đoàn quân **{war_name}**\n"
            f"• {len([u for u in units if u.get('unit_id')])} đơn vị đã trở về\n"
            f"• {total_returned:,} quân lẻ đã trở về kho"
        )


async def setup(bot):
    await bot.add_cog(SetWarArmy(bot))
