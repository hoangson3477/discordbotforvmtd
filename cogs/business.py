import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import asyncio
import math
import logging

logger = logging.getLogger("business")
logger.setLevel(logging.INFO)

VALID_UPGRADES = {
    "facility_level",
    "service_level"
}

class Business(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}
        self.profit_task.start()
        self.market_cycle.start()

    def cog_unload(self):
        self.profit_task.cancel()
        self.market_cycle.cancel()

    # -----------------------------
    # Utility
    # -----------------------------

    async def get_business(self, user_id: int, guild_id: int):
        async with self.bot.db.acquire() as conn:
            return await conn.fetchrow("""
                SELECT b.*, 
                    i.name AS industry_name,
                    i.base_demand,
                    i.base_spending,
                    i.employee_cost,
                    i.rent_cost,
                    i.materials_cost,
                    i.maintenance_cost
                FROM businesses b
                JOIN industries i ON b.industry_id = i.id
                WHERE b.user_id = $1 AND b.guild_id = $2
            """, user_id, guild_id)

    def check_cooldown(self, user_id, command, seconds):
        now = datetime.utcnow()
        key = f"{user_id}:{command}"

        if key in self.cooldowns:
            if now < self.cooldowns[key]:
                return False

        self.cooldowns[key] = now + timedelta(seconds=seconds)
        return True

    # -----------------------------
    # START BUSINESS
    # -----------------------------

    @commands.command()
    async def startbiz(self, ctx):
        existing = await self.get_business(ctx.author.id, ctx.guild.id)
        if existing:
            return await ctx.reply("Bạn đã có doanh nghiệp rồi.")

        async with self.bot.db.acquire() as conn:
            industries = await conn.fetch("SELECT * FROM industries")

        embed = discord.Embed(
            title="Chọn ngành nghề",
            description="\n".join(
                [f"**{i['id']}** - {i['name']}" for i in industries]
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def choose(self, ctx, industry_id: int):
        existing = await self.get_business(ctx.author.id, ctx.guild.id)
        if existing:
            return await ctx.reply("Bạn đã có doanh nghiệp.")

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO businesses (user_id, guild_id, industry_id)
                    VALUES ($1, $2, $3)
                """, ctx.author.id, ctx.guild.id, industry_id)

                await ctx.reply("Doanh nghiệp đã được tạo.")

    # -----------------------------
    # HIRE
    # -----------------------------

    @commands.command()
    async def hire(self, ctx, amount: int):

        if amount <= 0:
            return await ctx.reply("Số lượng không hợp lệ.")

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():

                biz = await conn.fetchrow("""
                    SELECT b.id, b.cash, i.employee_cost
                    FROM businesses b
                    JOIN industries i ON b.industry_id = i.id
                    WHERE b.user_id = $1 AND b.guild_id = $2
                    FOR UPDATE
                """, ctx.author.id, ctx.guild.id)

                if not biz:
                    return await ctx.reply("Bạn chưa có doanh nghiệp.")

                cost = biz["employee_cost"] * amount

                if biz["cash"] < cost:
                    return await ctx.reply("Không đủ tiền.")

                await conn.execute("""
                    UPDATE businesses
                    SET employees = employees + $1,
                        cash = cash - $2,
                        updated_at = NOW()
                    WHERE id = $3
                """, amount, cost, biz["id"])

        await ctx.reply(f"Đã thuê {amount} nhân viên.")

    # -----------------------------
    # UPGRADE
    # -----------------------------

    async def upgrade(self, ctx, column):

        if column not in VALID_UPGRADES:
            return await ctx.reply("Upgrade không hợp lệ.")

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():

                biz = await conn.fetchrow("""
                    SELECT id, cash, $1::text
                    FROM businesses
                    WHERE user_id = $2 AND guild_id = $3
                    FOR UPDATE
                """, column, ctx.author.id, ctx.guild.id)

                if not biz:
                    return await ctx.reply("Chưa có doanh nghiệp.")

                current = biz[column]
                upgrade_cost = int(5000 * math.pow(1.5, current))

                if biz["cash"] < upgrade_cost:
                    return await ctx.reply(f"Cần {upgrade_cost} để nâng cấp.")

                await conn.execute("""
                    UPDATE businesses
                    SET $1::text = $1::text + 1,
                        cash = cash - $2
                    WHERE id = $3
                """, column, upgrade_cost, biz["id"])

        await ctx.reply(f"Đã nâng cấp {column} lên {current + 1}")

    @commands.command()
    async def upgradefacility(self, ctx):
        await self.upgrade(ctx, "facility_level")

    @commands.command()
    async def upgradeservice(self, ctx):
        await self.upgrade(ctx, "service_level")

    # -----------------------------
    # OPEN BRANCH
    # -----------------------------

    @commands.command()
    async def openbranch(self, ctx):
        biz = await self.get_business(ctx.author.id, ctx.guild.id)
        if not biz:
            return await ctx.reply("Chưa có doanh nghiệp.")

        cost = 20000 * biz["branch_count"]

        if biz["cash"] < cost:
            return await ctx.reply("Không đủ tiền mở chi nhánh.")

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    UPDATE businesses
                    SET branch_count = branch_count + 1,
                        cash = cash - $1
                    WHERE id = $2
                """, cost, biz["id"])

        await ctx.reply("Đã mở thêm chi nhánh.")

    # -----------------------------
    # INFO
    # -----------------------------

    @commands.command()
    async def bizinfo(self, ctx):
        biz = await self.get_business(ctx.author.id, ctx.guild.id)
        if not biz:
            return await ctx.reply("Chưa có doanh nghiệp.")

        embed = discord.Embed(title="Thông tin doanh nghiệp")
        embed.add_field(name="Ngành", value=biz["industry_name"])
        embed.add_field(name="Level", value=biz["level"])
        embed.add_field(name="Nhân viên", value=biz["employees"])
        embed.add_field(name="Chi nhánh", value=biz["branch_count"])
        embed.add_field(name="Tiền", value=biz["cash"])
        await ctx.send(embed=embed)

    @commands.command()
    async def marketing(self, ctx, budget: int):

        if budget <= 0:
            return await ctx.reply("Ngân sách không hợp lệ.")

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():

                biz = await conn.fetchrow("""
                    SELECT id, cash
                    FROM businesses
                    WHERE user_id = $1 AND guild_id = $2
                    FOR UPDATE
                """, ctx.author.id, ctx.guild.id)

                if not biz:
                    return await ctx.reply("Bạn chưa có doanh nghiệp.")

                if biz["cash"] < budget:
                    return await ctx.reply("Không đủ tiền.")

                import random
                roll = random.random()

                # Tính bonus cơ bản
                base_effect = budget / 1000

                if roll < 0.7:
                    # Thành công bình thường
                    effect = base_effect
                    result = "Chiến dịch thành công."
                elif roll < 0.9:
                    # Bùng nổ
                    effect = base_effect * 1.5
                    result = "🔥 Chiến dịch bùng nổ! Hiệu quả vượt mong đợi."
                else:
                    # Thất bại
                    effect = 0
                    result = "❌ Chiến dịch thất bại."

                from datetime import datetime, timedelta

                marketing_until = datetime.utcnow() + timedelta(hours=1)

                await conn.execute("""
                    UPDATE businesses
                    SET cash = cash - $1,
                        marketing_bonus = $2,
                        marketing_until = $3
                    WHERE id = $4
                """, budget, effect, marketing_until, biz["id"])

        await ctx.reply(
            f"{result}\n"
            f"Ngân sách: {budget}\n"
            f"Bonus attraction: +{round(effect,2)} trong 2 chu kỳ."
        )

    @commands.command()
    async def expand(self, ctx, m2: int):

        if m2 <= 0:
            return await ctx.reply("Diện tích không hợp lệ.")

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():

                biz = await conn.fetchrow("""
                    SELECT id, cash, expansion_level
                    FROM businesses
                    WHERE user_id = $1 AND guild_id = $2
                    FOR UPDATE
                """, ctx.author.id, ctx.guild.id)

                if not biz:
                    return await ctx.reply("Bạn chưa có doanh nghiệp.")

                # Giá mở rộng tăng theo level
                base_cost = 2000
                scale = 1 + (biz["expansion_level"] * 0.25)

                cost = int(m2 * base_cost * scale)

                if biz["cash"] < cost:
                    return await ctx.reply(f"Cần {cost} để mở rộng.")

                await conn.execute("""
                    UPDATE businesses
                    SET area_size = area_size + $1,
                        cash = cash - $2,
                        expansion_level = expansion_level + 1
                    WHERE id = $3
                """, m2, cost, biz["id"])

        await ctx.reply(
            f"🏗 Mở rộng thành công {m2}m².\n"
            f"Chi phí: {cost}"
        )

    # -----------------------------
    # PROFIT LOOP
    # -----------------------------

    @tasks.loop(minutes=30)
    async def profit_task(self):

        logger.info("=== PROFIT TASK START ===")

        try:
            async with self.bot.db.acquire() as conn:

                economy = await conn.fetchrow("""
                    SELECT market_condition, demand_multiplier
                    FROM global_economy
                    WHERE id = 1
                """)

                if not economy:
                    logger.error("Global economy row not found!")
                    return

                demand_multiplier = economy["demand_multiplier"]
                logger.info(f"Market condition: {economy['market_condition']} | Multiplier: {demand_multiplier}")

                businesses = await conn.fetch("""
                    SELECT 
                        b.id AS business_id,
                        b.*,
                        i.id AS industry_real_id,
                        i.*
                    FROM businesses b
                    JOIN industries i ON b.industry_id = i.id
                """)

                logger.info(f"Total businesses loaded: {len(businesses)}")

                industry_map = {}

                for biz in businesses:
                    key = (biz["guild_id"], biz["industry_id"])
                    industry_map.setdefault(key, []).append(biz)

                total_processed = 0

                async with conn.transaction():

                    for (guild_id, industry_id), biz_list in industry_map.items():

                        if not biz_list:
                            continue

                        base_demand = biz_list[0]["base_demand"]
                        total_demand = int(base_demand * demand_multiplier)

                        logger.info(
                            f"[Guild {guild_id} | Industry {industry_id}] "
                            f"Businesses: {len(biz_list)} | Total Demand: {total_demand}"
                        )

                        attraction_scores = []
                        total_attraction = 0

                        for biz in biz_list:

                            marketing_bonus = 0

                            if biz["marketing_until"] and biz["marketing_until"] > datetime.utcnow():
                                marketing_bonus = biz["marketing_bonus"]

                            if biz["marketing_until"] and biz["marketing_until"] <= datetime.utcnow():
                                await conn.execute("""
                                    UPDATE businesses
                                    SET marketing_bonus = 0,
                                        marketing_until = NULL
                                    WHERE id = $1
                                """, biz["business_id"])

                            max_employees = biz["area_size"] // 5

                            if biz["employees"] > max_employees:
                                effective_employees = max_employees
                            else:
                                effective_employees = biz["employees"]

                            attraction = (
                                + effective_employees * 0.4
                                + biz["facility_level"] * 12
                                + biz["service_level"] * 10
                                + marketing_bonus
                                + biz["reputation"]
                            )

                            if attraction < 1:
                                attraction = 1

                            attraction_scores.append((biz, attraction))
                            total_attraction += attraction

                        if total_attraction == 0:
                            logger.warning("Total attraction is 0, skipping industry.")
                            continue

                        for biz, attraction in attraction_scores:

                            try:
                                share = attraction / total_attraction
                                customers = int(total_demand * share)

                                max_customers = biz["area_size"] * 2
                                customers = min(customers, max_customers)

                                avg_spending = int(
                                    biz["base_spending"]
                                    * (1 + 0.04 * biz["service_level"])
                                )

                                income = customers * avg_spending

                                expense = (
                                    biz["area_size"] * biz["rent_per_m2"]
                                    + (biz["employee_cost"] * biz["employees"])
                                    + biz["materials_cost"]
                                    + biz["maintenance_cost"]
                                )

                                net = income - expense

                                loss_streak = biz["loss_streak"]

                                if net < 0:
                                    loss_streak += 1
                                else:
                                    loss_streak = 0

                                if loss_streak >= 3:
                                    logger.warning(
                                        f"Business {biz['id']} triggered bankruptcy penalty."
                                    )
                                    net -= int(abs(net) * 0.2)
                                    loss_streak = 0

                                await conn.execute("""
                                    UPDATE businesses
                                    SET cash = cash + $1,
                                        loss_streak = $2,
                                        updated_at = NOW()
                                    WHERE id = $3
                                """, net, loss_streak, biz["business_id"])

                                await conn.execute("""
                                    INSERT INTO business_logs
                                    (business_id, customers, income, expense, net)
                                    VALUES ($1, $2, $3, $4, $5)
                                """, biz["business_id"], customers, income, expense, net)

                                logger.info(
                                    f"Business {biz['id']} | Customers: {customers} "
                                    f"| Income: {income} | Expense: {expense} | Net: {net}"
                                )

                                total_processed += 1

                            except Exception as e:
                                logger.exception(
                                    f"Error processing business ID {biz['id']}: {e}"
                                )

                logger.info(f"=== PROFIT TASK COMPLETE | Processed: {total_processed} businesses ===")

        except Exception as e:
            logger.exception(f"CRITICAL ERROR in profit_task: {e}")

    @tasks.loop(hours=6)
    async def market_cycle(self):

        import random

        conditions = [
            ("boom", 1.3),
            ("normal", 1.0),
            ("slow", 0.8),
            ("crisis", 0.6),
        ]

        condition, multiplier = random.choice(conditions)

        async with self.bot.db.acquire() as conn:
            await conn.execute("""
                UPDATE global_economy
                SET market_condition = $1,
                    demand_multiplier = $2,
                    updated_at = NOW()
                WHERE id = 1
            """, condition, multiplier)

    @profit_task.before_loop
    @market_cycle.before_loop
    async def before_profit_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Business(bot))