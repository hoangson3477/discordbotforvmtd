from discord.ext import commands
import discord
from cogs.natgame.__db import supabase


class SpecTrain(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="spectrain")
    async def spectrain(self, ctx, amount: int, branch: str):
        """
        !spectrain <amount> <navy|airforce>
        Ví dụ: !spectrain 20 navy
        """
        owner_id = str(ctx.author.id)
        branch = branch.lower()

        if branch not in ("navy", "airforce"):
            await ctx.reply("Quân chủng không hợp lệ. Dùng `navy` hoặc `airforce`.")
            return

        if amount <= 0:
            await ctx.reply("Số lượng phải lớn hơn 0.")
            return

        try:
            res = supabase.rpc(
                "nation_convert",
                {
                    "p_owner_id": owner_id,
                    "p_amount": amount,
                    "p_branch": branch
                }
            ).execute()

            if not res.data:
                await ctx.reply("Không có dữ liệu trả về từ hệ thống.")
                return

            data = res.data[0]

            embed = discord.Embed(
                title="Huấn luyện binh chủng đặc biệt",
                color=0x2ecc71
            )

            embed.add_field(
                name="📥 Yêu cầu huấn luyện",
                value=f"{data['requested']} quân",
                inline=False
            )
            embed.add_field(
                name="Thành công",
                value=f"{data['success']} quân",
                inline=True
            )
            embed.add_field(
                name="Thất bại",
                value=f"{data['failed']} quân (quay lại Lục quân)",
                inline=True
            )

            embed.add_field(
                name="Quân lực hiện tại",
                value=(
                    f"**Lục quân:** {data['final_army']}\n"
                    f"**Hải quân:** {data['final_navy']}\n"
                    f"**Không quân:** {data['final_airforce']}"
                ),
                inline=False
            )

            await ctx.send(embed=embed)

        except Exception as e:
            msg = str(e)

            if "Navy not unlocked" in msg:
                await ctx.reply("Quốc gia chưa mở khóa **Hải quân**.")
            elif "Airforce not unlocked" in msg:
                await ctx.reply("Quốc gia chưa mở khóa **Không quân**.")
            elif "Not enough army" in msg:
                await ctx.reply("Không đủ quân Lục quân để huấn luyện.")
            else:
                await ctx.reply("Lỗi hệ thống khi huấn luyện binh chủng.")
                raise e


async def setup(bot):
    await bot.add_cog(SpecTrain(bot))