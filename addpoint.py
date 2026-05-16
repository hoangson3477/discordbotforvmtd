"""
Merged !addpoint command — AutoSearch + SmartBatch + Vietnamese embed with per-user detail
Combines: addpoint_enhanced.py + addpoint_optimization.py
"""
import asyncio
import logging
import string
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

import discord
from discord.ext import commands
from gspread.utils import rowcol_to_a1

logger = logging.getLogger("my_bot")


# ─────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────

@dataclass
class UserSearchResult:
    """Result of user search operation (from enhanced)"""
    username: str
    sheet_name: str
    row_index: int
    status: str  # "exact_match" | "partial_match" | "multiple_matches" | "not_found"
    alternatives: List[str] = field(default_factory=list)


@dataclass
class UserUpdateDetail:
    """Per-user update detail for the response embed"""
    username: str
    sheet_name: str
    before_points: float
    after_points: float
    quota_before: str
    quota_after: str
    department_rank: str = ""

    @property
    def points_added(self) -> float:
        return self.after_points - self.before_points

    @property
    def quota_changed(self) -> bool:
        return self.quota_before != self.quota_after


@dataclass
class BatchUpdateResult:
    """Result of a full batch update run"""
    success_count: int
    failed_count: int
    updated_details: List[UserUpdateDetail]   # replaces plain updated_users list
    failed_users: List[str]
    total_points_added: float
    errors: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────
#  VALIDATOR  (from optimization)
# ─────────────────────────────────────────────

class PointUpdateValidator:
    """Validates and normalises point update inputs"""

    EVENT_TYPES = {
        'BT': 'BT',
        'CO-HOST': 'CO-HOST',
        'PHASE': 'PHASE',
        'TRYOUT': 'TRYOUT',
        'SUPERVISION': 'SUPERVISION',
        'PT': 'PT',
        'CT': 'CT',
        'EVENTS': 'EVENTS',
        'SPECIAL EVENTS': 'SPECIAL EVENTS',
        'INSPECTION': 'INSPECTION',
        'PATROL': 'PATROL',
        'INACTIVE': 'INACTIVE',
        'REQUESTED': 'REQUESTED',
    }

    POINT_LIMITS = {
        'BT': 15, 'CO-HOST': 10, 'PHASE': 20, 'TRYOUT': 15,
        'SUPERVISION': 8, 'PT': 5, 'CT': 10,
        'EVENTS': 25, 'SPECIAL EVENTS': 25,
        'INSPECTION': 12, 'PATROL': 8, 'INACTIVE': 3, 'REQUESTED': 5,
    }

    @classmethod
    def validate_event_type(cls, event_type: str) -> Tuple[bool, Optional[str], Optional[str]]:
        normalized = event_type.upper().strip()
        if normalized in cls.EVENT_TYPES:
            return True, cls.EVENT_TYPES[normalized], None
        # Fuzzy fallback
        for valid in cls.EVENT_TYPES:
            if normalized in valid or valid in normalized:
                return True, cls.EVENT_TYPES[valid], f"Auto-corrected '{event_type}' → '{cls.EVENT_TYPES[valid]}'"
        return False, None, f"Loại sự kiện không hợp lệ: `{event_type}`.\nHợp lệ: {', '.join(cls.EVENT_TYPES)}"

    @classmethod
    def validate_points(cls, points: Any, event_type: str) -> Tuple[bool, float, Optional[str]]:
        try:
            p = float(points)
        except (ValueError, TypeError):
            return False, 0, f"Điểm không hợp lệ: `{points}`. Phải là số."
        if p <= 0:
            return False, 0, "Điểm phải là số dương."
        limit = cls.POINT_LIMITS.get(event_type.upper(), 15)
        if p > limit:
            return False, p, f"Điểm vượt giới hạn cho `{event_type}`. Tối đa: **{limit}**, nhập: **{p}**"
        return True, p, None

    @classmethod
    def validate_usernames(cls, usernames_str: str) -> Tuple[bool, List[str], Optional[str]]:
        if not usernames_str or not usernames_str.strip():
            return False, [], "Danh sách người dùng không được để trống."
        usernames = [u.strip() for u in usernames_str.split(",") if u.strip()]
        if not usernames:
            return False, [], "Không tìm thấy username hợp lệ."
        duplicates = [u for u in set(usernames) if usernames.count(u) > 1]
        if duplicates:
            return False, [], f"Username bị trùng: {', '.join(duplicates)}"
        return True, usernames, None


# ─────────────────────────────────────────────
#  QUOTA CALCULATOR  (unified, from optimization — more precise thresholds)
# ─────────────────────────────────────────────

def calculate_quota_status(total_points: float, department_rank: str) -> str:
    try:
        total_points = float(total_points)
    except (TypeError, ValueError):
        return "Không xác định"

    if not department_rank:
        return "Không xác định"

    rank = department_rank.strip().lower()

    quotas = {
        "junior directing staff":  {"target": 20, "awaiting": 25},
        "directing staff":         {"target": 30, "awaiting": 35},
        "senior directing staff":  {"target": 30, "awaiting": 35},
        "head directing staff":    {"target": 30, "awaiting": 35},
    }
    info = quotas.get(rank, {"target": 4, "awaiting": 10})

    if total_points >= info["awaiting"]:
        return "Awaiting Promote"
    elif total_points >= info["target"]:
        return "Completed"
    elif total_points > 0:
        return "Half-completed"
    return "Didn't Completed"


# ─────────────────────────────────────────────
#  AUTO-SEARCH  (from enhanced)
# ─────────────────────────────────────────────

SHEET_ALIASES: Dict[str, str] = {
    "1st":   "1st Tryout Brigade",
    "2nd":   "2nd Phase Brigade",
    "3rd":   "3rd Reserved Regiment",
    "4th":   "4th Research and Development Department",
    "5th":   "5th Inspectorate Department",
    "6th":   "6th Non-regiment Regiment",
    "hicom": "VMTD Hicom",
}


class AutoSearchProcessor:
    """Partial-match user search across all sheets"""

    def __init__(self, sheets_client, column_map: Dict[str, int]):
        self.sheets_client = sheets_client
        self.column_map = column_map
        self.sheet_names = list(SHEET_ALIASES.values())

    async def find_users_bulk(
        self, partial_usernames: List[str]
    ) -> Tuple[List[UserSearchResult], List[str]]:
        logger.info(f"[AutoSearch] Processing {len(partial_usernames)} usernames")

        # Pre-fetch all sheets in parallel
        all_data = await asyncio.gather(
            *[self.sheets_client.get_sheet_data(s) for s in self.sheet_names],
            return_exceptions=True,
        )
        sheets_map = {
            name: data
            for name, data in zip(self.sheet_names, all_data)
            if not isinstance(data, Exception)
        }

        results, not_found = [], []
        for name in partial_usernames:
            r = self._find_single_user(name, sheets_map)
            results.append(r)
            if r.status == "not_found":
                not_found.append(name)
        return results, not_found

    def _find_single_user(self, partial: str, sheets_map: dict) -> UserSearchResult:
        partial_lower = partial.strip().lower()
        username_col = self.column_map.get("USERNAME")
        if username_col is None:
            return UserSearchResult(partial, "", -1, "not_found")

        all_matches = []
        for sheet_name, sheet_data in sheets_map.items():
            if not sheet_data or len(sheet_data) <= 8:
                continue
            for row_idx in range(8, len(sheet_data)):
                row = sheet_data[row_idx]
                if len(row) <= username_col or not row[username_col]:
                    continue
                uname = row[username_col].strip()
                uname_lower = uname.lower()
                if uname_lower == partial_lower:
                    all_matches.append({"username": uname, "sheet": sheet_name, "row": row_idx, "type": "exact"})
                elif uname_lower.startswith(partial_lower):
                    all_matches.append({"username": uname, "sheet": sheet_name, "row": row_idx, "type": "partial"})

        return self._select_best(partial, all_matches)

    @staticmethod
    def _select_best(partial: str, matches: list) -> UserSearchResult:
        if not matches:
            return UserSearchResult(partial, "", -1, "not_found")

        exact   = [m for m in matches if m["type"] == "exact"]
        partial_ = [m for m in matches if m["type"] == "partial"]

        if len(exact) == 1:
            m = exact[0]
            return UserSearchResult(m["username"], m["sheet"], m["row"], "exact_match")
        if len(exact) > 1:
            return UserSearchResult(partial, "", -1, "multiple_matches", [m["username"] for m in exact])
        if len(partial_) == 1:
            m = partial_[0]
            return UserSearchResult(m["username"], m["sheet"], m["row"], "partial_match")
        if partial_:
            best = min(partial_, key=lambda m: len(m["username"]))
            return UserSearchResult(
                best["username"], best["sheet"], best["row"],
                "partial_match", [m["username"] for m in partial_[:5]],
            )
        m = matches[0]
        return UserSearchResult(m["username"], m["sheet"], m["row"], "partial_match")


# ─────────────────────────────────────────────
#  EMBED BUILDER  (enhanced with per-user detail)
# ─────────────────────────────────────────────

QUOTA_EMOJI = {
    "Awaiting Promote": "🚀",
    "Completed":        "✅",
    "Half-completed":   "🔄",
    "Didn't Completed": "❌",
    "Không xác định":  "❓",
}


class VietnameseResponseBuilder:

    @staticmethod
    def success_embed(
        details: List[UserUpdateDetail],
        failed_results: List[UserSearchResult],
        multiple_results: List[UserSearchResult],
        event_type: str,
        points: float,
        author: discord.User,
    ) -> discord.Embed:
        """
        Embed hiển thị chi tiết từng người được cộng điểm:
          • Tên | Điểm: X → Y (+Z) | Quota: before → after
        """
        has_fail = bool(failed_results or multiple_results)
        color = discord.Color.orange() if has_fail else discord.Color.green()

        embed = discord.Embed(
            title="✅ Thêm Điểm Thành Công",
            description=(
                f"**Sự kiện:** `{event_type}`  |  "
                f"**Điểm thêm:** `+{points}`"
            ),
            color=color,
        )

        # ── Per-user detail ──────────────────────────────────
        if details:
            lines = []
            for d in details:
                q_before_emoji = QUOTA_EMOJI.get(d.quota_before, "❓")
                q_after_emoji  = QUOTA_EMOJI.get(d.quota_after,  "❓")

                # Highlight quota change
                if d.quota_changed:
                    quota_str = f"{q_before_emoji} {d.quota_before} → {q_after_emoji} **{d.quota_after}** ⬆️"
                else:
                    quota_str = f"{q_after_emoji} {d.quota_after}"

                lines.append(
                    f"**{d.username}**\n"
                    f"┣ 📊 Điểm: `{d.before_points}` → `{d.after_points}` *(+{d.points_added})*\n"
                    f"┗ 🏷️ Quota: {quota_str}"
                )

            # Discord field value limit = 1024 chars — split if needed
            chunks = VietnameseResponseBuilder._chunk_lines(lines, limit=1000)
            for i, chunk in enumerate(chunks):
                field_name = (
                    f"📝 Đã cập nhật ({len(details)} người)"
                    if i == 0 else "📝 (tiếp theo)"
                )
                embed.add_field(name=field_name, value="\n\n".join(chunk), inline=False)

        # ── Not found ────────────────────────────────────────
        if failed_results:
            embed.add_field(
                name=f"❌ Không tìm thấy ({len(failed_results)} người)",
                value="\n".join(f"• `{r.username}`" for r in failed_results),
                inline=False,
            )

        # ── Multiple matches ─────────────────────────────────
        if multiple_results:
            lines = []
            for r in multiple_results:
                alts = ", ".join(f"`{a}`" for a in (r.alternatives or [])[:4])
                lines.append(f"• `{r.username}` → gợi ý: {alts}")
            embed.add_field(
                name="⚠️ Trùng tên — cần tên đầy đủ",
                value="\n".join(lines),
                inline=False,
            )

        # ── Summary footer field ─────────────────────────────
        total_added = sum(d.points_added for d in details)
        promoted    = [d for d in details if d.quota_after == "Awaiting Promote" and d.quota_changed]

        summary_parts = [
            f"• Cập nhật thành công: **{len(details)}** người",
            f"• Tổng điểm đã thêm: **+{total_added}**",
        ]
        if promoted:
            summary_parts.append(
                f"• 🚀 Đủ điều kiện lên chức: {', '.join(f'**{d.username}**' for d in promoted)}"
            )

        embed.add_field(name="📊 Tổng kết", value="\n".join(summary_parts), inline=False)

        embed.set_footer(text=f"Thực hiện bởi {author.display_name}")
        embed.timestamp = discord.utils.utcnow()
        return embed

    @staticmethod
    def error_embed(error_type: str, details: str = "") -> discord.Embed:
        messages = {
            "validation":       ("❌ Lỗi xác thực",          "Vui lòng kiểm tra lại thông tin nhập vào."),
            "permission":       ("❌ Lỗi quyền truy cập",    "Bạn không có quyền thực hiện lệnh này."),
            "sheet_error":      ("❌ Lỗi Google Sheets",      "Không thể kết nối đến Google Sheets. Vui lòng thử lại sau."),
            "not_found":        ("❌ Không tìm thấy",         "Không tìm thấy người dùng nào với tên đã cho."),
            "multiple_matches": ("⚠️ Nhiều kết quả trùng",   "Vui lòng nhập tên đầy đủ hơn."),
        }
        title, desc = messages.get(error_type, ("❌ Lỗi không xác định", "Đã xảy ra lỗi."))
        embed = discord.Embed(title=title, description=desc, color=discord.Color.red())
        if details:
            embed.add_field(name="Chi tiết", value=details, inline=False)
        return embed

    @staticmethod
    def _chunk_lines(lines: List[str], limit: int = 1000) -> List[List[str]]:
        """Split lines into chunks each under `limit` chars."""
        chunks, current, current_len = [], [], 0
        for line in lines:
            if current_len + len(line) + 2 > limit and current:
                chunks.append(current)
                current, current_len = [], 0
            current.append(line)
            current_len += len(line) + 2
        if current:
            chunks.append(current)
        return chunks


# ─────────────────────────────────────────────
#  MAIN COMMAND CLASS
# ─────────────────────────────────────────────

class AddPointCommand:
    """
    Merged !addpoint command.
    Uses AutoSearchProcessor (partial matching) + PointUpdateValidator (per-event limits)
    and produces a detailed embed with before/after points and quota changes.
    """

    REQUIRED_ROLE_ID = 1126751064377544704

    def __init__(self, cog):
        self.cog = cog
        self.validator = PointUpdateValidator()
        self.auto_search = AutoSearchProcessor(cog.optimized_client, cog.column_map)

    # ── Entry point ──────────────────────────────────────────

    async def execute(self, ctx, usernames_str: str, event_type: str, points: Any):
        logger.info(
            f"[AddPoint] {getattr(getattr(ctx, 'author', None) or getattr(ctx, 'user', None), 'name', '?')}: "
            f"{usernames_str}, {event_type}, {points}"
        )

        # 1. Permission
        if not self._check_permissions(ctx):
            await self._send(ctx, VietnameseResponseBuilder.error_embed("permission"))
            return

        # 2. Validate inputs
        ok, validated, err_embed = self._validate(usernames_str, event_type, points)
        if not ok:
            await self._send(ctx, err_embed)
            return

        norm_event   = validated["event_type"]
        norm_points  = validated["points"]
        norm_names   = validated["usernames"]

        # 3. Auto-search
        search_results, _ = await self.auto_search.find_users_bulk(norm_names)

        valid_results    = [r for r in search_results if r.status in ("exact_match", "partial_match")]
        failed_results   = [r for r in search_results if r.status == "not_found"]
        multiple_results = [r for r in search_results if r.status == "multiple_matches"]

        # 4. Execute updates and collect per-user detail
        details = await self._process_updates(valid_results, norm_event, norm_points)

        # 5. Build and send embed
        author = getattr(ctx, "author", None) or getattr(ctx, "user", None)
        embed = VietnameseResponseBuilder.success_embed(
            details, failed_results, multiple_results,
            norm_event, norm_points, author,
        )
        await self._send(ctx, embed)

        # 6. Audit log
        await self._audit_log(ctx, details, norm_event, norm_points)

    # ── Validation ───────────────────────────────────────────

    def _validate(self, usernames_str, event_type, points):
        ok_e, norm_event, err_e = self.validator.validate_event_type(event_type)
        if not ok_e:
            return False, {}, VietnameseResponseBuilder.error_embed("validation", err_e)

        ok_p, norm_points, err_p = self.validator.validate_points(points, norm_event)
        if not ok_p:
            return False, {}, VietnameseResponseBuilder.error_embed("validation", err_p)

        ok_u, norm_names, err_u = self.validator.validate_usernames(usernames_str)
        if not ok_u:
            return False, {}, VietnameseResponseBuilder.error_embed("validation", err_u)

        return True, {"event_type": norm_event, "points": norm_points, "usernames": norm_names}, None

    # ── Permission ───────────────────────────────────────────

    def _check_permissions(self, ctx) -> bool:
        user = getattr(ctx, "author", None) or getattr(ctx, "user", None)
        if not isinstance(user, discord.Member):
            return False
        return any(r.id == self.REQUIRED_ROLE_ID for r in user.roles)

    # ── Sheet updates ────────────────────────────────────────

    async def _process_updates(
        self, results: List[UserSearchResult], event_type: str, points: float
    ) -> List[UserUpdateDetail]:
        """Process all valid results, grouped by sheet for batch efficiency."""
        if not results:
            return []

        # Group by sheet
        by_sheet: Dict[str, List[UserSearchResult]] = {}
        for r in results:
            by_sheet.setdefault(r.sheet_name, []).append(r)

        details: List[UserUpdateDetail] = []
        for sheet_name, sheet_results in by_sheet.items():
            sheet_details = await self._update_sheet(sheet_name, sheet_results, event_type, points)
            details.extend(sheet_details)

        return details

    async def _update_sheet(
        self,
        sheet_name: str,
        results: List[UserSearchResult],
        event_type: str,
        points: float,
    ) -> List[UserUpdateDetail]:
        column_map    = self.cog.column_map
        event_col_idx = column_map.get(event_type.upper())
        point_col_idx = column_map.get("POINT")
        quota_col_idx = column_map.get("QUOTA PROGRESS?")
        username_col  = column_map.get("USERNAME", 0)
        rank_col      = column_map.get("DEPARTMENT RANK")

        if point_col_idx is None:
            logger.error(f"[AddPoint] Missing POINT column for sheet {sheet_name}")
            return []

        details = []
        batch_updates = []

        try:
            sheet_data = await self.cog.optimized_client.get_sheet_data(sheet_name)

            for result in results:
                if not sheet_data or result.row_index >= len(sheet_data):
                    continue

                row = sheet_data[result.row_index]

                # Current values
                before_points = float(row[point_col_idx]) if len(row) > point_col_idx and row[point_col_idx] else 0.0
                after_points  = before_points + points
                dept_rank     = row[rank_col] if rank_col and len(row) > rank_col else ""

                quota_before  = calculate_quota_status(before_points, dept_rank)
                quota_after   = calculate_quota_status(after_points, dept_rank)

                logger.info(
                    f"[AddPoint] {result.username} | {sheet_name} | "
                    f"{event_type} | {before_points} → {after_points} (+{points}) | "
                    f"Quota: {quota_before} → {quota_after}"
                )

                # Prepare batch cells
                if event_col_idx is not None:
                    current_event = int(row[event_col_idx]) if len(row) > event_col_idx and row[event_col_idx] else 0
                    batch_updates.append({
                        "range": rowcol_to_a1(result.row_index + 1, event_col_idx + 1),
                        "values": [[str(current_event + 1)]],
                    })

                batch_updates.append({
                    "range": rowcol_to_a1(result.row_index + 1, point_col_idx + 1),
                    "values": [[str(after_points)]],
                })

                if quota_col_idx is not None:
                    batch_updates.append({
                        "range": rowcol_to_a1(result.row_index + 1, quota_col_idx + 1),
                        "values": [[quota_after]],
                    })

                details.append(UserUpdateDetail(
                    username=result.username,
                    sheet_name=sheet_name,
                    before_points=before_points,
                    after_points=after_points,
                    quota_before=quota_before,
                    quota_after=quota_after,
                    department_rank=dept_rank,
                ))

            # Execute all cells for this sheet in one API call
            if batch_updates:
                worksheet = self.cog.spreadsheet.worksheet(sheet_name)
                await asyncio.to_thread(worksheet.batch_update, batch_updates)
                logger.info(f"[AddPoint] {len(batch_updates)} cells updated in '{sheet_name}'")

        except Exception as e:
            logger.error(f"[AddPoint] Sheet update failed for '{sheet_name}': {e}")

        return details

    # ── Audit log ────────────────────────────────────────────

    async def _audit_log(
        self,
        ctx,
        details: List[UserUpdateDetail],
        event_type: str,
        points: float,
    ):
        author = getattr(ctx, "author", None) or getattr(ctx, "user", None)
        if not author or not details:
            return
        try:
            for d in details:
                await asyncio.to_thread(
                    self.cog.log_addpoint_audit,
                    discord_user=author,
                    roblox_username=d.username,
                    sheet_name=d.sheet_name,
                    event_type=event_type,
                    added_points=points,
                    before_points=d.before_points,
                    after_points=d.after_points,
                    before_quota=d.quota_before,
                    quota_status=d.quota_after,
                )
        except Exception as e:
            logger.error(f"[AddPoint] Audit log failed: {e}")

    # ── Send helper ──────────────────────────────────────────

    async def _send(self, ctx, embed: discord.Embed):
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(embed=embed)
            else:
                await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
