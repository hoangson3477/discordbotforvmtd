import discord
from discord.ext import commands
import datetime
import gspread
import os
import json
import base64
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID", "1EghAX-JZRxFwhLBdf0Rs7g6Q7aHlphS1wRTCkSM5kAg")
WORKSHEET_NAME = "5th Inspectorate Department"
LOG_CHANNEL_ID = 1472231717925421117

def get_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    
    # Thử load từ base64 env var trước (Railway)
    creds_b64 = os.getenv('GOOGLE_SHEET_CREDENTIALS_B64')
    if creds_b64:
        try:
            creds_json = base64.b64decode(creds_b64).decode('utf-8')
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            client = gspread.authorize(creds)
            return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
        except Exception as e:
            print(f"[ChamCong] Lỗi load base64 creds: {e}")
    
    # Fallback: load từ file (local)
    creds_file = "discordbotsheets-466304-0a64625eea26.json"
    if os.path.exists(creds_file):
        creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)
    
    raise Exception("[ChamCong] Không tìm thấy Google credentials!")

class ChamCong(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sheet = get_sheet()

    # ===== tìm username viết tắt =====
    def find_user_row(self, partial):
        usernames = self.sheet.col_values(2)

        for idx, name in enumerate(usernames):
            if name and partial.lower() in str(name).lower():
                return idx + 1, name

        return None, None

    # ===== lấy cột theo thứ =====
    def get_today_column(self):
        weekday = datetime.datetime.now().weekday()

        mapping = {
            0: 7,   # Mon
            1: 8,   # Tue
            2: 9,   # Wed
            3: 10,  # Thu
            4: 11,  # Fri
            5: 12,  # Sat
            6: 13   # Sun
        }
        return mapping[weekday]

    # ===== tính lại point =====
    def calculate_points(self, row):
        total = 0
        for col in range(7, 14):
            val = self.sheet.cell(row, col).value
            if val and str(val).isdigit():
                total += int(val)
        return total

    @commands.command(name="chamcong")
    async def chamcong(self, ctx, username: str, link: str):
        row, full_name = self.find_user_row(username)

        if not row:
            return await ctx.reply("❌ Không tìm thấy username.")

        # ===== check supervision =====
        sup1 = self.sheet.cell(row, 5).value
        sup2 = self.sheet.cell(row, 6).value

        if not sup1 and not sup2:
            return await ctx.reply("❌ Người này chưa có Supervision, không thể chấm công.")

        col = self.get_today_column()

        # ===== tăng số lần chấm công hôm nay =====
        current_val = self.sheet.cell(row, col).value

        if current_val and str(current_val).isdigit():
            new_val = int(current_val) + 1
        else:
            new_val = 1

        self.sheet.update_cell(row, col, new_val)

        # ===== cập nhật POINT = tổng 7 ngày =====
        total_points = self.calculate_points(row)
        self.sheet.update_cell(row, 14, total_points)

        # ===== log discord =====
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)

        embed = discord.Embed(
            title="📋 Chấm công 5th Department",
            color=0x2ecc71
        )
        embed.add_field(name="Username", value=full_name, inline=False)
        embed.add_field(name="Số lần hôm nay", value=str(new_val))
        embed.add_field(name="Tổng 7 ngày", value=str(total_points))
        embed.add_field(name="Link", value=link, inline=False)
        embed.add_field(name="Người chấm", value=ctx.author.mention)

        await log_channel.send(embed=embed)
        await ctx.reply("✅ Đã chấm công.")
        
async def setup(bot):
    await bot.add_cog(ChamCong(bot))
