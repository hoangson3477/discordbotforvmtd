import discord
from discord.ext import commands
from datetime import datetime, timedelta
from cogs.natgame.__db import supabase
from cogs.natgame.war.war_adapter import WarAdapter
from cogs.natgame.war.war_service import WarService

class War(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="war")
    async def war(self, ctx):
        if not ctx.message.mentions:
            return await ctx.reply("❌ Cú pháp: !war @user")

        attacker_user_id = str(ctx.author.id)
        defender_user_id = str(ctx.message.mentions[0].id)

        # 1️⃣ Load nation
        attacker = supabase.table("nations") \
            .select("*") \
            .eq("owner_id", attacker_user_id) \
            .single().execute().data

        defender = supabase.table("nations") \
            .select("*") \
            .eq("owner_id", defender_user_id) \
            .single().execute().data

        if not attacker or not defender:
            return await ctx.reply("❌ Một trong hai bên chưa có quốc gia.")

        # 2️⃣ Tạo war record
        war = supabase.table("wars").insert({
            "attacker_nation_id": attacker["id"],
            "defender_nation_id": defender["id"],
            "status": "active"
        }).execute().data[0]

        war_id = war["id"]

        # =============================
        # 3️⃣ SNAPSHOT ATTACKER
        # =============================
        war_army = supabase.table("war_armies") \
            .select("id") \
            .eq("nation_id", attacker["id"]) \
            .single().execute().data

        if not war_army:
            return await ctx.reply("❌ Bạn chưa có war army. Dùng `!setwararmy` trước.")

        # Lấy war_army_units (có thể là unit hoặc loose troops)
        war_units = supabase.table("war_army_units") \
            .select("unit_id, loose_troops") \
            .eq("war_army_id", war_army["id"]) \
            .execute().data

        for u in war_units:
            troops = 0
            if u.get("unit_id"):
                # Lấy size từ military_units
                unit_data = supabase.table("military_units") \
                    .select("size") \
                    .eq("id", u["unit_id"]) \
                    .single().execute().data
                if unit_data:
                    troops = unit_data["size"]
            elif u.get("loose_troops"):
                troops = u["loose_troops"]

            if troops > 0:
                supabase.table("war_attack_snapshot").insert({
                    "war_id": war_id,
                    "unit_id": u["unit_id"],
                    "troops": troops
                }).execute()

        # =============================
        # 4️⃣ SNAPSHOT DEFENDER
        # =============================
        defenses = supabase.table("defense_lines") \
            .select("slot, unit_id") \
            .eq("nation_id", defender["id"]) \
            .order("slot") \
            .execute().data

        for d in defenses:
            troops = 0
            if d.get("unit_id"):
                # Lấy size từ military_units
                unit_data = supabase.table("military_units") \
                    .select("size") \
                    .eq("id", d["unit_id"]) \
                    .single().execute().data
                if unit_data:
                    troops = unit_data["size"]

            if troops > 0:
                supabase.table("war_defense_snapshot").insert({
                    "war_id": war_id,
                    "slot": d["slot"],
                    "unit_id": d["unit_id"],
                    "troops": troops
                }).execute()

        await ctx.reply("⚔️ War started! Dùng !warresolve để xử lý.")

    @commands.command()
    async def warresolve(self, ctx):
        war = supabase.table("wars") \
            .select("*") \
            .eq("status", "active") \
            .limit(1).execute().data

        if not war:
            return await ctx.send("❌ Không có war đang diễn ra.")

        war = war[0]

        adapter = WarAdapter(supabase)
        service = WarService(adapter)

        result = service.resolve_war(war["id"])

        # Phân phối phần thưởng
        winner_id = None
        loser_id = None
        winner_side = None

        if result['result'] == 'attacker_win':
            winner_id = war["attacker_nation_id"]
            loser_id = war["defender_nation_id"]
            winner_side = "attacker"
        elif result['result'] == 'defender_win':
            winner_id = war["defender_nation_id"]
            loser_id = war["attacker_nation_id"]
            winner_side = "defender"

        rewards_text = ""
        if winner_id and loser_id:
            # Lấy thông tin loser
            loser = supabase.table("nations").select("money, name").eq("id", loser_id).single().execute().data
            winner = supabase.table("nations").select("name").eq("id", winner_id).single().execute().data

            if loser and winner:
                # Winner nhận 10% money của loser
                reward_money = int(loser["money"] * 0.1)

                # Cộng tiền cho winner
                winner_current = supabase.table("nations").select("money").eq("id", winner_id).single().execute().data
                if winner_current:
                    new_money = winner_current["money"] + reward_money
                    supabase.table("nations").update({"money": new_money}).eq("id", winner_id).execute()

                # Trừ tiền loser
                new_loser_money = loser["money"] - reward_money
                supabase.table("nations").update({"money": new_loser_money}).eq("id", loser_id).execute()

                # Thêm EXP cho cả 2 (winner nhiều hơn)
                from cogs.natgame.__utils_level import add_nation_exp
                add_nation_exp(supabase, winner_id, 50)  # Winner +50 EXP
                add_nation_exp(supabase, loser_id, 20)   # Loser +20 EXP

                # Cập nhật war winner
                supabase.table("wars").update({
                    "winner_nation_id": winner_id,
                    "status": "finished",
                    "ended_at": "now()"
                }).eq("id", war["id"]).execute()

                rewards_text = (
                    f"\n\n🎁 **Phần thưởng:**\n"
                    f"🏆 **{winner['name']}** nhận {reward_money:,} money (10% của {loser['name']})\n"
                    f"⭐ EXP: +50 (Winner), +20 (Loser)"
                )

        embed = discord.Embed(
            title="⚔️ WAR KẾT THÚC",
            color=discord.Color.green() if winner_side == "attacker" else discord.Color.red() if winner_side == "defender" else discord.Color.gray()
        )

        embed.add_field(
            name="Kết quả",
            value=f"**{result['result'].replace('_', ' ').title()}**",
            inline=False
        )

        embed.add_field(
            name="Attacker còn",
            value=f"{result.get('attacker_remaining', 0):,} quân",
            inline=True
        )

        embed.add_field(
            name="Defender còn",
            value=f"{result.get('defender_remaining', 0):,} quân",
            inline=True
        )

        if rewards_text:
            embed.add_field(
                name="Phần thưởng",
                value=rewards_text,
                inline=False
            )

        embed.set_footer(text="Dùng !warlog để xem chi tiết diễn biến trận đánh")
        await ctx.send(embed=embed)

    @commands.command(name="warlog", aliases=["battlereport", "br"])
    async def war_log(self, ctx, war_id: str = None):
        """
        Xem chi tiết diễn biến trận đánh
        !warlog <war_id> - Xem trận cụ thể
        !warlog - Xem trận đánh gần nhất của bạn
        """
        user_id = str(ctx.author.id)

        # Lấy nation
        nation = supabase.table("nations") \
            .select("id, name") \
            .eq("owner_id", user_id) \
            .single().execute().data

        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        # Nếu không có war_id, tìm trận gần nhất
        if not war_id:
            recent_war = supabase.table("wars") \
                .select("id, status, created_at, winner_nation_id, attacker_nation_id, defender_nation_id") \
                .or_(f"attacker_nation_id.eq.{nation['id']},defender_nation_id.eq.{nation['id']}") \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute().data

            if not recent_war:
                return await ctx.reply("❌ Bạn chưa tham gia trận đánh nào.")

            war_id = recent_war[0]["id"]
            war_info = recent_war[0]
        else:
            # Lấy thông tin war cụ thể
            war_info = supabase.table("wars") \
                .select("id, status, created_at, winner_nation_id, attacker_nation_id, defender_nation_id") \
                .eq("id", war_id) \
                .single().execute().data

            if not war_info:
                return await ctx.reply(f"❌ Không tìm thấy trận đánh **{war_id}**.")

        # Lấy war logs
        logs = supabase.table("war_logs") \
            .select("round, phase, attacker_loss, defender_loss, description") \
            .eq("war_id", war_id) \
            .order("round") \
            .execute().data

        if not logs:
            return await ctx.reply("❌ Không có dữ liệu diễn biến cho trận này.")

        # Lấy tên các bên
        attacker = supabase.table("nations") \
            .select("name").eq("id", war_info["attacker_nation_id"]).single().execute().data
        defender_id = war_info.get("defender_nation_id")
        defender = supabase.table("nations") \
            .select("name").eq("id", defender_id).single().execute().data if defender_id else None

        attacker_name = attacker["name"] if attacker else "Unknown"
        defender_name = defender["name"] if defender else "Bot (PvE)"

        # Tạo embed
        embed = discord.Embed(
            title=f"📜 Báo cáo trận đánh",
            description=f"**{attacker_name}** vs **{defender_name}**",
            color=discord.Color.dark_red()
        )

        # Thông tin tổng quan
        status_text = "✅ Hoàn thành" if war_info["status"] == "finished" else "⏳ Đang diễn ra"
        winner_text = "🎉 " + (attacker_name if war_info.get("winner_nation_id") == war_info["attacker_nation_id"] else defender_name) if war_info.get("winner_nation_id") else "❓ Chưa có"

        embed.add_field(
            name="Trạng thái",
            value=f"{status_text}\n🏆 Người thắng: {winner_text}",
            inline=True
        )

        # Tính tổng thiệt hại
        total_atk_loss = sum(l["attacker_loss"] for l in logs)
        total_def_loss = sum(l["defender_loss"] for l in logs)

        embed.add_field(
            name="Tổng thiệt hại",
            value=f"⚔️ {attacker_name}: -{total_atk_loss:,} quân\n🛡️ {defender_name}: -{total_def_loss:,} quân",
            inline=True
        )

        # Chi tiết từng round (deduplicate nếu có)
        seen = set()
        unique_logs = []
        for log in logs:
            key = (log["round"], log["phase"], log["attacker_loss"], log["defender_loss"])
            if key not in seen:
                seen.add(key)
                unique_logs.append(log)

        logs_text = []
        for log in unique_logs:
            phase_icon = "🛡️" if log["phase"] == "defense" else "🏰"
            logs_text.append(
                f"**Round {log['round']}** {phase_icon}\n"
                f"⚔️ -{log['attacker_loss']:,} | 🛡️ -{log['defender_loss']:,}\n"
                f"*{log['description']}*"
            )

        # Chia thành các field nếu quá dài
        logs_content = "\n\n".join(logs_text)
        if len(logs_content) > 1000:
            logs_content = logs_content[:997] + "..."

        embed.add_field(
            name="Diễn biến chi tiết",
            value=logs_content or "Không có dữ liệu",
            inline=False
        )

        embed.set_footer(text=f"War ID: {war_id}")
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(War(bot))
