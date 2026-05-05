import discord
from discord.ext import commands
from cogs.natgame.__db import supabase
from cogs.natgame.formunit import get_tier_display
import math

class FormDefense(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="formdefense")
    async def form_defense(self, ctx, *, units_raw: str):
        user_id = str(ctx.author.id)

        # 1️⃣ Lấy nation
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
        level = nation.get("level", 1)

        # 2️⃣ Tính slot
        max_slots = 3 + math.floor((level - 1) / 5)

        # 3️⃣ Slot đang dùng
        used_slots = (
            supabase.table("defense_lines")
            .select("slot")
            .eq("nation_id", nation_id)
            .execute()
        ).data

        used_slots = {d["slot"] for d in used_slots}
        free_slots = [i for i in range(1, max_slots + 1) if i not in used_slots]

        if not free_slots:
            return await ctx.reply("❌ Bạn đã dùng hết slot phòng tuyến.")

        unit_names = [u.strip() for u in units_raw.split(",")]

        if len(unit_names) > len(free_slots):
            return await ctx.reply(
                f"❌ Chỉ còn {len(free_slots)} slot phòng tuyến trống."
            )

        success = []

        for unit_name in unit_names:
            if not free_slots:
                break

            # 4️⃣ Lấy unit
            unit = (
                supabase.table("military_units")
                .select("*")
                .eq("nation_id", nation_id)
                .eq("name", unit_name)
                .eq("status", "idle")
                .single()
                .execute()
            ).data

            if not unit:
                continue

            slot = free_slots.pop(0)

            # 5️⃣ Insert defense line
            supabase.table("defense_lines").insert({
                "nation_id": nation_id,
                "slot": slot,
                "unit_id": unit["id"]
            }).execute()

            # 6️⃣ Update unit
            supabase.table("military_units").update({
                "status": "defense"
            }).eq("id", unit["id"]).execute()

            success.append(f"{unit_name} → Slot {slot}")

        if not success:
            return await ctx.reply("❌ Không unit nào hợp lệ để lập phòng tuyến.")

        await ctx.reply(
            "**Đã lập phòng tuyến:**\n" + "\n".join(success)
        )

    @commands.command(name="defensestatus")
    async def defense_status(self, ctx):
        """Xem trạng thái phòng tuyến hiện tại"""
        user_id = str(ctx.author.id)

        nation = supabase.table("nations") \
            .select("id, name") \
            .eq("owner_id", user_id) \
            .single().execute().data

        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        # Lấy defense lines với thông tin unit
        defenses = supabase.table("defense_lines") \
            .select("slot, unit_id, military_units(name, tier, size)") \
            .eq("nation_id", nation["id"]) \
            .order("slot") \
            .execute().data

        if not defenses:
            return await ctx.reply("🛡️ Chưa có phòng tuyến nào. Dùng `!formdefense` để lập.")

        embed = discord.Embed(
            title=f"🛡️ Phòng tuyến - {nation['name']}",
            color=discord.Color.dark_red()
        )

        lines_text = []
        for d in defenses:
            unit = d.get("military_units", {})
            if unit:
                tier = get_tier_display(unit.get("tier", ""))
                lines_text.append(
                    f"**Slot {d['slot']}**: {unit.get('name')} "
                    f"({tier}, {unit.get('size', 0):,} quân)"
                )
            else:
                lines_text.append(f"**Slot {d['slot']}**: [Trống]")

        embed.description = "\n".join(lines_text)

        # Tính max slots
        level = 1  # TODO: Get from nation_levels
        max_slots = 3 + (level - 1) // 5
        embed.set_footer(text=f"Slots: {len(defenses)}/{max_slots}")

        await ctx.reply(embed=embed)

    @commands.command(name="cleardefense")
    async def clear_defense(self, ctx, slot: int = None):
        """
        Xóa phòng tuyến
        !cleardefense - Xóa tất cả
        !cleardefense <slot> - Xóa slot cụ thể
        """
        user_id = str(ctx.author.id)

        nation = supabase.table("nations") \
            .select("id") \
            .eq("owner_id", user_id) \
            .single().execute().data

        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        nation_id = nation["id"]

        if slot:
            # Xóa slot cụ thể
            defense = supabase.table("defense_lines") \
                .select("unit_id") \
                .eq("nation_id", nation_id) \
                .eq("slot", slot) \
                .single().execute().data

            if not defense:
                return await ctx.reply(f"❌ Không có phòng tuyến ở slot {slot}.")

            # Update unit status về idle
            if defense.get("unit_id"):
                supabase.table("military_units") \
                    .update({"status": "idle"}) \
                    .eq("id", defense["unit_id"]) \
                    .execute()

            # Xóa defense line
            supabase.table("defense_lines") \
                .delete() \
                .eq("nation_id", nation_id) \
                .eq("slot", slot) \
                .execute()

            await ctx.reply(f"✅ Đã xóa phòng tuyến slot {slot}.")
        else:
            # Xóa tất cả
            defenses = supabase.table("defense_lines") \
                .select("unit_id") \
                .eq("nation_id", nation_id) \
                .execute().data

            # Update tất cả units về idle
            for d in defenses:
                if d.get("unit_id"):
                    supabase.table("military_units") \
                        .update({"status": "idle"}) \
                        .eq("id", d["unit_id"]) \
                        .execute()

            # Xóa tất cả defense lines
            supabase.table("defense_lines") \
                .delete() \
                .eq("nation_id", nation_id) \
                .execute()

            await ctx.reply(f"✅ Đã xóa {len(defenses)} phòng tuyến.")


async def setup(bot):
    await bot.add_cog(FormDefense(bot))
