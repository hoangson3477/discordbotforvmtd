"""
Utility functions for database operations and error handling
"""
import logging
from functools import wraps
from typing import Optional, Any, Callable, List, Dict
from discord.ext import commands

logger = logging.getLogger("my_bot")

def safe_db_operation(operation_name: str = "Database operation"):
    """Decorator for safe database operations with error handling"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"[{operation_name}] Database error: {e}")
                # Return None or raise based on operation type
                if "get_" in func.__name__ or "fetch_" in func.__name__:
                    return None
                elif "insert_" in func.__name__ or "update_" in func.__name__ or "delete_" in func.__name__:
                    return False
                else:
                    raise
        return wrapper
    return decorator

def handle_command_error(ctx: commands.Context, operation: str, error: Exception):
    """Handle command errors with appropriate messages"""
    logger.error(f"[{operation}] Command error: {error}")
    
    error_msg = str(error).lower()
    
    if "duplicate" in error_msg or "already exists" in error_msg:
        message = "❌ Dữ liệu đã tồn tại."
    elif "not found" in error_msg or "does not exist" in error_msg:
        message = "❌ Không tìm thấy dữ liệu."
    elif "permission" in error_msg or "unauthorized" in error_msg:
        message = "❌ Bạn không có quyền thực hiện hành động này."
    elif "constraint" in error_msg or "foreign key" in error_msg:
        message = "❌ Lỗi ràng buộc dữ liệu. Kiểm tra các liên kết."
    elif "timeout" in error_msg:
        message = "⏰ Hết thời gian chờ. Vui lòng thử lại."
    elif "rate limit" in error_msg:
        message = "⚠️ Bot đang bị rate limit. Vui lòng chờ chút."
    else:
        message = f"❌ Lỗi: {str(error)}"
    
    return ctx.send(message)

def validate_discord_id(user_input: str, field_name: str = "ID") -> Optional[int]:
    """Validate Discord user/role/channel ID"""
    try:
        return int(user_input)
    except (ValueError, TypeError):
        logger.warning(f"[Validation] Invalid {field_name}: {user_input}")
        return None

def validate_length(text: str, min_len: int = 1, max_len: int = 1000, field_name: str = "text") -> Optional[str]:
    """Validate text length"""
    if not text or len(text.strip()) < min_len:
        logger.warning(f"[Validation] {field_name} too short: '{text}'")
        return None
    if len(text) > max_len:
        logger.warning(f"[Validation] {field_name} too long: {len(text)} > {max_len}")
        return None
    return text.strip()

def validate_achievement_id(achievement_id: str) -> Optional[int]:
    """Validate achievement ID"""
    try:
        aid = int(achievement_id)
        if aid <= 0:
            logger.warning(f"[Validation] Invalid achievement ID: {achievement_id}")
            return None
        return aid
    except (ValueError, TypeError):
        logger.warning(f"[Validation] Invalid achievement ID: {achievement_id}")
        return None

def safe_embed_send(ctx: commands.Context, title: str, description: str, color: Any = None, **kwargs):
    """Safely send embed with error handling"""
    try:
        embed = discord.Embed(title=title, description=description, color=color or discord.Color.blue(), **kwargs)
        return ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"[Embed Send] Error: {e}")
        return ctx.send("❌ Lỗi khi gửi tin nhắn.")

def parse_pagination_input(page_str: str, max_page: int) -> int:
    """Parse and validate pagination input"""
    try:
        page = int(page_str) - 1  # Convert to 0-based
        return max(0, min(page, max_page))
    except (ValueError, TypeError):
        return 0  # Default to first page

def format_user_mention(user_id: int) -> str:
    """Format user mention safely"""
    return f"<@{user_id}>"

def truncate_text(text: str, max_len: int = 100, suffix: str = "...") -> str:
    """Safely truncate text"""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix
