"""
NATGAME Help System
"""
import discord
from discord.ext import commands


class NatHelp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="nathelp", aliases=["nghelp", "gamehelp"])
    async def nathelp(self, ctx, category: str = None):
        """
        Hiển thị help cho NATGAME
        !nathelp - Tất cả commands
        !nathelp setup - Setup commands
        !nathelp economy - Economy commands
        !nathelp military - Military commands
        !nathelp war - War commands
        """

        if category is None:
            embed = discord.Embed(
                title="🎮 NATGAME - Danh sách lệnh",
                description="Game mô phỏng quốc gia trên Discord",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="📋 Setup",
                value="`!gameregister`, `!nationinfo`, `!level`, `!nathelp`",
                inline=False
            )

            embed.add_field(
                name="💰 Economy",
                value="`!recruit`, `!spectrain`",
                inline=False
            )

            embed.add_field(
                name="⚔️ Military",
                value="`!army`, `!formunit`, `!listunits`, `!disbandunit`, "
                      "`!formdefense`, `!defensestatus`, `!cleardefense`, "
                      "`!setwararmy`, `!listwarmy`, `!deletewarmy`",
                inline=False
            )

            embed.add_field(
                name="⚔️ Combat",
                value="`!war`, `!warresolve`, `!pve`",
                inline=False
            )

            embed.add_field(
                name="📊 Xếp hạng",
                value="`!nationtop`, `!richlist`, `!wartop`",
                inline=False
            )

            embed.add_field(
                name="🛒 Shop",
                value="`!shop`, `!buy`",
                inline=False
            )

            embed.set_footer(text="Dùng !nathelp <category> để xem chi tiết | VD: !nathelp military")

        elif category.lower() in ["setup", "start"]:
            embed = discord.Embed(
                title="📋 Setup Commands",
                color=discord.Color.green()
            )
            embed.add_field(
                name="!gameregister <tên_quốc_gia>",
                value="Tạo quốc gia mới\nVD: `!gamregister Vương Quốc A`",
                inline=False
            )
            embed.add_field(
                name="!nationinfo / !nation / !n",
                value="Xem thông tin quốc gia của bạn",
                inline=False
            )
            embed.add_field(
                name="!level / !lvl",
                value="Xem level, EXP và phúc lợi đã mở khóa",
                inline=False
            )
            embed.add_field(
                name="!nathelp",
                value="Hiển thị trang help này",
                inline=False
            )

        elif category.lower() in ["economy", "eco"]:
            embed = discord.Embed(
                title="💰 Economy Commands",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="!recruit / !r",
                value="Tuyển quân từ dân số\n"
                      "• Cooldown: 1 giờ\n"
                      "• Chi phí: 10 money/quân\n"
                      "• Tỷ lệ: 10% dân số",
                inline=False
            )
            embed.add_field(
                name="!spectrain <số> <navy|airforce>",
                value="Huấn luyện quân đặc biệt\n"
                      "• Cần Level 3 để mở khóa Hải quân\n"
                      "• Cần Level 5 để mở khóa Không quân\n"
                      "• Tỷ lệ thành công: 70%\n"
                      "VD: `!spectrain 50 navy`",
                inline=False
            )
            embed.add_field(
                name="Tiền và Dân",
                value="• Money tăng mỗi 10 phút (tick)\n"
                      "• Dân số tăng 1% mỗi tick\n"
                      "• Maintenance: 1 money/10 quân/tick",
                inline=False
            )

        elif category.lower() in ["military", "mil"]:
            embed = discord.Embed(
                title="⚔️ Military Commands",
                color=discord.Color.dark_red()
            )
            embed.add_field(
                name="!army / !a",
                value="Xem tổng quân lực (Lục/Hải/Không quân)",
                inline=False
            )
            embed.add_field(
                name="!formunit <tên> <tier> <số>",
                value="Tạo đơn vị quân từ quân lẻ\n"
                      "Tiers: to, tieu_doi, trung_doi, dai_doi, tieu_doan, trung_doan, lu_doan, su_doan\n"
                      "VD: `!formunit Đội1 tieu_doi 10`",
                inline=False
            )
            embed.add_field(
                name="!listunits / !u",
                value="Liệt kê tất cả đơn vị và trạng thái",
                inline=False
            )
            embed.add_field(
                name="!disbandunit <tên>",
                value="Giải tán đơn vị, trả quân về kho\n"
                      "⚠️ Chỉ giải tán được khi unit đang rảnh (idle)",
                inline=False
            )
            embed.add_field(
                name="!formdefense <unit1, unit2...>",
                value="Lập phòng tuyến từ units đang rảnh\n"
                      "VD: `!formdefense Đội1, Đội2, Đội3`",
                inline=False
            )
            embed.add_field(
                name="!defensestatus",
                value="Xem phòng tuyến hiện tại",
                inline=False
            )
            embed.add_field(
                name="!cleardefense [slot]",
                value="Xóa phòng tuyến\n"
                      "• Không có slot: Xóa tất cả\n"
                      "• Có slot: Xóa slot cụ thể",
                inline=False
            )
            embed.add_field(
                name="!setwararmy <tên>, +<số>, <unit1>, <unit2>...",
                value="Tạo tập đoàn quân để tấn công\n"
                      "• `+<số>`: Quân lẻ không thuộc unit\n"
                      "VD: `!setwararmy Đạo quân A, +100, Đội1, Đội2`",
                inline=False
            )
            embed.add_field(
                name="!listwarmy",
                value="Liệt kê các tập đoàn quân",
                inline=False
            )
            embed.add_field(
                name="!deletewarmy <tên>",
                value="Giải tán tập đoàn quân, trả units về",
                inline=False
            )

        elif category.lower() in ["war", "combat"]:
            embed = discord.Embed(
                title="⚔️ War Commands",
                color=discord.Color.red()
            )
            embed.add_field(
                name="!war @user",
                value="Tuyên chiến với người chơi khác\n"
                      "• Cần có tập đoàn quân (war army)\n"
                      "• Đối phương phải có phòng tuyến\n"
                      "VD: `!war @tên_người_chơi`",
                inline=False
            )
            embed.add_field(
                name="!warresolve",
                value="Giải quyết war đang diễn ra\n"
                      "• Chạy combat engine\n"
                      "• Phân phối phần thưởng",
                inline=False
            )
            embed.add_field(
                name="!pve",
                value="Đánh với AI\n"
                      "• Độ khó auto-detect theo quân số\n"
                      "• Easy: <100 quân | Medium: 100-500 | Hard: >500\n"
                      "• Thưởng: Money, EXP",
                inline=False
            )
            embed.add_field(
                name="!spy @user",
                value="Do thám đối phương (tốn 100 money)\n"
                      "Xem thông tin tổng quan về quân đội họ",
                inline=False
            )
            embed.add_field(
                name="Phần thưởng War",
                value="• Winner: 10% money của loser\n"
                      "• EXP cho cả 2 bên\n"
                      "• Loser bị protection 24h",
                inline=False
            )

        elif category.lower() in ["shop", "store"]:
            embed = discord.Embed(
                title="🛒 Shop Commands",
                color=discord.Color.purple()
            )
            embed.add_field(
                name="!shop",
                value="Xem danh sách items và giá",
                inline=False
            )
            embed.add_field(
                name="!buy <item> [số_lượng]",
                value="Mua item\nVD: `!buy infrastructure 2`",
                inline=False
            )
            embed.add_field(
                name="Items hiện có",
                value="• 🏗️ Infrastructure (+20% population growth) - 5000\n"
                      "• 🎓 Academy (+50% EXP gain) - 3000\n"
                      "• 🏰 Fortification (+30% defense strength) - 4000\n"
                      "• ⚡ Instant Recruit (Bỏ qua cooldown) - 1000",
                inline=False
            )

        elif category.lower() in ["top", "rank", "leaderboard"]:
            embed = discord.Embed(
                title="📊 Leaderboard Commands",
                color=discord.Color.teal()
            )
            embed.add_field(
                name="!nationtop / !top",
                value="BXH Top 10 quốc gia theo Level",
                inline=False
            )
            embed.add_field(
                name="!richlist / !rich",
                value="BXH Top 10 quốc gia giàu nhất",
                inline=False
            )
            embed.add_field(
                name="!wartop",
                value="BXH Top 10 theo số war thắng",
                inline=False
            )

        else:
            embed = discord.Embed(
                title="❌ Không tìm thấy category",
                description="Categories hợp lệ: setup, economy, military, war, shop, top",
                color=discord.Color.red()
            )

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(NatHelp(bot))
