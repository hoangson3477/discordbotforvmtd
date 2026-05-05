"""
Utilities và decorators cho natgame
"""
from functools import wraps
from cogs.natgame.__db import supabase


def require_nation(coro):
    """Decorator kiểm tra user có nation không"""
    @wraps(coro)
    async def wrapper(self, ctx, *args, **kwargs):
        user_id = str(ctx.author.id)

        nation = supabase.table("nations") \
            .select("id, name") \
            .eq("owner_id", user_id) \
            .single().execute().data

        if not nation:
            await ctx.reply("❌ Bạn chưa có quốc gia. Dùng `!gameregister` trước.")
            return

        # Thêm nation vào ctx để dùng trong command
        ctx.nation_id = nation["id"]
        ctx.nation_name = nation["name"]

        return await coro(self, ctx, *args, **kwargs)

    return wrapper


def get_nation_id(user_id: str) -> str | None:
    """Lấy nation_id từ user_id, return None nếu không có"""
    res = supabase.table("nations") \
        .select("id") \
        .eq("owner_id", user_id) \
        .single().execute()
    return res.data["id"] if res.data else None
