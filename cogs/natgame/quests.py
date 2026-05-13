"""
NATGAME Quests & Achievements System
"""
import discord
from discord.ext import commands
from cogs.natgame.__db import supabase

# Quests definition
DAILY_QUESTS = [
    {
        "id": "daily_recruit",
        "name": "🎖️ Tuyển quân hàng ngày",
        "description": "Tuyển ít nhất 50 quân",
        "requirement": "recruit_50",
        "reward_money": 300,
        "reward_exp": 20
    },
    {
        "id": "daily_pve",
        "name": "⚔️ Luyện tập chiến đấu",
        "description": "Thắng 1 trận PVE",
        "requirement": "win_pve_1",
        "reward_money": 500,
        "reward_exp": 30
    },
    {
        "id": "daily_form_unit",
        "name": "🛡️ Xây dựng quân đội",
        "description": "Thành lập 1 đơn vị quân mới",
        "requirement": "form_unit_1",
        "reward_money": 400,
        "reward_exp": 25
    }
]

ACHIEVEMENTS = [
    {
        "id": "first_blood",
        "name": "🩸 First Blood",
        "description": "Thắng war đầu tiên",
        "requirement": "win_war_1",
        "reward_money": 1000,
        "reward_exp": 100
    },
    {
        "id": "veteran",
        "name": "⚔️ Chiến binh kỳ cựu",
        "description": "Thắng 10 trận war",
        "requirement": "win_war_10",
        "reward_money": 5000,
        "reward_exp": 300
    },
    {
        "id": "warlord",
        "name": "👑 Chúa tể chiến tranh",
        "description": "Thắng 50 trận war",
        "requirement": "win_war_50",
        "reward_money": 20000,
        "reward_exp": 1000
    },
    {
        "id": "recruiter",
        "name": "📢 Nhà tuyển quân",
        "description": "Tuyển tổng cộng 1000 quân",
        "requirement": "recruit_total_1000",
        "reward_money": 2000,
        "reward_exp": 150
    },
    {
        "id": "rich",
        "name": "💰 Triệu phú",
        "description": "Có 10,000 money trong ngân khố",
        "requirement": "have_money_10000",
        "reward_money": 5000,
        "reward_exp": 200
    },
    {
        "id": "population",
        "name": "🌍 Đế chế đông dân",
        "description": "Đạt 1000 dân số",
        "requirement": "have_population_1000",
        "reward_money": 3000,
        "reward_exp": 150
    },
    {
        "id": "level_5",
        "name": "⭐ Đang lên",
        "description": "Đạt level 5",
        "requirement": "reach_level_5",
        "reward_money": 2000,
        "reward_exp": 100
    },
    {
        "id": "level_10",
        "name": "🌟 Huyền thoại",
        "description": "Đạt level 10",
        "requirement": "reach_level_10",
        "reward_money": 10000,
        "reward_exp": 500
    }
]


class Quests(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="quests")
    async def show_quests(self, ctx):
        """Hiển thị nhiệm vụ hàng ngày"""
        user_id = str(ctx.author.id)

        nation = supabase.table("nations").select("id, name").eq("owner_id", user_id).single().execute().data
        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        # Lấy tiến độ quest
        quest_progress = supabase.table("quest_progress").select("quest_id, progress, completed").eq("nation_id", nation["id"]).execute().data
        progress_map = {q["quest_id"]: q for q in quest_progress}

        embed = discord.Embed(
            title=f"📜 Nhiệm vụ hàng ngày - {nation['name']}",
            description="Completed để nhận thưởng!",
            color=discord.Color.gold()
        )

        for quest in DAILY_QUESTS:
            prog = progress_map.get(quest["id"], {"progress": 0, "completed": False})

            if prog["completed"]:
                status = "✅ Completed"
            else:
                status = f"⏳ Đang làm ({prog['progress']}/?)"

            embed.add_field(
                name=f"{quest['name']}",
                value=(
                    f"{quest['description']}\n"
                    f"🎁 {quest['reward_money']:,} 💰 | {quest['reward_exp']} EXP\n"
                    f"Status: {status}"
                ),
                inline=False
            )

        embed.set_footer(text="Nhiệm vụ reset mỗi ngày lúc 00:00 UTC")
        await ctx.reply(embed=embed)

    @commands.command(name="achievements", aliases=["achieve"])
    async def show_achievements(self, ctx):
        """Hiển thị thành tích đã đạt được"""
        user_id = str(ctx.author.id)

        nation = supabase.table("nations").select("id, name").eq("owner_id", user_id).single().execute().data
        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        # Lấy achievements đã Completed
        completed = supabase.table("achievements").select("achievement_id").eq("nation_id", nation["id"]).execute().data
        completed_ids = {a["achievement_id"] for a in completed}

        embed = discord.Embed(
            title=f"🏆 Thành tích - {nation['name']}",
            color=discord.Color.purple()
        )

        completed_text = []
        pending_text = []

        for ach in ACHIEVEMENTS:
            if ach["id"] in completed_ids:
                completed_text.append(f"✅ **{ach['name']}** - {ach['description']}")
            else:
                pending_text.append(
                    f"⬜ **{ach['name']}** - {ach['description']}\n"
                    f"   🎁 {ach['reward_money']:,} 💰 | {ach['reward_exp']} EXP"
                )

        if completed_text:
            embed.add_field(
                name=f"Đã đạt ({len(completed_text)}/{len(ACHIEVEMENTS)})",
                value="\n".join(completed_text) or "Chưa có",
                inline=False
            )

        if pending_text:
            embed.add_field(
                name="Chưa đạt",
                value="\n".join(pending_text[:5]) + ("\n..." if len(pending_text) > 5 else ""),
                inline=False
            )

        await ctx.reply(embed=embed)

    @commands.command(name="claim")
    async def claim_rewards(self, ctx):
        """Nhận thưởng nhiệm vụ đã Completed"""
        user_id = str(ctx.author.id)

        nation = supabase.table("nations").select("id, money").eq("owner_id", user_id).single().execute().data
        if not nation:
            return await ctx.reply("❌ Bạn chưa có quốc gia.")

        # Lấy quests đã Completed nhưng chưa nhận thưởng
        completed_quests = supabase.table("quest_progress") \
            .select("quest_id") \
            .eq("nation_id", nation["id"]) \
            .eq("completed", True) \
            .eq("claimed", False) \
            .execute().data

        if not completed_quests:
            return await ctx.reply("⏳ Không có nhiệm vụ nào để nhận thưởng. Completed nhiệm vụ trước!")

        total_money = 0
        total_exp = 0

        from cogs.natgame.__utils_level import add_nation_exp

        for q in completed_quests:
            quest_def = next((dq for dq in DAILY_QUESTS if dq["id"] == q["quest_id"]), None)
            if quest_def:
                total_money += quest_def["reward_money"]
                total_exp += quest_def["reward_exp"]

                # Đánh dấu đã nhận
                supabase.table("quest_progress") \
                    .update({"claimed": True}) \
                    .eq("nation_id", nation["id"]) \
                    .eq("quest_id", q["quest_id"]) \
                    .execute()

        # Cộng tiền
        new_money = nation["money"] + total_money
        supabase.table("nations").update({"money": new_money}).eq("id", nation["id"]).execute()

        # Cộng EXP
        add_nation_exp(supabase, nation["id"], total_exp)

        embed = discord.Embed(
            title="🎁 Nhận thưởng thành công!",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Đã nhận",
            value=(
                f"💰 **{total_money:,}** money\n"
                f"⭐ **{total_exp}** EXP\n"
                f"📜 {len(completed_quests)} nhiệm vụ"
            ),
            inline=False
        )

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Quests(bot))
