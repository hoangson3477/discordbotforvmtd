import discord
from discord.ext import commands, tasks
from discord import app_commands

class ThongKeRoleVoice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.du_lieu = {
            897801443501821964: [
                {
                    "voice_id": 1404885090458144849,
                    "ten": "VMTD Personnel",
                    "roles": [897805862008160276]
                },
                {
                    "voice_id": 1404885203683639416,
                    "ten": "1st Tryout Brigade",
                    "roles": [1143466367916449914]
                },
                {
                    "voice_id": 1404885276605812776,
                    "ten": "2nd Phase Brigade",
                    "roles": [1143466527803322388]
                },
                {
                    "voice_id": 1404885535432114246,
                    "ten": "Trial Staff Phase",
                    "roles": [897804847120801823]
                },
                {
                    "voice_id": 1404893367296458813,
                    "ten": "Staff and Officer",
                    "roles": [
                        1113827793218838580,
                        1113827968901447722,
                        1277586026939809792,
                        1401565217087033456,
                        1406627469699580066
                    ]
                },
                {
                    "voice_id": 1405044661135081572,
                    "ten": "Official Personnel",
                    "roles": [
                        1136461324952551466,
                        1392790649488675006,
                        903826625211281418,
                        897810289234411550,
                    ]
                },
                {
                    "voice_id": 1454284986495537225,
                    "ten": "Reg 1 - 2nd Brigade",
                    "roles": [1367860982579335311]
                },
                {
                    "voice_id": 1454285052736442580,
                    "ten": "Reg 2 - 2nd Brigade",
                    "roles": [1367861271113891992]
                },
                {
                    "voice_id": 1454285128313475112,
                    "ten": "Reg 3 - 1st Brigade",
                    "roles": [1367859410390618243]
                },
                {
                    "voice_id": 1454285182633906311,
                    "ten": "Reg 4 - 1st Brigade",
                    "roles": [1367860747195125770]
                },
                {
                    "voice_id": 1466404333309526089,
                    "ten": "6th Non-reg Regiment",
                    "roles": [1464966236654796912]
                }
            ]
        }

        self.cap_nhat_tu_dong.start()

    def cog_unload(self):
        self.cap_nhat_tu_dong.cancel()

    # ================== CORE ==================

    async def cap_nhat_guild(self, guild: discord.Guild):
        if guild.id not in self.du_lieu:
            return

        for cau_hinh in self.du_lieu[guild.id]:
            kenh_voice = guild.get_channel(cau_hinh["voice_id"])
            if not kenh_voice:
                continue

            tap_member = set()

            for role_id in cau_hinh["roles"]:
                role = guild.get_role(role_id)
                if role:
                    for member in role.members:
                        tap_member.add(member.id)

            so_luong = len(tap_member)
            ten_moi = f"{cau_hinh['ten']}: {so_luong}"

            if kenh_voice.name != ten_moi:
                try:
                    await kenh_voice.edit(name=ten_moi)
                except discord.Forbidden:
                    pass

    # ================== TASK ==================

    @tasks.loop(minutes=5)
    async def cap_nhat_tu_dong(self):
        for guild in self.bot.guilds:
            await self.cap_nhat_guild(guild)

    @cap_nhat_tu_dong.before_loop
    async def truoc_khi_chay(self):
        await self.bot.wait_until_ready()

    # ================== FORCE UPDATE COMMAND ==================

    @app_commands.command(
        name="thongke_update",
        description="Ép cập nhật thống kê role ngay lập tức"
    )
    async def thongke_update(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Bạn cần quyền Administrator",
                ephemeral=True
            )
            return

        await self.cap_nhat_guild(interaction.guild)

        await interaction.response.send_message(
            "✅ Đã cập nhật toàn bộ thống kê!",
            ephemeral=True
        )

# ================== SETUP ==================

async def setup(bot: commands.Bot):
    await bot.add_cog(ThongKeRoleVoice(bot))
