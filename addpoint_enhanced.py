"""
Enhanced !addpoint command with auto-search and Vietnamese responses
"""
import discord
from discord.ext import commands
import asyncio
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger("my_bot")

@dataclass
class UserSearchResult:
    """Result of user search operation"""
    username: str
    sheet_name: str
    row_index: int
    status: str  # "exact_match", "partial_match", "multiple_matches", "not_found"
    alternatives: List[str] = None

class AutoSearchProcessor:
    """Advanced user search with partial matching and suggestions"""
    
    def __init__(self, sheets_client, column_map: dict, sheet_aliases: dict):
        self.sheets_client = sheets_client
        self.column_map = column_map
        self.sheet_aliases = sheet_aliases
        self.sheet_names = list(sheet_aliases.values())
    
    async def find_users_bulk(self, partial_usernames: List[str]) -> Tuple[List[UserSearchResult], List[str]]:
        """Find multiple users with partial matching"""
        logger.info(f"[AutoSearch] Processing {len(partial_usernames)} usernames: {partial_usernames}")
        
        # Pre-fetch all sheets in parallel
        sheet_data_tasks = [
            self.sheets_client.get_sheet_data(sheet_name) 
            for sheet_name in self.sheet_names
        ]
        all_sheets_data = await asyncio.gather(*sheet_data_tasks, return_exceptions=True)
        
        # Create sheet data map
        sheets_map = {}
        for i, sheet_name in enumerate(self.sheet_names):
            if not isinstance(all_sheets_data[i], Exception):
                sheets_map[sheet_name] = all_sheets_data[i]
        
        results = []
        not_found = []
        
        for partial_username in partial_usernames:
            result = await self._find_single_user(partial_username, sheets_map)
            results.append(result)
            
            if result.status == "not_found":
                not_found.append(partial_username)
        
        return results, not_found
    
    async def _find_single_user(self, partial_username: str, sheets_map: dict) -> UserSearchResult:
        """Find a single user with smart matching"""
        partial_lower = partial_username.strip().lower()
        
        # Search through all sheets
        all_matches = []
        
        for sheet_name, sheet_data in sheets_map.items():
            if not sheet_data or len(sheet_data) <= 8:  # Skip empty sheets
                continue
            
            username_col_idx = self.column_map.get("USERNAME")
            if username_col_idx is None:
                continue
            
            matches = self._find_matches_in_sheet(partial_lower, sheet_data, username_col_idx)
            
            for match in matches:
                all_matches.append({
                    'username': match['username'],
                    'sheet_name': sheet_name,
                    'row_index': match['row_index'],
                    'match_type': match['type']  # "exact" or "partial"
                })
        
        # Determine best match
        return self._select_best_match(partial_username, all_matches)
    
    def _find_matches_in_sheet(self, partial_lower: str, sheet_data: List[List[str]], username_col_idx: int) -> List[dict]:
        """Find all matches in a single sheet"""
        matches = []
        
        for row_idx in range(8, len(sheet_data)):  # Start from row 9 (index 8)
            row = sheet_data[row_idx]
            
            if len(row) <= username_col_idx or not row[username_col_idx]:
                continue
            
            username = row[username_col_idx].strip()
            username_lower = username.lower()
            
            # Exact match
            if username_lower == partial_lower:
                matches.append({
                    'username': username,
                    'row_index': row_idx,
                    'type': 'exact'
                })
            # Partial match (starts with)
            elif username_lower.startswith(partial_lower):
                matches.append({
                    'username': username,
                    'row_index': row_idx,
                    'type': 'partial'
                })
        
        return matches
    
    def _select_best_match(self, partial_username: str, all_matches: List[dict]) -> UserSearchResult:
        """Select the best match from all found matches"""
        if not all_matches:
            return UserSearchResult(
                username=partial_username,
                sheet_name="",
                row_index=-1,
                status="not_found"
            )
        
        # Priority: Exact matches > Partial matches
        exact_matches = [m for m in all_matches if m['match_type'] == 'exact']
        partial_matches = [m for m in all_matches if m['match_type'] == 'partial']
        
        # Single exact match - best case
        if len(exact_matches) == 1:
            match = exact_matches[0]
            return UserSearchResult(
                username=match['username'],
                sheet_name=match['sheet_name'],
                row_index=match['row_index'],
                status="exact_match"
            )
        
        # Multiple exact matches - ask for clarification
        if len(exact_matches) > 1:
            alternatives = [m['username'] for m in exact_matches]
            return UserSearchResult(
                username=partial_username,
                sheet_name="",
                row_index=-1,
                status="multiple_matches",
                alternatives=alternatives
            )
        
        # Single partial match
        if len(partial_matches) == 1 and len(exact_matches) == 0:
            match = partial_matches[0]
            return UserSearchResult(
                username=match['username'],
                sheet_name=match['sheet_name'],
                row_index=match['row_index'],
                status="partial_match"
            )
        
        # Multiple partial matches - return closest
        if len(partial_matches) > 1 and len(exact_matches) == 0:
            # Choose the shortest/closest match
            best_match = min(partial_matches, key=lambda m: len(m['username']))
            alternatives = [m['username'] for m in partial_matches[:5]]  # Top 5 suggestions
            
            return UserSearchResult(
                username=best_match['username'],
                sheet_name=best_match['sheet_name'],
                row_index=best_match['row_index'],
                status="partial_match",
                alternatives=alternatives
            )
        
        # Fallback
        match = all_matches[0]
        return UserSearchResult(
            username=match['username'],
            sheet_name=match['sheet_name'],
            row_index=match['row_index'],
            status="partial_match"
        )

class VietnameseResponseBuilder:
    """Build Vietnamese responses for addpoint commands"""
    
    @staticmethod
    def success_embed(results: List[UserSearchResult], event_type: str, points: float, author: discord.User) -> discord.Embed:
        """Build success response in Vietnamese"""
        embed = discord.Embed(
            title="✅ Thêm Điểm Thành Công",
            description=f"**Sự kiện:** `{event_type}` | **Điểm:** `{points}`",
            color=discord.Color.green()
        )
        
        success_results = [r for r in results if r.status in ["exact_match", "partial_match"]]
        failed_results = [r for r in results if r.status == "not_found"]
        
        if success_results:
            success_text = []
            for result in success_results:
                if result.status == "partial_match":
                    success_text.append(f"🔍 **{result.username}** (tìm thấy từ '{result.username[:3]}...')")
                else:
                    success_text.append(f"✅ **{result.username}**")
            
            embed.add_field(
                name=f"📝 Đã cập nhật ({len(success_results)} người)",
                value="\n".join(success_text),
                inline=False
            )
        
        if failed_results:
            embed.add_field(
                name=f"❌ Không tìm thấy ({len(failed_results)} người)",
                value="\n".join(f"• {r.username}" for r in failed_results),
                inline=False
            )
        
        # Multiple matches warning
        multiple_results = [r for r in results if r.status == "multiple_matches"]
        if multiple_results:
            warning_text = []
            for result in multiple_results:
                alternatives = ", ".join(result.alternatives[:3])
                warning_text.append(f"⚠️ '{result.username}' khớp nhiều: {alternatives}")
            
            embed.add_field(
                name="⚠️ Cần làm rõ",
                value="\n".join(warning_text),
                inline=False
            )
        
        embed.set_footer(text=f"Thực hiện bởi {author.display_name}")
        embed.timestamp = discord.utils.utcnow()
        
        return embed
    
    @staticmethod
    def error_embed(error_type: str, details: str = "") -> discord.Embed:
        """Build error response in Vietnamese"""
        error_messages = {
            "validation": "❌ **Lỗi xác thực**",
            "permission": "❌ **Lỗi quyền truy cập**",
            "sheet_error": "❌ **Lỗi Google Sheets**",
            "not_found": "❌ **Không tìm thấy người dùng**",
            "multiple_matches": "⚠️ **Nhiều kết quả trùng khớp**"
        }
        
        titles = {
            "validation": "Vui lòng kiểm tra lại thông tin nhập vào.",
            "permission": "Bạn không có quyền thực hiện lệnh này.",
            "sheet_error": "Không thể kết nối đến Google Sheets. Vui lòng thử lại sau.",
            "not_found": "Không tìm thấy người dùng nào với tên đã cho.",
            "multiple_matches": "Tên người dùng khớp với nhiều người. Vui lòng nhập tên đầy đủ."
        }
        
        embed = discord.Embed(
            title=error_messages.get(error_type, "❌ **Lỗi không xác định**"),
            description=titles.get(error_type, "Đã xảy ra lỗi không xác định."),
            color=discord.Color.red()
        )
        
        if details:
            embed.add_field(name="Chi tiết", value=details, inline=False)
        
        return embed

class EnhancedAddPointCommand:
    """Enhanced addpoint command with auto-search and Vietnamese responses"""
    
    def __init__(self, cog):
        self.cog = cog
        self.auto_search = AutoSearchProcessor(
            cog.optimized_client,
            cog.column_map,
            {
                "1st": "1st Tryout Brigade",
                "2nd": "2nd Phase Brigade",
                "3rd": "3rd Reserved Regiment",
                "4th": "4th Research and Development Department",
                "5th": "5th Inspectorate Department",
                "6th": "6th Non-regiment Regiment",
                "hicom": "VMTD Hicom"
            }
        )
    
    async def execute(self, ctx, usernames_str: str, event_type: str, points: float):
        """Execute enhanced addpoint command"""
        logger.info(f"[EnhancedAddPoint] Processing: {usernames_str}, {event_type}, {points}")
        
        # Validation
        if not await self._validate_inputs(ctx, usernames_str, event_type, points):
            return
        
        # Auto-search users
        usernames = [u.strip() for u in usernames_str.split(",") if u.strip()]
        search_results, not_found = await self.auto_search.find_users_bulk(usernames)
        
        # Process updates for found users
        await self._process_updates(ctx, search_results, event_type, points)
        
        # Send response
        embed = VietnameseResponseBuilder.success_embed(search_results, event_type, points, ctx.author)
        await self._send_response(ctx, embed)
    
    async def _validate_inputs(self, ctx, usernames_str: str, event_type: str, points: float) -> bool:
        """Validate all inputs with Vietnamese error messages"""
        # Check permissions
        if not self._check_permissions(ctx):
            embed = VietnameseResponseBuilder.error_embed("permission")
            await self._send_response(ctx, embed)
            return False
        
        # Validate usernames
        if not usernames_str or not usernames_str.strip():
            embed = VietnameseResponseBuilder.error_embed("validation", "Danh sách người dùng không được để trống.")
            await self._send_response(ctx, embed)
            return False
        
        # Validate event type
        valid_events = ['BT', 'CO-HOST', 'PHASE', 'TRYOUT', 'SUPERVISION', 'PT', 'CT', 'SPECIAL EVENTS', 'INSPECTION', 'PATROL', 'INACTIVE', 'REQUESTED']
        if event_type.upper() not in valid_events:
            embed = VietnameseResponseBuilder.error_embed(
                "validation", 
                f"Loại sự kiện không hợp lệ.\n\n**Các loại hợp lệ:**\n{', '.join(valid_events)}"
            )
            await self._send_response(ctx, embed)
            return False
        
        # Validate points
        if points <= 0:
            embed = VietnameseResponseBuilder.error_embed("validation", "Điểm phải là số dương.")
            await self._send_response(ctx, embed)
            return False
        
        if points > 25:
            embed = VietnameseResponseBuilder.error_embed("validation", "Điểm tối đa cho mỗi lần là 25.")
            await self._send_response(ctx, embed)
            return False
        
        return True
    
    def _check_permissions(self, ctx) -> bool:
        """Check if user has required permissions"""
        required_role_id = 1126751064377544704
        
        user = ctx.author if hasattr(ctx, 'author') else ctx.user
        if not isinstance(user, discord.Member):
            return False
        
        return any(role.id == required_role_id for role in user.roles)
    
    async def _process_updates(self, ctx, search_results: List[UserSearchResult], event_type: str, points: float):
        """Process point updates for found users"""
        valid_results = [r for r in search_results if r.status in ["exact_match", "partial_match"]]
        
        if not valid_results:
            return
        
        # Group by sheet for batch processing
        sheet_updates = {}
        for result in valid_results:
            if result.sheet_name not in sheet_updates:
                sheet_updates[result.sheet_name] = []
            sheet_updates[result.sheet_name].append(result)
        
        # Process each sheet
        for sheet_name, updates in sheet_updates.items():
            await self._update_sheet(sheet_name, updates, event_type, points)
    
    async def _update_sheet(self, sheet_name: str, updates: List[UserSearchResult], event_type: str, points: float):
        """Update a single sheet with batch operations"""
        try:
            column_map = self.cog.column_map
            event_col_idx = column_map.get(event_type.upper())
            point_col_idx = column_map.get("POINT")
            quota_col_idx = column_map.get("QUOTA PROGRESS?")
            
            if not all([event_col_idx, point_col_idx, quota_col_idx]):
                logger.error(f"[EnhancedAddPoint] Missing columns for {event_type}")
                return
            
            # Prepare batch updates
            batch_updates = []
            for update in updates:
                # Get current data
                sheet_data = await self.cog.optimized_client.get_sheet_data(sheet_name)
                if not sheet_data or update.row_index >= len(sheet_data):
                    continue
                
                row = sheet_data[update.row_index]
                
                # Update event count
                current_event = int(row[event_col_idx]) if row[event_col_idx] else 0
                new_event = current_event + 1
                
                # Update total points
                current_points = float(row[point_col_idx]) if row[point_col_idx] else 0.0
                new_points = current_points + points
                
                # Calculate quota status
                department_rank = row[column_map.get("DEPARTMENT RANK")] if len(row) > column_map.get("DEPARTMENT RANK", 0) else ""
                new_quota = self._calculate_quota_status(new_points, department_rank)
                
                # Add batch update
                from gspread.utils import rowcol_to_a1
                batch_updates.extend([
                    {
                        'range': rowcol_to_a1(update.row_index + 1, event_col_idx + 1),
                        'values': [[str(new_event)]]
                    },
                    {
                        'range': rowcol_to_a1(update.row_index + 1, point_col_idx + 1),
                        'values': [[str(new_points)]]
                    },
                    {
                        'range': rowcol_to_a1(update.row_index + 1, quota_col_idx + 1),
                        'values': [[new_quota]]
                    }
                ])
            
            # Execute batch update
            if batch_updates:
                worksheet = self.cog.spreadsheet.worksheet(sheet_name)
                worksheet.batch_update(batch_updates)
                logger.info(f"[EnhancedAddPoint] Updated {len(batch_updates)} cells in {sheet_name}")
        
        except Exception as e:
            logger.error(f"[EnhancedAddPoint] Sheet update failed: {e}")
    
    def _calculate_quota_status(self, total_points: float, department_rank: str) -> str:
        """Calculate quota status in Vietnamese"""
        try:
            total_points = float(total_points)
        except (TypeError, ValueError):
            return "Không xác định"
        
        if not department_rank:
            return "Không xác định"
        
        rank = department_rank.strip().lower()
        
        # Define quotas by rank
        if rank == "junior directing staff":
            if total_points > 20:
                return "Chờ thăng chức"
            elif total_points >= 4:
                return "Hoàn thành"
            elif total_points > 0:
                return "Hoàn thành một nửa"
            else:
                return "Chưa hoàn thành"
        
        if rank in ["directing staff", "senior directing staff", "head directing staff"]:
            if total_points > 30:
                return "Chờ thăng chức"
            elif total_points >= 4:
                return "Hoàn thành"
            elif total_points > 0:
                return "Hoàn thành một nửa"
            else:
                return "Chưa hoàn thành"
        
        # Default
        if total_points >= 4:
            return "Hoàn thành"
        elif total_points > 0:
            return "Hoàn thành một nửa"
        
        return "Chưa hoàn thành"
    
    async def _send_response(self, ctx, embed: discord.Embed):
        """Send response using appropriate method"""
        if isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(embed=embed)
            else:
                await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
