import discord
from discord.ext import commands

class GiveRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # ====== CONFIG ======
        self.ALLOWED_ROLES = [
            897810289234411550,  # ID role được phép give
            1465413279911252180,
            1126751064377544704,
            1113827968901447722,
            1413571646501027861,
        ]

        self.LOG_CHANNEL_ID = 1396447272103055421  # kênh staff check

        # Các nhánh role
        self.ROLE_BRANCH = {
            "fe": 1136463510914727946,  # role FE
            "1st": 1143466367916449914, # role 1st
            "2nd": 1143466527803322388, # role 1st
            "3rd": 1143495816561037412, # role 1st
            "jins": 1155132633328652310, # role 1st
            "ins": 1124907485648650282, # role 1st
        }

    def has_permission(self, member: discord.Member):
        return any(role.id in self.ALLOWED_ROLES for role in member.roles)

    @commands.group(invoke_without_command=True)
    async def giverole(self, ctx):
        await ctx.reply("Dùng: !giverole <fe/1st/2nd/3rd> @user")

    async def give_and_log(self, ctx, member: discord.Member, branch: str):
        if not self.has_permission(ctx.author):
            return await ctx.reply("Bạn không có quyền dùng lệnh này.")

        role_id = self.ROLE_BRANCH[branch]
        role = ctx.guild.get_role(role_id)

        if not role:
            return await ctx.reply("Không tìm thấy role.")

        # ===== LOGIC THAY ROLE JINS -> INS =====
        removed_jins = False

        if branch == "ins":
            jins_role_id = self.ROLE_BRANCH.get("jins")
            jins_role = ctx.guild.get_role(jins_role_id)

            if jins_role and jins_role in member.roles:
                await member.remove_roles(jins_role)
                removed_jins = True

        # Tránh add trùng
        if role in member.roles:
            return await ctx.reply("Người này đã có role rồi.")

        await member.add_roles(role)
        await ctx.reply(f"Đã cấp role {role.name} cho {member.mention}")

        # Log
        log_channel = self.bot.get_channel(self.LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(title="LOG GIVE ROLE", color=discord.Color.orange())
            embed.add_field(name="Người give", value=ctx.author.mention, inline=False)
            embed.add_field(name="Người được give", value=member.mention, inline=False)
            embed.add_field(name="Role mới", value=role.name, inline=False)

            if removed_jins:
                embed.add_field(name="Role bị thay", value="jins → ins", inline=False)

            await log_channel.send(embed=embed)

    # ====== CÁC NHÁNH ======

    @giverole.command()
    async def fe(self, ctx, member: discord.Member):
        await self.give_and_log(ctx, member, "fe")

    @giverole.command(name="1st")
    async def first(self, ctx, member: discord.Member):
        await self.give_and_log(ctx, member, "1st")

    @giverole.command(name="2nd")
    async def second(self, ctx, member: discord.Member):
        await self.give_and_log(ctx, member, "2nd")

    @giverole.command(name="3rd")
    async def third(self, ctx, member: discord.Member):
        await self.give_and_log(ctx, member, "3rd")
    
    @giverole.command(name="jins")
    async def third(self, ctx, member: discord.Member):
        await self.give_and_log(ctx, member, "jins")
    
    @giverole.command(name="ins")
    async def third(self, ctx, member: discord.Member):
        await self.give_and_log(ctx, member, "ins")

async def setup(bot):
    await bot.add_cog(GiveRole(bot))
