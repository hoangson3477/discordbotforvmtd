"""
Advanced !addpoint command optimization with smart batching and validation
"""
import asyncio
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from discord.ext import commands
import discord

logger = logging.getLogger("my_bot")

@dataclass
class PointUpdate:
    """Represents a single point update operation"""
    username: str
    event_type: str
    points: float
    sheet_name: str
    row_index: int
    before_points: float
    department_rank: str
    quota_status: str

@dataclass
class BatchUpdateResult:
    """Result of batch update operation"""
    success_count: int
    failed_count: int
    updated_users: List[str]
    failed_users: List[str]
    total_points_added: float
    errors: List[str]

class PointUpdateValidator:
    """Validates and normalizes point update inputs"""
    
    # Valid event types and their column mappings
    EVENT_TYPES = {
        'BT': 'BT',
        'CO-HOST': 'CO-HOST', 
        'PHASE': 'PHASE',
        'TRYOUT': 'TRYOUT',
        'SUPERVISION': 'SUPERVISION',
        'PT': 'PT',
        'CT': 'CT',
        'SPECIAL EVENTS': 'SPECIAL EVENTS',
        'INSPECTION': 'INSPECTION',
        'PATROL': 'PATROL',
        'INACTIVE': 'INACTIVE',
        'REQUESTED': 'REQUESTED'
    }
    
    # Point limits per event type
    POINT_LIMITS = {
        'BT': 15,
        'CO-HOST': 10,
        'PHASE': 20,
        'TRYOUT': 15,
        'SUPERVISION': 8,
        'PT': 5,
        'CT': 10,
        'SPECIAL EVENTS': 25,
        'INSPECTION': 12,
        'PATROL': 8,
        'INACTIVE': 3,
        'REQUESTED': 5
    }
    
    @classmethod
    def validate_event_type(cls, event_type: str) -> Tuple[bool, str, Optional[str]]:
        """Validate event type and return normalized form"""
        normalized = event_type.upper().strip()
        
        if normalized in cls.EVENT_TYPES:
            return True, cls.EVENT_TYPES[normalized], None
        
        # Fuzzy matching for common typos
        for valid in cls.EVENT_TYPES:
            if normalized in valid or valid in normalized:
                return True, cls.EVENT_TYPES[valid], f"Auto-corrected '{event_type}' to '{cls.EVENT_TYPES[valid]}'"
        
        return False, None, f"Invalid event type: '{event_type}'. Valid types: {', '.join(cls.EVENT_TYPES.keys())}"
    
    @classmethod
    def validate_points(cls, points: Any, event_type: str) -> Tuple[bool, float, Optional[str]]:
        """Validate points and check limits"""
        try:
            parsed_points = float(points)
        except (ValueError, TypeError):
            return False, 0, f"Invalid points value: '{points}'. Must be a number."
        
        if parsed_points <= 0:
            return False, 0, f"Points must be positive. Got: {parsed_points}"
        
        # Check event-specific limits
        limit = cls.POINT_LIMITS.get(event_type.upper(), 15)
        if parsed_points > limit:
            return False, parsed_points, f"Points exceed limit for {event_type}. Max: {limit}, Got: {parsed_points}"
        
        return True, parsed_points, None
    
    @classmethod
    def validate_usernames(cls, usernames_str: str) -> Tuple[bool, List[str], Optional[str]]:
        """Validate and parse username list"""
        if not usernames_str or not usernames_str.strip():
            return False, [], "Username list cannot be empty."
        
        usernames = [u.strip() for u in usernames_str.split(",") if u.strip()]
        
        if not usernames:
            return False, [], "No valid usernames found."
        
        # Check for duplicates
        duplicates = [u for u in set(usernames) if usernames.count(u) > 1]
        if duplicates:
            return False, [], f"Duplicate usernames found: {', '.join(duplicates)}"
        
        # Check username format (basic validation)
        invalid_usernames = []
        for username in usernames:
            if len(username) < 3 or len(username) > 50:
                invalid_usernames.append(username)
            elif not username.replace('_', '').replace('-', '').isalnum():
                invalid_usernames.append(username)
        
        if invalid_usernames:
            return False, [], f"Invalid username format: {', '.join(invalid_usernames)}. Must be 3-50 characters, alphanumeric + '_' + '-'"
        
        return True, usernames, None

class SmartPointProcessor:
    """Intelligent point update processor with batching and optimization"""
    
    def __init__(self, sheets_client, column_map: Dict[str, int]):
        self.sheets_client = sheets_client
        self.column_map = column_map
        self.sheet_aliases = {
            "1st": "1st Tryout Brigade",
            "2nd": "2nd Phase Brigade", 
            "3rd": "3rd Reserved Regiment",
            "4th": "4th Research and Development Department",
            "5th": "5th Inspectorate Department",
            "6th": "6th Non-regiment Regiment",
            "hicom": "VMTD Hicom"
        }
    
    async def process_batch_update(self, usernames: List[str], event_type: str, points: float) -> BatchUpdateResult:
        """Process batch point update with optimization"""
        logger.info(f"[PointProcessor] Processing batch update: {len(usernames)} users, {event_type}, {points} points")
        
        # Pre-fetch all sheets in parallel
        sheet_names = list(self.sheet_aliases.values())
        sheet_data_tasks = [
            self.sheets_client.get_sheet_data(sheet_name) 
            for sheet_name in sheet_names
        ]
        all_sheets_data = await asyncio.gather(*sheet_data_tasks, return_exceptions=True)
        
        # Create sheet data map
        sheets_map = {}
        for i, sheet_name in enumerate(sheet_names):
            if not isinstance(all_sheets_data[i], Exception):
                sheets_map[sheet_name] = all_sheets_data[i]
        
        # Find all users and prepare updates
        updates = []
        failed_users = []
        
        for username in usernames:
            user_update = await self._find_user_and_prepare_update(username, event_type, points, sheets_map)
            if user_update:
                updates.append(user_update)
            else:
                failed_users.append(username)
        
        # Execute batch updates
        if updates:
            await self._execute_batch_updates(updates)
        
        # Prepare result
        updated_usernames = [u.username for u in updates]
        total_points = len(updated_usernames) * points
        
        result = BatchUpdateResult(
            success_count=len(updated_usernames),
            failed_count=len(failed_users),
            updated_users=updated_usernames,
            failed_users=failed_users,
            total_points_added=total_points,
            errors=[]
        )
        
        logger.info(f"[PointProcessor] Batch complete: {result.success_count} success, {result.failed_count} failed")
        return result
    
    async def _find_user_and_prepare_update(self, username: str, event_type: str, points: float, sheets_map: Dict[str, List[List[str]]]) -> Optional[PointUpdate]:
        """Find user across all sheets and prepare update"""
        username_lower = username.lower().strip()
        
        for sheet_name, sheet_data in sheets_map.items():
            if not sheet_data or len(sheet_data) <= 8:  # Skip empty sheets
                continue
            
            # Use optimized client's fast user lookup
            row_index = self.sheets_client.find_user_row_fast(sheet_name, username)
            if row_index is not None and row_index > 7:  # Data starts at row 8
                # Get current data
                row_data = sheet_data[row_index]
                
                # Extract current points and rank
                point_col = self.column_map.get('POINT')
                rank_col = self.column_map.get('DEPARTMENT RANK')
                event_col = self.column_map.get(event_type)
                
                if point_col is None or event_col is None:
                    continue
                
                before_points = float(row_data[point_col]) if row_data[point_col] else 0.0
                department_rank = row_data[rank_col] if rank_col and rank_col < len(row_data) else ""
                
                # Calculate quota status
                quota_status = self._calculate_quota_status(before_points, department_rank)
                
                return PointUpdate(
                    username=username,
                    event_type=event_type,
                    points=points,
                    sheet_name=sheet_name,
                    row_index=row_index,
                    before_points=before_points,
                    department_rank=department_rank,
                    quota_status=quota_status
                )
        
        return None
    
    def _calculate_quota_status(self, total_points: float, department_rank: str) -> str:
        """Calculate quota status based on points and rank"""
        try:
            total_points = float(total_points)
        except (TypeError, ValueError):
            return "UNKNOWN"
        
        if not department_rank:
            return "UNKNOWN"
        
        rank = department_rank.strip().lower()
        
        # Define quotas by rank
        quotas = {
            "junior directing staff": {"target": 20, "awaiting": 25},
            "directing staff": {"target": 30, "awaiting": 35},
            "senior directing staff": {"target": 30, "awaiting": 35},
            "head directing staff": {"target": 30, "awaiting": 35}
        }
        
        quota_info = quotas.get(rank, {"target": 4, "awaiting": 10})
        
        if total_points >= quota_info["awaiting"]:
            return "Awaiting Promote"
        elif total_points >= quota_info["target"]:
            return "Completed"
        elif total_points > 0:
            return "Half-completed"
        else:
            return "Didn't Completed"
    
    async def _execute_batch_updates(self, updates: List[PointUpdate]):
        """Execute all updates in optimized batches"""
        logger.info(f"[PointProcessor] Executing {len(updates)} updates")
        
        # Group updates by sheet for efficiency
        sheet_updates = {}
        for update in updates:
            if update.sheet_name not in sheet_updates:
                sheet_updates[update.sheet_name] = []
            sheet_updates[update.sheet_name].append(update)
        
        # Process each sheet
        for sheet_name, sheet_updates_list in sheet_updates.items():
            await self._process_sheet_updates(sheet_name, sheet_updates_list)
    
    async def _process_sheet_updates(self, sheet_name: str, updates: List[PointUpdate]):
        """Process updates for a specific sheet"""
        for update in updates:
            try:
                # Update event column
                event_col = self.column_map.get(update.event_type)
                if event_col is not None:
                    cell = self._row_col_to_a1(update.row_index + 1, event_col + 1)
                    await self.sheets_client.update_cell(sheet_name, cell, 1, batch=True)
                
                # Update total points
                new_total = update.before_points + update.points
                point_col = self.column_map.get('POINT')
                if point_col is not None:
                    cell = self._row_col_to_a1(update.row_index + 1, point_col + 1)
                    await self.sheets_client.update_cell(sheet_name, cell, new_total, batch=True)
                
                logger.debug(f"[PointProcessor] Updated {update.username}: +{update.points} points in {sheet_name}")
                
            except Exception as e:
                logger.error(f"[PointProcessor] Failed to update {update.username} in {sheet_name}: {e}")
        
        # Flush all updates for this sheet
        await self.sheets_client.flush_updates()
    
    def _row_col_to_a1(self, row: int, col: int) -> str:
        """Convert row/col to A1 notation"""
        import string
        col_str = ""
        while col > 0:
            col -= 1
            col_str = string.ascii_uppercase[col % 26] + col_str
            col //= 26
        return f"{col_str}{row}"

class OptimizedAddPointCommand:
    """Optimized version of !addpoint command"""
    
    def __init__(self, cog):
        self.cog = cog
        self.validator = PointUpdateValidator()
        
    async def execute(self, ctx, usernames_str: str, event_type: str, points: Any) -> discord.Message:
        """Execute optimized addpoint command"""
        logger.info(f"[AddPoint] Processing request from {getattr(ctx.author, 'name', 'Unknown')}: {usernames_str}, {event_type}, {points}")
        
        # Step 1: Validate all inputs
        validation_results = await self._validate_all_inputs(usernames_str, event_type, points)
        if not validation_results['valid']:
            error_embed = discord.Embed(
                title="❌ Validation Error",
                description=validation_results['error'],
                color=discord.Color.red()
            )
            return await self._send_response(ctx, error_embed)
        
        # Step 2: Check permissions
        if not await self._check_permissions(ctx):
            return
        
        # Step 3: Process with smart batching
        processor = SmartPointProcessor(self.cog.optimized_client, self.cog.column_map)
        result = await processor.process_batch_update(
            validation_results['usernames'],
            validation_results['event_type'],
            validation_results['points']
        )
        
        # Step 4: Generate response
        response_embed = await self._generate_response_embed(result, validation_results['event_type'], validation_results['points'])
        
        # Step 5: Log to audit
        await self._log_audit_results(ctx, result, validation_results)
        
        return await self._send_response(ctx, response_embed)
    
    async def _validate_all_inputs(self, usernames_str: str, event_type: str, points: Any) -> Dict[str, Any]:
        """Validate all command inputs"""
        result = {'valid': True, 'error': None}
        
        # Validate event type
        valid, normalized_event, warning = self.validator.validate_event_type(event_type)
        if not valid:
            result['valid'] = False
            result['error'] = warning
            return result
        
        result['event_type'] = normalized_event
        if warning:
            logger.info(f"[AddPoint] {warning}")
        
        # Validate points
        valid_points, normalized_points, points_error = self.validator.validate_points(points, normalized_event)
        if not valid_points:
            result['valid'] = False
            result['error'] = points_error
            return result
        
        result['points'] = normalized_points
        
        # Validate usernames
        valid_usernames, normalized_usernames, usernames_error = self.validator.validate_usernames(usernames_str)
        if not valid_usernames:
            result['valid'] = False
            result['error'] = usernames_error
            return result
        
        result['usernames'] = normalized_usernames
        
        return result
    
    async def _check_permissions(self, ctx) -> bool:
        """Check if user has required permissions"""
        required_role_id = 1126751064377544704  # ROLE_ID_ADD_POINT
        
        if hasattr(ctx, 'author'):
            user = ctx.author
        else:
            user = ctx.user
        
        if not isinstance(user, discord.Member):
            error_embed = discord.Embed(
                title="❌ Permission Error",
                description="This command can only be used in a server.",
                color=discord.Color.red()
            )
            await self._send_response(ctx, error_embed)
            return False
        
        has_permission = any(role.id == required_role_id for role in user.roles)
        if not has_permission:
            error_embed = discord.Embed(
                title="❌ Permission Error",
                description=f"You need role <@&{required_role_id}> to use this command.",
                color=discord.Color.red()
            )
            await self._send_response(ctx, error_embed)
            return False
        
        return True
    
    async def _generate_response_embed(self, result: BatchUpdateResult, event_type: str, points: float) -> discord.Embed:
        """Generate comprehensive response embed"""
        color = discord.Color.green() if result.failed_count == 0 else discord.Color.orange()
        
        embed = discord.Embed(
            title="✅ Point Update Complete",
            description=f"Processed **{event_type}** event with **{points}** points each.",
            color=color
        )
        
        # Success section
        if result.success_count > 0:
            success_text = "\n".join(f"• {user}" for user in result.updated_users[:10])
            if len(result.updated_users) > 10:
                success_text += f"\n... and {len(result.updated_users) - 10} more"
            
            embed.add_field(
                name=f"✅ Successfully Updated ({result.success_count})",
                value=success_text,
                inline=False
            )
        
        # Failed section
        if result.failed_count > 0:
            failed_text = "\n".join(f"• {user}" for user in result.failed_users[:10])
            if len(result.failed_users) > 10:
                failed_text += f"\n... and {len(result.failed_users) - 10} more"
            
            embed.add_field(
                name=f"❌ Not Found ({result.failed_count})",
                value=failed_text,
                inline=False
            )
        
        # Summary
        embed.add_field(
            name="📊 Summary",
            value=f"• Total points added: **{result.total_points_added}**\n• Success rate: **{result.success_count}/{result.success_count + result.failed_count}**",
            inline=False
        )
        
        embed.set_footer(text=f"Processed by {getattr(self.cog.bot.user, 'name', 'Bot')}")
        embed.timestamp = discord.utils.utcnow()
        
        return embed
    
    async def _log_audit_results(self, ctx, result: BatchUpdateResult, validation_results: Dict[str, Any]):
        """Log results to audit database"""
        try:
            author = getattr(ctx, 'author', None) or getattr(ctx, 'user', None)
            if not author:
                return
            
            for update in result.updated_users:
                # This would integrate with the existing audit logging system
                await asyncio.to_thread(
                    self.cog.log_addpoint_audit,
                    discord_user=author,
                    roblox_username=update.username,
                    sheet_name=update.sheet_name,
                    event_type=validation_results['event_type'],
                    added_points=validation_results['points'],
                    before_points=update.before_points,
                    after_points=update.before_points + validation_results['points'],
                    before_quota=update.quota_status,
                    quota_status=update.quota_status
                )
        except Exception as e:
            logger.error(f"[AddPoint] Audit logging failed: {e}")
    
    async def _send_response(self, ctx, embed: discord.Embed) -> discord.Message:
        """Send response using appropriate method"""
        if isinstance(ctx, discord.Interaction):
            return await ctx.followup.send(embed=embed)
        else:
            return await ctx.send(embed=embed)
