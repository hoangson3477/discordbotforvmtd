import discord
from discord.ext import commands

class GetRoleID(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="getroleid")
    async def get_role_id(self, ctx: commands.Context, role: discord.Role = None):
        if role is None:
            await ctx.send("Vui lòng tag 1 role.\nVí dụ: `!getroleid @Admin`")
            return

        await ctx.send(
            f"**Role:** {role.mention}\n"
            f"**Role ID:** `{role.id}`"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(GetRoleID(bot))
