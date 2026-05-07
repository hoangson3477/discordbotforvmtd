import discord
from discord.ext import commands
import gspread
import os
import json
import base64
from datetime import datetime, timezone, timedelta
import asyncio
import logging
from . import __utils 
from dotenv import load_dotenv
from supabase import create_client
import time

from config import SupabaseConfig, GoogleSheetsConfig, logger
from sheets_optimization import OptimizedSheetsClient
from addpoint_optimization import OptimizedAddPointCommand

log = logging.getLogger(__name__)

# Environment variables
GOOGLE_SHEET_ID = GoogleSheetsConfig.SHEET_ID
GOOGLE_SHEET_CREDENTIALS_FILE = GoogleSheetsConfig.CREDENTIALS_FILE
GOOGLE_SHEET_CREDENTIALS_B64 = GoogleSheetsConfig.CREDENTIALS_B64

# Initialize Supabase client
supabase = SupabaseConfig.validate_main()

# --- CẤU HÌNH ROLE ID ---
ROLE_ID_ADD_POINT = 1126751064377544704
ROLE_ID_END_QUOTA = 897810289234411550

POINT_RECORD_SHEET = "Point Record"
POINT_RECORD_USERNAME_COL = 2  # C
POINT_RECORD_TOP_COL = 1       # B
POINT_RECORD_POINT_COL = 6     # G
START_ROW = 8                 # nếu hàng 1 là header
HEADER_ROW_INDEX = 7      # hàng 8
DATA_START_INDEX = 8      # hàng 9
SHEET_CACHE_TTL = 60      # giây

# Các cột hệ thống không bị reset khi end quota
SYSTEM_COLS = {
    'USERNAME',
    'DEPARTMENT RANK',
    'REGIMENT RANK',
    'DEPENDENT UNIT',
    'POINT',
    'QUOTA PROGRESS?',
    'INACTIVE REQUESTED?'
}


# FIX #8: Xóa khai báo trùng lặp ở dưới (đã có ở trên)

def load_google_credentials():
    """Load credentials từ file hoặc base64 env var"""
    # Cách 1: File path (local dev)
    creds_file = os.getenv('GOOGLE_SHEET_CREDENTIALS_FILE')
    if creds_file and os.path.exists(creds_file):
        return creds_file, None
    
    # Cách 2: Base64 encoded JSON (Railway deploy)
    creds_b64 = os.getenv('GOOGLE_SHEET_CREDENTIALS_B64')
    if creds_b64:
        try:
            creds_json = base64.b64decode(creds_b64).decode('utf-8')
            creds_dict = json.loads(creds_json)
            return None, creds_dict
        except Exception as e:
            log.error(f"[GSheets] Lỗi decode base64 credentials: {e}")
            return None, None
    
    return None, None

gc = None
if GOOGLE_SHEET_ID:
    creds_file, creds_dict = load_google_credentials()
    
    if creds_file:
        try:
            gc = gspread.service_account(filename=creds_file)
            log.info(f"[GSheets Cog] Đã kết nối với Google Sheets API (file).")
        except Exception as e:
            log.error(f"[GSheets] Lỗi kết nối qua file: {e}")
    
    # Nếu gc vẫn None và có creds_dict, thử cách 2
    if gc is None and creds_dict:
        try:
            from google.oauth2.service_account import Credentials
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            gc = gspread.Client(auth=credentials)
            log.info("[GSheets Cog] Đã kết nối với Google Sheets API (env var).")
        except Exception as e:
            log.error(f"[GSheets] Lỗi kết nối qua env var: {e}")
    else:
        log.warning("[GSheets] Không tìm thấy credentials (cần GOOGLE_SHEET_CREDENTIALS_FILE hoặc GOOGLE_SHEET_CREDENTIALS_B64)")

# --- Định nghĩa các bí danh cho tên trang tính ---
# FIX #11: Lowercase toàn bộ key để lookup nhất quán (sheet_name.lower() sẽ luôn khớp)
SHEET_ALIASES = {
    "1st": "1st Tryout Brigade",
    "2nd": "2nd Phase Brigade",
    "3rd": "3rd Reserved Regiment",
    "4th": "4th Research and Development Department",
    "5th": "5th Inspectorate Department",
    "6th": "6th Non-regiment Regiment",
    "hicom": "VMTD Hicom",
}

# --- Danh sách các trang tính regiment mà bot sẽ tìm kiếm ---
REGIMENT_SHEETS_TO_SEARCH = list(SHEET_ALIASES.values())

# Helper function to find full username based on partial input
def _find_full_username_by_partial(
    partial_username: str,
    sheet_data: list,
    username_col_idx: int,
    data_start_row_idx: int = 8  # index 8 = hàng 9
):
    """
    Tìm username trong sheet_data dựa trên partial input.
    - Ưu tiên exact match
    - Sau đó prefix match
    Trả về:
        (full_username, status, row_index)
    """

    if not partial_username:
        return None, "no_match", -1

    partial = partial_username.strip().lower()

    exact_matches = []
    prefix_matches = []

    # Duyệt từ hàng dữ liệu (row 9)
    for r_idx in range(data_start_row_idx, len(sheet_data)):
        row = sheet_data[r_idx]

        # Row ngắn hơn cột USERNAME → skip
        if len(row) <= username_col_idx:
            continue

        cell_value = row[username_col_idx]
        if not cell_value:
            continue

        full_username = cell_value.strip()
        full_lower = full_username.lower()

        if full_lower == partial:
            exact_matches.append((full_username, r_idx))
        elif full_lower.startswith(partial):
            prefix_matches.append((full_username, r_idx))

    # Exact match
    if len(exact_matches) == 1:
        return exact_matches[0][0], "exact_match", exact_matches[0][1]

    if len(exact_matches) > 1:
        return [u for u, _ in exact_matches], "multiple_matches", -1

    # Prefix match
    if len(prefix_matches) == 1:
        return prefix_matches[0][0], "single_prefix_match", prefix_matches[0][1]

    if len(prefix_matches) > 1:
        return [u for u, _ in prefix_matches], "multiple_matches", -1

    # Không tìm thấy
    return None, "no_match", -1

def log_addpoint_audit(
    discord_user,
    roblox_username,
    sheet_name,
    event_type,
    added_points,
    before_points,
    after_points,
    before_quota,
    quota_status
):
    try:
        supabase.table("addpoint_audit_logs").insert({
            "discord_user_id": str(discord_user.id),
            "discord_username": discord_user.name,

            "roblox_username": roblox_username,
            "sheet_name": sheet_name,

            "event_type": event_type,
            "added_points": added_points,

            "before_points": before_points,
            "after_points": after_points,

            "before_quota": before_quota,
            "quota_status_after": quota_status
        }).execute()
    except Exception as e:
        log.error(f"[AUDIT LOG] Lỗi ghi audit: {e}")

async def log_addpoint_audit_async(**kwargs):
    """Wrapper async để không block event loop khi ghi Supabase."""
    await asyncio.to_thread(log_addpoint_audit, **kwargs)

def fetch_addpoint_audit_logs(
    limit=10,
    discord_user_id=None,
    roblox_username=None
):
    try:
        query = (
            supabase
            .table("addpoint_audit_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        )

        if discord_user_id:
            query = query.eq("discord_user_id", str(discord_user_id))

        if roblox_username:
            query = query.ilike("roblox_username", roblox_username)

        res = query.execute()
        return res.data if res.data else []
    except Exception as e:
        log.error(f"[AUDIT LOG] Lỗi khi truy vấn audit logs: {e}")
        return []

class GoogleSheets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.column_map = None 
        self.sheet_cache = {}
        self.username_index = {}
        
        # Initialize optimized client
        self.optimized_client = None
        
        # FIX #3: gc có thể là None nếu credentials lỗi — không gọi trực tiếp trong __init__
        self.spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID) if gc else None
        
        # --- CACHE ---
        self.sheet_data_cache = None 
        self.cache_lock = asyncio.Lock()
        self.last_cache_refresh = None
        self.cache_duration = timedelta(minutes=5)
        
        # --- LOGGING IN MEMORY ---
        self.log_channel_id = None # Lưu ID kênh log vào RAM

        self.bot.loop.create_task(self._initialize_cog())

    async def _initialize_cog(self):
        log.info("[GSheets Cog] Đang chờ bot sẵn sàng để tạo bản đồ cột...")
        await self.bot.wait_until_ready()
        await asyncio.sleep(5) 
        await self._create_column_map()
        await self._load_or_get_cache(force_refresh=True)
        
        # Initialize optimized client after spreadsheet is ready
        if self.spreadsheet:
            self.optimized_client = OptimizedSheetsClient(
                self.spreadsheet,
                cache_ttl=300,  # 5 minutes cache
                batch_size=100   # Batch 100 updates
            )
            log.info("[GSheets Cog] Đã khởi tạo optimized client")
        else:
            log.warning("[GSheets Cog] Không thể khởi tạo optimized client - spreadsheet chưa sẵn sàng")

    async def _create_column_map(self):
        if not gc:
            log.error("[Column Map] Không thể tạo bản đồ cột vì chưa kết nối Google Sheets.")
            return

        try:
            log.info("[Column Map] Bắt đầu tạo bản đồ cột từ Google Sheet...")
            sh = gc.open_by_key(GOOGLE_SHEET_ID)
            worksheet = sh.worksheet(REGIMENT_SHEETS_TO_SEARCH[0])
            header_row = worksheet.get_all_values()[7]  # hàng 8, đủ cột
            self.column_map = {
                header.upper().strip(): idx
                for idx, header in enumerate(header_row)
                if header and header.strip()
            }
            log.info(f"[Column Map] Tạo bản đồ cột thành công với {len(self.column_map)} cột.")

            required_cols = ['USERNAME', 'DEPARTMENT RANK', 'POINT', 'QUOTA PROGRESS?']
            for col in required_cols:
                if col not in self.column_map:
                    log.critical(f"[Column Map] Cảnh báo nghiêm trọng: Không tìm thấy cột '{col}' trong Google Sheet!")

        except Exception as e:
            log.error(f"[Column Map] Lỗi khi tạo bản đồ cột: {e}", exc_info=True)
            self.column_map = None

    async def _load_or_get_cache(self, force_refresh=False):
        async with self.cache_lock:
            now = datetime.now()
            # FIX #2: Kiểm tra last_cache_refresh is None riêng để tránh TypeError khi trừ None với datetime
            should_refresh = (
                force_refresh
                or not self.sheet_data_cache
                or self.last_cache_refresh is None
                or (now - self.last_cache_refresh) > self.cache_duration
            )

            if not should_refresh:
                return self.sheet_data_cache

            log.info("[Cache] Bắt đầu làm mới cache dữ liệu từ Google Sheets...")
            if not gc:
                return None

            try:
                sh = gc.open_by_key(GOOGLE_SHEET_ID)
                new_cache = {}
                for sheet_name in REGIMENT_SHEETS_TO_SEARCH:
                    worksheet = sh.worksheet(sheet_name)
                    all_data = worksheet.get_all_values()
                    new_cache[sheet_name] = all_data
                
                self.sheet_data_cache = new_cache
                self.last_cache_refresh = now
                log.info(f"[Cache] Làm mới cache thành công.")
                return self.sheet_data_cache
            except Exception as e:
                log.error(f"[Cache] Lỗi nghiêm trọng khi làm mới cache: {e}", exc_info=True)
                return None

    # --- NEW: Hàm kiểm tra Role Discord ---
    def _check_discord_role(self, user, required_role_id):
        """Kiểm tra xem user có Role ID yêu cầu hay không."""
        if not isinstance(user, discord.Member):
            # Nếu lệnh dùng trong DM, không check được Role
            return False
        
        # Kiểm tra nếu user có role ID trùng khớp
        return any(role.id == required_role_id for role in user.roles)
    
    def update_point_record(self, username: str, added_points: float):
        # FIX #9: Hàm này là blocking I/O — nên gọi qua update_point_record_async
        if not gc:
            return
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        ws = sh.worksheet(POINT_RECORD_SHEET)
        rows = ws.get_all_values()

        user_row = None
        for i in range(START_ROW-1, len(rows)):
            if len(rows[i]) > POINT_RECORD_USERNAME_COL and rows[i][POINT_RECORD_USERNAME_COL].strip().lower() == username.lower():
                user_row = i
                break

        if user_row is not None:
            current = float(rows[user_row][POINT_RECORD_POINT_COL] or 0)
            ws.update_cell(user_row+1, POINT_RECORD_POINT_COL+1, current + added_points)
        else:
            ws.append_row(["", "", username, "", "", "", added_points])

        self._resort_point_record(ws)

    async def update_point_record_async(self, username: str, added_points: float):
        """Wrapper async để không block event loop khi cập nhật Point Record sheet."""
        await asyncio.to_thread(self.update_point_record, username, added_points)

    def _resort_point_record(self, ws):
        rows = ws.get_all_values()[START_ROW-1:]
    
        parsed = []
        for r in rows:
            try:
                parsed.append((r, float(r[POINT_RECORD_POINT_COL])))
            except:
                parsed.append((r, 0))

        parsed.sort(key=lambda x: x[1], reverse=True)

        updates = []
        last_point = None
        rank = 0
        display_rank = 0

        for idx, (row, point) in enumerate(parsed):
            rank += 1
            if point != last_point:
                display_rank = rank

            # FIX #7: Tạo bản sao để không mutate list gốc từ get_all_values()

    async def get_sheet_cached_async(self, sheet_name: str):
        """Get sheet data using optimized client"""
        if not self.optimized_client:
            return []
        return await self.optimized_client.get_sheet_data(sheet_name)

    def resolve_user_row(self, sheet_name, partial_username):
        index = self.username_index.get(sheet_name, {})
        partial = partial_username.lower()

        # exact match trước
        if partial in index:
            return index[partial]

        # prefix fallback (scan rất ít)
        matches = [
            r for u, r in index.items()
            if u.startswith(partial)
        ]

        if len(matches) == 1:
            return matches[0]

        return None

    def _calculate_quota_status(self, total_points: float, department_rank: str) -> str:
        """
        Xác định trạng thái quota dựa trên tổng điểm và Department Rank
        """

        try:
            total_points = float(total_points)
        except (TypeError, ValueError):
            return "UNKNOWN"

        if not department_rank:
            return "UNKNOWN"

        rank = department_rank.strip().lower()

        # --- Junior Directing Staff ---
        if rank == "junior directing staff":
            if total_points > 20:
                return "Awaiting Promote"
            elif total_points >= 4:
                return "Completed"
            elif total_points > 0:
                return "Half-completed"
            else:
                return "Didn't Completed"

        # --- Higher Directing Staff ---
        if rank in {
            "directing staff",
            "senior directing staff",
            "head directing staff"
        }:
            if total_points > 30:
                return "Awaiting Promote"
            elif total_points >= 4:
                return "Completed"
            elif total_points > 0:
                return "Half-completed"
            else:
                return "Didn't Completed"

        # --- Fallback ---
        if total_points >= 4:
            return "Completed"
        elif total_points > 0:
            return "Half-completed"

        return "Didn't Completed"

    def _get_promotion_target(self, department_rank: str) -> float | None:
        if not department_rank:
            return None

        rank = department_rank.lower().strip()

        if rank == "junior directing staff":
            return 20

        if rank in [
            "directing staff",
            "senior directing staff",
            "head directing staff"
        ]:
            return 30

        return None

    def _make_progress_bar_emoji(self, current: float, target: float, length: int = 10) -> str:
        if not target or target <= 0:
            return "N/A"

        try:
            current = float(current)
        except:
            current = 0.0

        # ĐỦ ĐIỂM → FULL BAR + THÔNG BÁO
        if current >= target:
            bar = "🟩" * length
            return (
                f"{bar}\n"
                f"`{current:.1f}/{target}` • 🎉 **Awaiting Promote**"
            )

        # CHƯA ĐỦ → BAR THƯỜNG
        ratio = max(0, current / target)
        filled = int(ratio * length)
        empty = length - filled

        bar = "🟩" * filled + "⬜" * empty
        remaining = target - current

        return (
            f"{bar}\n"
            f"`{current:.1f}/{target}` • Còn thiếu: `{remaining:.1f}`"
        )

    @commands.command(name="addpoint")
    async def add_point_command(self, ctx, raw_roblox_usernames, event_type, points):
        """Optimized addpoint command with smart batching"""
        log.info(f"[AddPoint] Processing command from {ctx.author.name}: {raw_roblox_usernames} {event_type} {points}")
        
        # Use optimized processor
        if hasattr(self, 'optimized_addpoint'):
            processor = self.optimized_addpoint
        else:
            processor = OptimizedAddPointCommand(self)
            self.optimized_addpoint = processor
        
        await processor.execute(ctx, raw_roblox_usernames, event_type, points)

    # --- Slash Command /addpoint ---
    @discord.app_commands.command(name="addpoint", description="Thêm điểm và cập nhật số lần tham gia cho người dùng Roblox.")
    @discord.app_commands.describe(
        roblox_usernames="Username Roblox (ghi tắt được), cách nhau bởi dấu phẩy",
        event_type="Loại sự kiện (BT, CO-HOST, PHASE, TRYOUT, SUPERVISION, PT, CT, SPECIAL EVENTS, INSPECTION, PATROL, INACTIVE, REQUESTED)",
        points="Số điểm muốn thêm (tối đa 15)"
    )
    async def slash_add_point_command(self, interaction: discord.Interaction, roblox_usernames: str, event_type: str, points: float):
        """Optimized slash addpoint command"""
        log.info(f"[AddPoint] Processing slash from {interaction.user.name}: {roblox_usernames} {event_type} {points}")
        
        # Use optimized processor
        if hasattr(self, 'optimized_addpoint'):
            processor = self.optimized_addpoint
        else:
            processor = OptimizedAddPointCommand(self)
            self.optimized_addpoint = processor
        
        await processor.execute(interaction, roblox_usernames, event_type, points)

    async def _handle_add_point_logic(
        self,
        ctx,
        raw_usernames: str,
        event_type: str,
        added_points: float
    ):
        # FIX #5: Xác định send_func đồng nhất cho cả prefix command và slash interaction
        is_interaction = isinstance(ctx, discord.Interaction)
        send_func = ctx.followup.send if is_interaction else ctx.send

        # ===== PARSE INPUT =====
        usernames = [u.strip() for u in raw_usernames.split(",") if u.strip()]
        if not usernames:
            return await send_func("❌ Danh sách user rỗng.")

        if self.column_map is None:
            return await send_func("❌ Bot chưa tải xong column map, vui lòng thử lại sau.")

        event_key = event_type.upper()
        event_col_idx = self.column_map.get(event_key)
        if event_col_idx is None:
            return await send_func("❌ Event không hợp lệ (không tìm thấy cột).")

        username_col_idx = self.column_map["USERNAME"]
        point_col_idx = self.column_map["POINT"]
        quota_col_idx = self.column_map["QUOTA PROGRESS?"]
        rank_col_idx = self.column_map["DEPARTMENT RANK"]

        updates_by_sheet = {}   # sheet_name -> list[batch updates]
        audit_logs = []
        not_found = []

        author = ctx.author if hasattr(ctx, "author") else ctx.user

        # ===== PROCESS EACH USER =====
        # FIX: Pre-fetch tất cả sheets song song thay vì fetch tuần tự trong vòng lặp
        sheet_names = list(SHEET_ALIASES.values())
        fetched_sheets = await asyncio.gather(*[
            self.get_sheet_cached_async(s) for s in sheet_names
        ])
        all_sheets_map = dict(zip(sheet_names, fetched_sheets))

        for partial_username in usernames:
            found = False

            for sheet_name in sheet_names:
                sheet_data = all_sheets_map[sheet_name]

                full_username, status, row_idx = _find_full_username_by_partial(
                    partial_username=partial_username,
                    sheet_data=sheet_data,
                    username_col_idx=username_col_idx,
                    data_start_row_idx=DATA_START_INDEX
                )

                if status == "no_match":
                    continue

                if status == "multiple_matches":
                    return await send_func(
                        f"⚠️ `{partial_username}` khớp nhiều user ở `{sheet_name}`:\n"
                        f"{', '.join(full_username)}"
                    )

                # ===== FOUND USER =====
                found = True
                row = sheet_data[row_idx]
                department_rank = row[rank_col_idx]
                before_quota_status = row[quota_col_idx] if len(row) > quota_col_idx else ""

                # --- POINT ---
                try:
                    current_points = float(row[point_col_idx] or 0)
                except ValueError:
                    current_points = 0.0

                new_points = current_points + added_points

                # --- EVENT COUNT ---
                try:
                    current_event_count = int(row[event_col_idx] or 0)
                except ValueError:
                    current_event_count = 0

                new_event_count = current_event_count + 1

                # --- QUOTA ---
                new_quota_status = self._calculate_quota_status(new_points, department_rank)

                # --- BUILD BATCH UPDATE ---
                updates_by_sheet.setdefault(sheet_name, []).extend([
                    {
                        "range": gspread.utils.rowcol_to_a1(row_idx + 1, point_col_idx + 1),
                        "values": [[str(new_points)]]
                    },
                    {
                        "range": gspread.utils.rowcol_to_a1(row_idx + 1, event_col_idx + 1),
                        "values": [[str(new_event_count)]]
                    },
                    {
                        "range": gspread.utils.rowcol_to_a1(row_idx + 1, quota_col_idx + 1),
                        "values": [[new_quota_status]]
                    }
                ])

                # --- AUDIT LOG ---
                audit_logs.append({
                    "discord_user": author,
                    "roblox_username": full_username,
                    "sheet_name": sheet_name,
                    "event_type": event_type,
                    "added_points": added_points,
                    "before_points": current_points,
                    "after_points": new_points,
                    "before_quota": before_quota_status,
                    "quota_status": new_quota_status
                })

                break  # đã tìm thấy user → không scan sheet khác

            if not found:
                not_found.append(partial_username)

        # ===== WRITE: 1 BATCH / SHEET =====
        if self.spreadsheet:
            for sheet_name, updates in updates_by_sheet.items():
                worksheet = self.spreadsheet.worksheet(sheet_name)
                worksheet.batch_update(updates)

                # invalidate cache
                self.sheet_cache.pop(sheet_name, None)
                self.username_index.pop(sheet_name, None)

        # ===== SAVE AUDIT =====
        # FIX: Dùng async version để không block event loop khi ghi Supabase
        for audit_entry in audit_logs:
            await log_addpoint_audit_async(**audit_entry)

        # ===== RESPONSE (EMBED) =====
        author = ctx.author if hasattr(ctx, "author") else ctx.user

        embed = discord.Embed(
            title="Kết quả thêm điểm",
            color=discord.Color.green()
        )

        embed.description = (
            f"**Sự kiện:** `{event_type}` | "
            f"**Số Point được thêm:** `{added_points}`\n"
        )

        lines = []
        # FIX #6: Đổi tên biến từ 'log' → 'audit_entry' để không shadow module logger
        for audit_entry in audit_logs:
            before_quota = audit_entry.get("before_quota") or "Didn't Completed"
            lines.append(
                f"**{audit_entry['roblox_username']}**: "
                f"{audit_entry['before_points']:g} → {audit_entry['after_points']:g}; "
                f"Quota: {before_quota} → {audit_entry['quota_status']}"
            )

        if lines:
            embed.add_field(
                name="Kết quả",
                value="\n".join(lines),
                inline=False
            )

        if not_found:
            embed.add_field(
                name="⚠️ Không tìm thấy",
                value=", ".join(not_found),
                inline=False
            )

        embed.set_footer(
            text=f"Addpoint bởi {author.display_name}"
        )

        # FIX: Dùng send_func thống nhất thay vì ctx.send (crash nếu là slash command)
        await send_func(embed=embed)

    # --- Lệnh Prefix !endquota ---
    @commands.command(name='endquota')
    async def end_quota_command(self, ctx):
        log.info(f"Nhận lệnh !endquota từ {ctx.author.name}")

        # Check Role ID cho Endquota
        if not self._check_discord_role(ctx.author, ROLE_ID_END_QUOTA):
            await ctx.send(embed=discord.Embed(title="❌ Lỗi Quyền", description=f"Bạn cần có Role <@&{ROLE_ID_END_QUOTA}> để sử dụng lệnh này.", color=discord.Color.red()))
            return

        await self._handle_end_quota_logic(ctx)

    # --- Slash Command /endquota ---
    @discord.app_commands.command(name="endquota", description="Thống kê điểm tuần và reset điểm cho quota mới.")
    async def slash_end_quota_command(self, interaction: discord.Interaction):
        log.info(f"Nhận slash command /endquota từ {interaction.user.name}")
        await interaction.response.defer(ephemeral=False) 

        # Check Role ID cho Endquota
        if not self._check_discord_role(interaction.user, ROLE_ID_END_QUOTA):
             await interaction.followup.send(embed=discord.Embed(title="❌ Lỗi Quyền", description=f"Bạn cần có Role <@&{ROLE_ID_END_QUOTA}> để sử dụng lệnh này.", color=discord.Color.red()))
             return
        
        await self._handle_end_quota_logic(interaction)

    async def _handle_end_quota_logic(self, ctx_or_interaction):
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        send_func = ctx_or_interaction.send if not is_interaction else ctx_or_interaction.followup.send
        author = ctx_or_interaction.author if not is_interaction else ctx_or_interaction.user 

        if not self.spreadsheet or self.column_map is None:
            return await send_func("❌ Bot chưa sẵn sàng hoặc chưa kết nối Google Sheets.")

        processing_msg = await send_func("⏳ Đang xử lý end quota...")

        # FIX: Dùng self.spreadsheet thay vì mở kết nối mới mỗi lần
        sh = self.spreadsheet
        all_players_total_points = []

        try:
            # ========= 1. THU THẬP ĐIỂM (non-blocking) =========
            # FIX: Wrap toàn bộ blocking I/O trong asyncio.to_thread
            def _fetch_all_sheets_data():
                result = {}
                for sname in REGIMENT_SHEETS_TO_SEARCH:
                    ws = sh.worksheet(sname)
                    result[sname] = ws.get_all_values()
                return result

            all_sheets_raw = await asyncio.to_thread(_fetch_all_sheets_data)

            username_col = self.column_map['USERNAME']
            points_col = self.column_map['POINT']

            for sheet_name, all_data in all_sheets_raw.items():
                if len(all_data) <= HEADER_ROW_INDEX:
                    continue
                for r_idx in range(DATA_START_INDEX, len(all_data)):
                    row = all_data[r_idx]
                    if len(row) <= username_col:
                        continue
                    username = row[username_col].strip()
                    if not username:
                        continue
                    points = 0.0
                    if len(row) > points_col:
                        try:
                            points = float(row[points_col] or 0)
                        except (ValueError, TypeError):
                            pass
                    if points > 0:
                        all_players_total_points.append({
                            "username": username,
                            "points": points,
                            "sheet": sheet_name
                        })

            all_players_total_points.sort(key=lambda x: x["points"], reverse=True)

            # ========= 2. BÁO CÁO =========
            report_lines = ["📊 **BÁO CÁO KẾT THÚC QUOTA**\n"]

            if all_players_total_points:
                for rank, p in enumerate(all_players_total_points, start=1):
                    report_lines.append(
                        f"{rank}. `{p['username']}` – `{p['points']}` điểm ({p['sheet']})"
                    )
            else:
                report_lines.append("Không có ai có điểm trong quota này.")

            report_text = "\n".join(report_lines)

            await processing_msg.delete()
            for i in range(0, len(report_text), 2000):
                await send_func(report_text[i:i+2000])

            # ========= 3. RESET DỮ LIỆU (non-blocking) =========
            point_col = self.column_map['POINT']
            quota_col = self.column_map['QUOTA PROGRESS?']
            username_col_idx = self.column_map['USERNAME']

            def _build_and_apply_resets():
                reset_logs = []
                for sheet_name, all_data in all_sheets_raw.items():
                    if len(all_data) <= HEADER_ROW_INDEX:
                        reset_logs.append(f"⚠️ `{sheet_name}`: Không có dữ liệu.")
                        continue

                    headers = all_data[HEADER_ROW_INDEX]
                    event_cols = [
                        idx for idx, h in enumerate(headers)
                        if h and h.strip().upper() not in SYSTEM_COLS
                    ]

                    updates = []
                    for r_idx in range(DATA_START_INDEX, len(all_data)):
                        row = all_data[r_idx]
                        if len(row) <= username_col_idx or not row[username_col_idx].strip():
                            continue

                        if len(row) > point_col:
                            updates.append({
                                "range": gspread.utils.rowcol_to_a1(r_idx+1, point_col+1),
                                "values": [["0"]]
                            })
                        for c in event_cols:
                            if len(row) > c:
                                updates.append({
                                    "range": gspread.utils.rowcol_to_a1(r_idx+1, c+1),
                                    "values": [[""]]
                                })
                        if len(row) > quota_col:
                            updates.append({
                                "range": gspread.utils.rowcol_to_a1(r_idx+1, quota_col+1),
                                "values": [["Didn't Completed"]]
                            })

                    if updates:
                        worksheet = sh.worksheet(sheet_name)
                        worksheet.batch_update(updates)
                        reset_logs.append(f"✅ `{sheet_name}`: Đã reset.")
                    else:
                        reset_logs.append(f"⚠️ `{sheet_name}`: Không có gì để reset.")
                return reset_logs

            reset_logs = await asyncio.to_thread(_build_and_apply_resets)

            # ========= 4. CLEAR CACHE =========
            self.sheet_data_cache = None
            self.last_cache_refresh = None

            await send_func(
                embed=discord.Embed(
                    title="✅ End Quota Hoàn Tất",
                    description="\n".join(reset_logs),
                    color=discord.Color.green()
                ).set_footer(text=f"Thực hiện bởi {author.name}")
            )

        except Exception as e:
            await processing_msg.delete()
            await send_func(f"❌ Lỗi khi end quota: `{e}`")

    # --- Lệnh Prefix !checkpoint --- 
    @commands.command(name='checkpoint')
    async def check_point_command(self, ctx, roblox_username: str, sheet_name: str = None):
        # Không giới hạn Role
        await self._handle_check_point_logic(ctx, sheet_name, roblox_username)

    # --- Slash Command /checkpoint --- 
    @discord.app_commands.command(name="checkpoint", description="Kiểm tra điểm và số lần tham gia của người dùng Roblox.")
    @discord.app_commands.describe(roblox_username="Username Roblox", sheet_name="Tên trang tính (1st, 2nd,...)")
    async def slash_check_point_command(self, interaction: discord.Interaction, roblox_username: str, sheet_name: str = None):
        await interaction.response.defer(ephemeral=False)
        await self._handle_check_point_logic(interaction, sheet_name, roblox_username)

    async def _handle_check_point_logic(self, ctx_or_interaction, sheet_name: str | None, roblox_username: str):
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        send_func = ctx_or_interaction.send if not is_interaction else ctx_or_interaction.followup.send
        author = ctx_or_interaction.author if not is_interaction else ctx_or_interaction.user 

        all_sheets_data = await self._load_or_get_cache()
        if not all_sheets_data or self.column_map is None:
            return await send_func(embed=discord.Embed(
                title="❌ Lỗi Bot",
                description="Dữ liệu chưa tải.",
                color=discord.Color.red()
            ))

        username_col_index = self.column_map['USERNAME']
        points_col_index = self.column_map['POINT']
        quota_status_col_index = self.column_map['QUOTA PROGRESS?']

        found_sheet_name = None
        user_row_index = -1
        full_username = None
        sheet_data = None

        # =============================
        # CASE 1: Có chỉ định sheet
        # =============================
        if sheet_name:
            normalized_sheet_name = SHEET_ALIASES.get(sheet_name.lower(), sheet_name)
            sheet_data = all_sheets_data.get(normalized_sheet_name)

            if not sheet_data:
                return await send_func(embed=discord.Embed(
                    title="❌ Lỗi Trang Tính",
                    description=f"Không tìm thấy trang `{normalized_sheet_name}`.",
                    color=discord.Color.red()
                ))

            full_username, status, row_idx = _find_full_username_by_partial(
                roblox_username,
                sheet_data,
                username_col_index,
                DATA_START_INDEX
            )

            if status == "no_match":
                return await send_func(embed=discord.Embed(
                    title="⚠️ Không Tìm Thấy",
                    description=f"Không tìm thấy `{roblox_username}` trong `{normalized_sheet_name}`.",
                    color=discord.Color.orange()
                ))

            if status == "multiple_matches":
                return await send_func(embed=discord.Embed(
                    title="⚠️ Trùng Kết Quả",
                    description=f"Có nhiều username khớp với `{roblox_username}` trong `{normalized_sheet_name}`.",
                    color=discord.Color.orange()
                ))

            found_sheet_name = normalized_sheet_name
            user_row_index = row_idx

        # =============================
        # CASE 2: Không chỉ định sheet → scan toàn bộ
        # =============================
        else:
            for s_name, s_data in all_sheets_data.items():
                full_username, status, row_idx = _find_full_username_by_partial(
                    roblox_username,
                    s_data,
                    username_col_index,
                    DATA_START_INDEX
                )

                if status in ("exact_match", "single_prefix_match"):
                    found_sheet_name = s_name
                    sheet_data = s_data
                    user_row_index = row_idx
                    break

            if user_row_index == -1:
                return await send_func(embed=discord.Embed(
                    title="⚠️ Không Tìm Thấy",
                    description=f"Không tìm thấy username gần giống `{roblox_username}` ở bất kỳ sheet nào.",
                    color=discord.Color.orange()
                ))

        # =============================
        # Lấy dữ liệu user
        # =============================
        user_row_data = sheet_data[user_row_index]
        headers = sheet_data[7]

        event_data = {}
        for i, header_name in enumerate(headers):
            # Dùng module-level SYSTEM_COLS thay vì định nghĩa lại
            if not header_name or header_name.upper() in SYSTEM_COLS:
                continue

            event_count = 0
            if len(user_row_data) > i:
                try:
                    event_count = int(user_row_data[i] or 0)
                except (ValueError, TypeError):
                    pass

            if event_count > 0:
                event_data[header_name.strip()] = event_count

        # Points
        total_points = 0.0
        if len(user_row_data) > points_col_index:
            try:
                total_points = float(user_row_data[points_col_index] or 0.0)
            except:
                pass

        rank_col_idx = self.column_map['DEPARTMENT RANK']
        department_rank = ""

        if len(user_row_data) > rank_col_idx:
            department_rank = user_row_data[rank_col_idx]

        target = self._get_promotion_target(department_rank)

        progress_text = "Không áp dụng"
        if target:
            progress_text = self._make_progress_bar_emoji(total_points, target)
        
        # Quota
        quota_status = "N/A"
        if len(user_row_data) > quota_status_col_index:
            quota_status = user_row_data[quota_status_col_index].strip()

        # =============================
        # EMBED
        # =============================
        embed = discord.Embed(
            title=f"Thông tin `{full_username}`",
            description=f"Nguồn: `{found_sheet_name}`",
            color=discord.Color.blue()
        )

        embed.add_field(name="Tổng Điểm", value=f"**`{total_points}`**", inline=False)
        embed.add_field(name="Quota Status", value=f"**`{quota_status}`**", inline=False)

        if target:
            embed.add_field(
                name="Tiến độ thăng cấp",
                value=f"Rank: `{department_rank}`\n{progress_text}",
                inline=False
            )

        events_str = "\n".join([
            f"- **{name}**: `{count}` lần"
            for name, count in event_data.items()
        ]) if event_data else "Chưa có dữ liệu."

        embed.add_field(name="Chi tiết Sự kiện", value=events_str, inline=False)
        embed.set_footer(
            text=f"Check bởi: {author.name}",
            icon_url=author.avatar.url if author.avatar else None
        )

        await send_func(embed=embed)

    # --- Lệnh Prefix !setlogchannel --- 
    @commands.command(name='setlogchannel')
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """
        Đặt kênh log cho phiên làm việc hiện tại (Reset khi bot restart).
        Yêu cầu Role ID Admin (Ví dụ: dùng chung Role End Quota hoặc Add Point tùy ý, ở đây dùng ROLE_ID_END_QUOTA)
        """
        if not self._check_discord_role(ctx.author, ROLE_ID_END_QUOTA):
             await ctx.send("Bạn không có quyền cài đặt kênh log.")
             return

        self.log_channel_id = channel.id
        await ctx.send(f"✅ Đã đặt kênh log tại {channel.mention}. (Lưu ý: Cài đặt sẽ mất khi bot khởi động lại vì không dùng Database).")
        log.info(f"Log channel set to {channel.id}")

    # --- Helper tổng hợp: gộp _collect_all_player_points + _collect_all_players_with_zero ---
    async def _collect_all_player_data(self, include_zero: bool = False):
        """
        Thu thập điểm tất cả player từ cache.
        - include_zero=False (mặc định): chỉ lấy player có điểm > 0 (dùng cho /bxh)
        - include_zero=True: lấy cả player điểm = 0 (dùng cho quotareport)
        """
        all_sheets_data = await self._load_or_get_cache()
        if not all_sheets_data or self.column_map is None:
            return None, "Dữ liệu chưa được tải."

        all_players_data = []
        username_col_index = self.column_map['USERNAME']
        rank_col_index = self.column_map['DEPARTMENT RANK']
        points_col_index = self.column_map['POINT']

        for sheet_full_name, all_data in all_sheets_data.items():
            if sheet_full_name not in REGIMENT_SHEETS_TO_SEARCH:
                continue
            if len(all_data) <= HEADER_ROW_INDEX:
                continue

            for r_idx in range(DATA_START_INDEX, len(all_data)):
                row = all_data[r_idx]
                username = row[username_col_index].strip() if len(row) > username_col_index else ""
                if not username:
                    continue

                rank = row[rank_col_index].strip() if len(row) > rank_col_index else "N/A"
                points = 0.0
                if len(row) > points_col_index:
                    try:
                        points = float(row[points_col_index] or 0.0)
                    except (ValueError, TypeError):
                        pass

                if include_zero or points > 0:
                    all_players_data.append({"username": username, "rank": rank, "points": points})

        all_players_data.sort(key=lambda x: x['points'], reverse=True)
        return all_players_data, None

    def _generate_bxh_embed(self, ranked_players: list, page_num: int, total_pages: int, items_per_page: int, requester_info):
        start_index = (page_num - 1) * items_per_page
        end_index = start_index + items_per_page
        current_page_players = ranked_players[start_index:end_index]

        description = ""
        if not current_page_players:
            description = "Trống."
        else:
            for i, player in enumerate(current_page_players):
                global_rank = start_index + i + 1
                description += f"**Top {global_rank}.** `{player['username']}` - `{player['rank']}`: **`{player['points']:.1f}`**\n"

        embed = discord.Embed(title="🏆 Bảng Xếp Hạng Điểm", description=description, color=discord.Color.gold())
        embed.set_footer(text=f"Trang {page_num}/{total_pages} | Yêu cầu bởi: {requester_info.name}")
        return embed

    class PlayerRankView(discord.ui.View):
        def __init__(self, ranked_players, items_per_page, requester, parent_cog):
            super().__init__(timeout=180)
            self.ranked_players = ranked_players
            self.items_per_page = items_per_page
            self.requester = requester
            self.current_page = 1
            self.total_pages = max(1, (len(self.ranked_players) + items_per_page - 1) // items_per_page)
            self.parent_cog = parent_cog
            self.update_buttons()

        def update_buttons(self):
            self.children[0].disabled = self.current_page == 1
            self.children[1].disabled = self.current_page == 1
            self.children[2].disabled = self.current_page == self.total_pages
            self.children[3].disabled = self.current_page == self.total_pages

        async def update_message(self, interaction: discord.Interaction):
            self.update_buttons()
            embed = self.parent_cog._generate_bxh_embed(self.ranked_players, self.current_page, self.total_pages, self.items_per_page, self.requester)
            await interaction.response.edit_message(embed=embed, view=self)

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            return interaction.user == self.requester

        @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
        async def first_page(self, interaction, button):
            self.current_page = 1
            await self.update_message(interaction)

        @discord.ui.button(label="⬅️", style=discord.ButtonStyle.primary)
        async def previous_page(self, interaction, button):
            self.current_page -= 1
            await self.update_message(interaction)

        @discord.ui.button(label="➡️", style=discord.ButtonStyle.primary)
        async def next_page(self, interaction, button):
            self.current_page += 1
            await self.update_message(interaction)

        @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
        async def last_page(self, interaction, button):
            self.current_page = self.total_pages
            await self.update_message(interaction)

    # --- Lệnh Prefix !bxh ---
    @commands.command(name='bxh', aliases=['bangxephang', 'leaderboard'])
    async def bxh_command(self, ctx):
        await self._handle_bxh_logic(ctx)

    # --- Slash Command /bxh ---
    @discord.app_commands.command(name="bxh", description="Xem bảng xếp hạng điểm.")
    async def slash_bxh_command(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._handle_bxh_logic(interaction)

    async def _handle_bxh_logic(self, ctx_or_interaction):
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        send_func = ctx_or_interaction.send if not is_interaction else ctx_or_interaction.followup.send
        author = ctx_or_interaction.author if not is_interaction else ctx_or_interaction.user 

        ranked_players, error = await self._collect_all_player_data(include_zero=False)
        if error:
            await send_func(embed=discord.Embed(title="Lỗi", description=error, color=discord.Color.red()))
            return
        
        if not ranked_players:
            await send_func("Chưa có ai có điểm.")
            return

        view = self.PlayerRankView(ranked_players, 10, author, self)
        embed = self._generate_bxh_embed(ranked_players, 1, view.total_pages, 10, author)
        await send_func(embed=embed, view=view)

    # --- Quotareport Logic ---

    def _generate_quota_embed(self, players, page_num, total_pages, items_per_page, requester_info):
        start_index = (page_num - 1) * items_per_page
        current_page_players = players[start_index:start_index + items_per_page]
        desc = "".join([f"{p['username']} - [{p['rank']}]: {int(p['points'])} Points\n" for p in current_page_players]) or "Trống."
        return discord.Embed(title="Báo cáo Quota", description=desc, color=discord.Color.blue()).set_footer(text=f"Trang {page_num}/{total_pages} | User: {requester_info.name}")

    class QuotaReportView(PlayerRankView): # Kế thừa lại View cũ cho gọn
        async def update_message(self, interaction):
            self.update_buttons()
            embed = self.parent_cog._generate_quota_embed(self.ranked_players, self.current_page, self.total_pages, self.items_per_page, self.requester)
            await interaction.response.edit_message(embed=embed, view=self)

    @commands.command(name="quotareport")
    async def quota_report_command(self, ctx):
        ranked_players, error = await self._collect_all_player_data(include_zero=True)
        if error or not ranked_players:
            await ctx.send("Lỗi hoặc không có dữ liệu.")
            return
        view = self.QuotaReportView(ranked_players, 10, ctx.author, self)
        embed = self._generate_quota_embed(ranked_players, 1, view.total_pages, 10, ctx.author)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="checkaudit")
    async def check_audit_command(self, ctx, *, target: str = None):
        """
        !checkaudit
        !checkaudit @user
        !checkaudit roblox_username
        """

        # 🔐 Check quyền
        if not self._check_discord_role(ctx.author, ROLE_ID_END_QUOTA):
            return await ctx.send("❌ Bạn không có quyền xem audit log.")

        logs = []

        # ========= CASE 1: !checkaudit =========
        if not target:
            logs = fetch_addpoint_audit_logs(limit=10)
            title = "10 lần addpoint gần nhất"

        # ========= CASE 2: !checkaudit @user =========
        elif ctx.message.mentions:
            user = ctx.message.mentions[0]
            logs = fetch_addpoint_audit_logs(
                limit=10,
                discord_user_id=user.id
            )
            title = f"📋 10 lần dùng addpoint gần nhất bởi {user.name}"

        # ========= CASE 3: !checkaudit username =========
        else:
            roblox_username = target.strip()
            logs = fetch_addpoint_audit_logs(
                limit=10,
                roblox_username=roblox_username
            )
            title = f"Lịch sử được addpoint của `{roblox_username}`"

        if not logs:
            return await ctx.send("⚠️ Không tìm thấy audit log phù hợp.")

        # ========= FORMAT KẾT QUẢ =========
        lines = []
        for i, log_item in enumerate(logs, start=1):
            time_str = log_item["created_at"]
            lines.append(
                f"**{i}.** `{log_item['roblox_username']}` | "
                f"+{log_item['added_points']} | "
                f"`{log_item['event_type']}` | "
                f"{log_item['before_points']} → {log_item['after_points']} | "
                f"by **{log_item['discord_username']}**\n"
                f"🕒 `{time_str}`"
            )

        embed = discord.Embed(
            title=title,
            description="\n\n".join(lines),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Yêu cầu bởi {ctx.author.name}")

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(GoogleSheets(bot))
    print("GoogleSheets Cog đã được tải (Chế độ No-DB).")