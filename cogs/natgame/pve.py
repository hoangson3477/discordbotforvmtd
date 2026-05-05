import discord
from discord.ext import commands
from cogs.natgame.__db import supabase
from cogs.natgame.war.war_service import WarService
from cogs.natgame.war.pve_adapter import PVEAdapter
import logging

logger = logging.getLogger("natgame.pve")


class PVECog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.supabase = supabase

    @commands.command()
    async def pve(self, ctx):
        user_id = str(ctx.author.id)

        # 1️⃣ Lấy nation của attacker
        nation_res = self.supabase.table("nations") \
            .select("id, name") \
            .eq("owner_id", user_id) \
            .single().execute()

        if not nation_res.data:
            return await ctx.reply("❌ Bạn chưa có quốc gia. Dùng `!gameregister` trước.")

        attacker_nation_id = nation_res.data["id"]
        nation_name = nation_res.data["name"]

        # 2️⃣ Kiểm tra có war army không (lấy cái mới nhất)
        war_army_res = self.supabase.table("war_armies") \
            .select("id") \
            .eq("nation_id", attacker_nation_id) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()

        if not war_army_res.data:
            return await ctx.reply("❌ Bạn chưa có war army. Dùng `!setwararmy` trước.")

        # 3️⃣ Tạo war record PVE
        war_insert = self.supabase.table("wars").insert({
            "attacker_nation_id": attacker_nation_id,
            "defender_nation_id": None,
            "status": "ongoing",
            "war_type": "pve"
        }).execute().data

        war_id = war_insert[0]["id"]

        # 4️⃣ Load units từ war army để tạo snapshot
        war_army_id = war_army_res.data[0]["id"]
        units_res = self.supabase.table("war_army_units") \
            .select("unit_id, troops, loose_troops") \
            .eq("war_army_id", war_army_id) \
            .execute()

        # Insert vào war_attack_snapshot
        total_snapshot_troops = 0
        for u in units_res.data:
            # Tính tổng troops (unit + loose)
            unit_troops = u.get("troops") or 0
            loose_troops = u.get("loose_troops") or 0
            troops = unit_troops + loose_troops

            if troops > 0:
                self.supabase.table("war_attack_snapshot").insert({
                    "war_id": war_id,
                    "unit_id": u.get("unit_id"),
                    "troops": troops
                }).execute()
                total_snapshot_troops += troops
                logger.debug(f"Snapshot: unit_id={u.get('unit_id')}, troops={troops}")

        logger.info(f"PVE Snapshot created: {total_snapshot_troops} troops for war {war_id}")

        # 5️⃣ Chạy combat
        adapter = PVEAdapter(self.supabase)
        service = WarService(adapter)

        try:
            result = service.resolve_war(war_id=war_id)

            # 6️⃣ Phân phối phần thưởng PVE
            rewards_text = ""
            if result['result'] == 'attacker_win':
                # Tính reward dựa trên độ khó
                difficulty_multipliers = {"easy": 1, "medium": 2, "hard": 3}
                diff = result.get('difficulty', 'medium')
                multiplier = difficulty_multipliers.get(diff, 2)

                money_reward = 500 * multiplier
                exp_reward = 30 * multiplier

                # Cộng tiền
                nation_current = supabase.table("nations").select("money").eq("id", attacker_nation_id).single().execute().data
                if nation_current:
                    new_money = nation_current["money"] + money_reward
                    supabase.table("nations").update({"money": new_money}).eq("id", attacker_nation_id).execute()

                # Cộng EXP
                from cogs.natgame.__utils_level import add_nation_exp
                leveled_up, new_level = add_nation_exp(supabase, attacker_nation_id, exp_reward)

                rewards_text = (
                    f"💰 **{money_reward:,}** money\n"
                    f"⭐ **{exp_reward}** EXP"
                )
                if leveled_up:
                    rewards_text += f"\n🎉 **LEVEL UP!** Bạn đã đạt level **{new_level}**!"

                # Cập nhật war winner
                supabase.table("wars").update({
                    "winner_nation_id": attacker_nation_id,
                    "status": "finished",
                    "ended_at": "now()"
                }).eq("id", war_id).execute()
            else:
                # Thua vẫn có ít EXP
                from cogs.natgame.__utils_level import add_nation_exp
                add_nation_exp(supabase, attacker_nation_id, 10)
                rewards_text = "⭐ **10** EXP (Thưởng tham gia)"

                supabase.table("wars").update({
                    "status": "finished",
                    "ended_at": "now()"
                }).eq("id", war_id).execute()

            # 7️⃣ Hiển thị kết quả
            embed = discord.Embed(
                title=f"⚔️ PVE Combat - {nation_name}",
                color=discord.Color.green() if result['result'] == 'attacker_win' else discord.Color.red()
            )

            embed.add_field(
                name="Kết quả",
                value="**CHIẾN THẮNG** 🎉" if result['result'] == 'attacker_win' else "**THẤT BẠI** 💀",
                inline=False
            )

            # Tính tổng thiệt hại từ logs
            total_loss = sum(log.get("attacker_loss", 0) for log in result.get("logs", []))
            starting_troops = total_snapshot_troops
            remaining = result.get('attacker_remaining', 0)

            embed.add_field(
                name="Độ khó",
                value=result.get('difficulty', 'medium').title(),
                inline=True
            )

            embed.add_field(
                name="Quân số",
                value=f"Ban đầu: {starting_troops:,}\n"
                      f"Thiệt hại: -{total_loss:,}\n"
                      f"Còn lại: {remaining:,}",
                inline=True
            )

            embed.add_field(
                name="Phần thưởng",
                value=rewards_text,
                inline=False
            )

            if result.get('logs'):
                log_summary = "\n".join([
                    f"Round {log['round']}: {log['description'][:50]}..."
                    for log in result['logs'][:3]
                ])
                embed.add_field(
                    name="Diễn biến",
                    value=log_summary or "Không có log",
                    inline=False
                )

            await ctx.reply(embed=embed)

        except Exception as e:
            logger.error(f"PVE combat error: {e}")
            await ctx.reply(f"❌ Lỗi trong combat: {e}")


async def setup(bot):
    await bot.add_cog(PVECog(bot))
