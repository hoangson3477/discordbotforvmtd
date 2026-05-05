import discord
from discord.ext import commands
import re

from cogs.natgame.__db import supabase

UNIT_TIERS = {
    "to": (3, 5),
    "tieu_doi": (8, 12),
    "trung_doi": (25, 40),
    "dai_doi": (80, 150),
    "tieu_doan": (300, 800),
    "trung_doan": (1000, 3000),
    "lu_doan": (3000, 6000),
    "su_doan": (10000, 20000),
}

# Display names với dấu và chỉ hoa chữ cái đầu
TIER_DISPLAY = {
    "to": "Tổ",
    "tieu_doi": "Tiểu đội",
    "trung_doi": "Trung đội",
    "dai_doi": "Đại đội",
    "tieu_doan": "Tiểu đoàn",
    "trung_doan": "Trung đoàn",
    "lu_doan": "Lữ đoàn",
    "su_doan": "Sư đoàn",
}

def format_unit_name(name: str) -> str:
    """
    Chuyển tên như 'ĐộiA', 'TienPhong' thành 'Đội A', 'Tien Phong'
    Thêm khoảng trắng trước chữ hoa (trừ chữ cái đầu tiên)
    """
    # Thêm khoảng trắng trước chữ hoa (trừ đầu câu)
    formatted = re.sub(r'(?<!^)(?=[A-Z])', ' ', name)
    return formatted

def get_tier_display(tier: str) -> str:
    """Lấy tên cấp bậc có dấu"""
    return TIER_DISPLAY.get(tier, tier.replace("_", " ").title())


class FormUnit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="formunit")
    async def formunit(self, ctx, *, args: str):
        """
        Tạo đơn vị quân mới
        !formunit <tên> <cấp bậc> <số quân>
        VD: !formunit Đội A tieu_doi 10
        VD: !formunit "Tiểu Đoàn 1" tieu_doan 500
        """
        # Parse arguments
        parts = args.strip().split()

        if len(parts) < 3:
            return await ctx.send(
                "❌ Cú pháp: `!formunit <tên> <cấp bậc> <số quân>`\n"
                "VD: `!formunit Đội A tieu_doi 10` hoặc `!formunit 'Tiểu Đoàn 1' tieu_doan 500`"
            )

        # Lấy size (số cuối cùng)
        try:
            size = int(parts[-1])
        except ValueError:
            return await ctx.send("❌ Số quân phải là số nguyên.")

        # Lấy tier (phần tử áp chót)
        tier = parts[-2].lower()

        # Phần còn lại là tên unit
        unit_name_raw = " ".join(parts[:-2])

        # Xử lý tên: thêm khoảng trắng trước chữ hoa (ĐộiA -> Đội A)
        unit_name = format_unit_name(unit_name_raw)

        if tier not in UNIT_TIERS:
            valid_tiers = ", ".join(TIER_DISPLAY.values())
            return await ctx.send(
                f"❌ Cấp bậc không hợp lệ.\n"
                f"Hợp lệ: {valid_tiers}\n"
                f"(nhập: {', '.join(UNIT_TIERS.keys())})"
            )

        min_size, max_size = UNIT_TIERS[tier]

        if size < min_size or size > max_size:
            tier_display = get_tier_display(tier)
            return await ctx.send(
                f"❌ Quân số không hợp lệ cho **{tier_display}**.\n"
                f"Cho phép: {min_size} – {max_size}"
            )

        user_id = str(ctx.author.id)

        # 1️⃣ Lấy nation
        nation = (
            supabase.table("nations")
            .select("id, army")
            .eq("owner_id", user_id)
            .single()
            .execute()
        )

        if not nation.data:
            return await ctx.send("❌ Bạn chưa có quốc gia.")

        nation_id = nation.data["id"]
        army = nation.data["army"]

        # 2️⃣ Check quân
        if army < size:
            return await ctx.send(
                f"❌ Không đủ quân.\n"
                f"Army hiện tại: {army}"
            )

        # 3️⃣ Tạo unit
        try:
            supabase.table("military_units").insert({
                "nation_id": nation_id,
                "name": unit_name,
                "tier": tier,
                "branch": "army",
                "size": size,
                "level": 1,
                "exp": 0,
                "status": "idle",
            }).execute()
        except Exception:
            return await ctx.send(
                "❌ Không thể tạo đơn vị (có thể trùng tên)."
            )

        # 4️⃣ Trừ quân
        supabase.table("nations").update({
            "army": army - size
        }).eq("id", nation_id).execute()

        # 5️⃣ Confirm
        tier_display = get_tier_display(tier)
        await ctx.send(
            f"**THÀNH LẬP ĐƠN VỊ THÀNH CÔNG**\n"
            f"• Tên: **{unit_name}**\n"
            f"• Cấp: **{tier_display}**\n"
            f"• Quân số: **{size}**\n"
            f"• Binh chủng: **Lục quân**"
        )

    @commands.command(name="listunits")
    async def list_units(self, ctx):
        """Liệt kê tất cả đơn vị quân đội"""
        user_id = str(ctx.author.id)

        nation = supabase.table("nations") \
            .select("id, name") \
            .eq("owner_id", user_id) \
            .single().execute().data

        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        units = supabase.table("military_units") \
            .select("name, tier, size, status, level") \
            .eq("nation_id", nation["id"]) \
            .order("tier") \
            .execute().data

        if not units:
            return await ctx.reply("❌ Chưa có đơn vị nào. Dùng `!formunit` để tạo.")

        embed = discord.Embed(
            title=f"📋 Đơn vị quân đội - {nation['name']}",
            color=discord.Color.blue()
        )

        # Group by status
        status_icons = {
            "idle": "🟢",
            "war": "⚔️",
            "defense": "🛡️"
        }

        units_text = []
        for u in units:
            icon = status_icons.get(u["status"], "⚪")
            tier_display = get_tier_display(u["tier"])
            units_text.append(
                f"{icon} **{u['name']}** | {tier_display} | {u['size']:,} quân | Lv.{u['level']}"
            )

        embed.description = "\n".join(units_text)
        embed.set_footer(text="🟢 Rảnh | ⚔️ Tập đoàn quân | 🛡️ Phòng tuyến")

        await ctx.reply(embed=embed)

    @commands.command(name="disbandunit")
    async def disband_unit(self, ctx, *, unit_name: str):
        """Giải tán đơn vị, trả quân về kho"""
        user_id = str(ctx.author.id)

        nation = supabase.table("nations") \
            .select("id, army") \
            .eq("owner_id", user_id) \
            .single().execute().data

        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        # Tìm unit
        unit = supabase.table("military_units") \
            .select("id, name, size, status") \
            .eq("nation_id", nation["id"]) \
            .eq("name", unit_name.strip()) \
            .single().execute().data

        if not unit:
            return await ctx.reply(f"❌ Không tìm thấy đơn vị **{unit_name}**.")

        if unit["status"] != "idle":
            return await ctx.reply(
                f"❌ Đơn vị **{unit_name}** đang {unit['status']}. "
                "Phải rút về trước khi giải tán."
            )

        # Trả quân về kho
        new_army = nation["army"] + unit["size"]

        # Xóa unit
        supabase.table("military_units") \
            .delete() \
            .eq("id", unit["id"]) \
            .execute()

        # Cập nhật army
        supabase.table("nations") \
            .update({"army": new_army}) \
            .eq("id", nation["id"]) \
            .execute()

        await ctx.reply(
            f"✅ Đã giải tán **{unit_name}**\n"
            f"• {unit['size']:,} quân đã trở về kho\n"
            f"• Tổng quân: {new_army:,}"
        )


async def setup(bot):
    await bot.add_cog(FormUnit(bot))
