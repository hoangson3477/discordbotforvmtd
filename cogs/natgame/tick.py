from discord.ext import commands, tasks
from .__db import supabase
import logging
import random
from datetime import datetime

logger = logging.getLogger("natgame.tick")

# Random events definition
RANDOM_EVENTS = [
    {
        "id": "bumper_crop",
        "name": "🌾 Mùa bội thu",
        "description": "Mùa màng thuận lợi, dân số tăng thêm 10%",
        "effect": "population",
        "value": 1.10,
        "chance": 0.05  # 5% per tick per nation
    },
    {
        "id": "merchant_visit",
        "name": "💰 Thương nhân qua đường",
        "description": "Đoàn thương nhân đến buôn bán, ngân khố +500",
        "effect": "money",
        "value": 500,
        "chance": 0.08
    },
    {
        "id": "desertion",
        "name": "🏃 Lính đào ngũ",
        "description": "Một số lính bỏ trốn do thiếu lương thực",
        "effect": "army_loss",
        "value": 0.05,  # Lose 5% army
        "chance": 0.03
    },
    {
        "id": "immigration",
        "name": "👥 Dân nhập cư",
        "description": "Dân từ các vùng khác đến sinh sống",
        "effect": "population_add",
        "value": 50,
        "chance": 0.06
    },
    {
        "id": "training_accident",
        "name": "⚠️ Tai nạn huấn luyện",
        "description": "Tai nạn trong lúc tập trận, mất một ít quân",
        "effect": "army_loss_flat",
        "value": 10,
        "chance": 0.04
    },
    {
        "id": "discovery",
        "name": "⛏️ Phát hiện mỏ quặng",
        "description": "Tìm thấy mỏ khoáng sản, ngân khố +1000",
        "effect": "money",
        "value": 1000,
        "chance": 0.02
    }
]


class NationTick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.nation_tick.start()

    def cog_unload(self):
        self.nation_tick.cancel()

    async def process_random_events(self):
        """Xử lý random events cho mỗi nation"""
        nations = supabase.table("nations").select("id, name, population, money, army, owner_id").execute().data

        events_triggered = []

        for nation in nations:
            for event in RANDOM_EVENTS:
                if random.random() < event["chance"]:
                    # Event triggered!
                    effect_desc = ""

                    if event["effect"] == "population":
                        new_pop = int(nation["population"] * event["value"])
                        supabase.table("nations").update({"population": new_pop}).eq("id", nation["id"]).execute()
                        effect_desc = f"Dân số: {nation['population']:,} → {new_pop:,}"

                    elif event["effect"] == "money":
                        new_money = nation["money"] + event["value"]
                        supabase.table("nations").update({"money": new_money}).eq("id", nation["id"]).execute()
                        effect_desc = f"Ngân khố +{event['value']:,} 💰"

                    elif event["effect"] == "population_add":
                        new_pop = nation["population"] + event["value"]
                        supabase.table("nations").update({"population": new_pop}).eq("id", nation["id"]).execute()
                        effect_desc = f"Dân số +{event['value']:,} 👥"

                    elif event["effect"] == "army_loss" and nation.get("army", 0) > 0:
                        loss = int(nation["army"] * event["value"])
                        new_army = max(0, nation["army"] - loss)
                        supabase.table("nations").update({"army": new_army}).eq("id", nation["id"]).execute()
                        effect_desc = f"Mất {loss:,} quân ⚔️"

                    elif event["effect"] == "army_loss_flat" and nation.get("army", 0) > 0:
                        loss = min(event["value"], nation["army"])
                        new_army = nation["army"] - loss
                        supabase.table("nations").update({"army": new_army}).eq("id", nation["id"]).execute()
                        effect_desc = f"Mất {loss} quân ⚔️"

                    events_triggered.append({
                        "nation_name": nation["name"],
                        "nation_id": nation["id"],
                        "owner_id": nation["owner_id"],
                        "event": event,
                        "effect": effect_desc
                    })

                    logger.info(f"Random event '{event['name']}' triggered for {nation['name']}")
                    break  # Chỉ 1 event mỗi tick mỗi nation

        return events_triggered

    @tasks.loop(minutes=10)
    async def nation_tick(self):
        try:
            # Tick tăng dân số và tiền
            result = supabase.rpc("nation_tick").execute()

            # Tick maintenance quân đội
            supabase.rpc("nation_maintenance_tick").execute()

            # Random events (10% chance có event cho mỗi nation)
            events = await self.process_random_events()

            if result.data is not None:
                logger.info(f"Tick OK, updated {result.data} nations, {len(events)} events triggered")

            # Thông báo events qua Discord (optional - có thể spam nên tắt)
            # for ev in events:
            #     # Tìm user và DM hoặc gửi vào channel
            #     pass

        except Exception as e:
            logger.error(f"Tick error: {e}", exc_info=True)

    @nation_tick.error
    async def nation_tick_error(self, error):
        """Xử lý lỗi từ task loop"""
        logger.error(f"Nation tick task error: {error}", exc_info=True)

    @commands.command(name="events")
    async def show_events(self, ctx):
        """Hiển thị danh sách các random events có thể xảy ra"""
        embed = discord.Embed(
            title="🎲 Random Events",
            description="Các sự kiện ngẫu nhiên có thể xảy ra mỗi 10 phút",
            color=discord.Color.blue()
        )

        for event in RANDOM_EVENTS:
            embed.add_field(
                name=f"{event['name']} ({event['chance']*100:.0f}%)",
                value=event['description'],
                inline=False
            )

        await ctx.reply(embed=embed)

    @nation_tick.before_loop
    async def before_tick(self):
        await self.bot.wait_until_ready()
        logger.info("Nation tick task started (every 10 minutes)")


async def setup(bot):
    await bot.add_cog(NationTick(bot))
