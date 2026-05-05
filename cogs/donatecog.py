import discord
from discord.ext import commands
import time
import random

class DonateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_sent = {}  # cooldown global
        self.last_trigger_time = 0

    def can_send(self, channel_id):
        last = self.last_sent.get(channel_id, 0)
        return time.time() - last >= 180

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # chỉ bắt tin nhắn bot
        if message.author != self.bot.user:
            return

        if not message.guild:
            return

        now = time.time()

        # 🔥 FIX: chống bị gọi 2 lần liên tiếp
        if now - self.last_trigger_time < 2:
            return
        self.last_trigger_time = now

        # 🎲 30% chance
        if random.random() > 0.3:
            return

        # cooldown theo channel
        if not self.can_send(message.channel.id):
            return

        try:
            await message.channel.send(
                "Nếu ae thấy bot hữu ích, hãy ủng hộ để thg bloxfruit làm bot lâu dài và maybe thuê VPS chạy bot\n"
                "Dùng `!donate` để xem chi tiết."
            )
            self.last_sent[message.channel.id] = time.time()
        except Exception:
            pass

    @commands.command(name="donate")
    async def donate(self, ctx):
        embed = discord.Embed(
            title="Ủng hộ bloxfruit và bot",
            description="Cảm ơn ae đã quan tâm!",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Thông tin donate",
            value=(
                "Momo: 0906690134\n"
                "Bank: Vietcombank - 1906690134\n"
                "Chủ TK: Le Thai Hoang Son"
            ),
            inline=False
        )

        embed.set_footer(text="Mọi donate sẽ giúp thg bloxfruit làm bot lâu dài và maybe thuê VPS chạy bot")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(DonateCog(bot))