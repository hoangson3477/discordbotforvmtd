import discord
from discord.ext import commands
import json
import os
import time
import logging

logger = logging.getLogger("autorep")

# =============================================
# FILE: cogs/auto_reply.py
# Load vào main.py bằng: await bot.load_extension("cogs.auto_reply")
# =============================================

# Dữ liệu mặc định — bạn có thể sửa trực tiếp hoặc dùng lệnh để thêm/xóa khi chạy
# Cấu trúc: { "user_id": { "trigger_message": "reply_message" } }
DEFAULT_RULES: dict[str, dict[str, str]] = {
    # Ví dụ:
    # "123456789012345678": {
    #     "hello": "Chào bạn! 👋",
    #     "gg": "ez pz 😎",
    # },
}

DATA_FILE = "data/auto_reply_rules.json"   # Nơi lưu rules vĩnh viễn


def load_rules() -> dict:
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Lỗi khi load auto-reply rules: {e}")
    return dict(DEFAULT_RULES)


def save_rules(rules: dict):
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
    except (OSError, json.JSONEncodeError) as e:
        logger.error(f"Lỗi khi save auto-reply rules: {e}")
        raise


class AutoReply(commands.Cog):
    """
    Tự động gửi tin nhắn khi một user cụ thể nhắn một câu đã được cài sẵn.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rules: dict[str, dict[str, str]] = load_rules()
        # rules[user_id][trigger] = response
        self.last_reply = {}  # user_id -> timestamp for rate limiting
        self.RATE_LIMIT = 5  # seconds between replies per user

    # ------------------------------------------------------------------
    # LẮNG NGHE TIN NHẮN
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bỏ qua tin nhắn của chính bot
        if message.author.bot:
            return

        user_id = str(message.author.id)
        if user_id not in self.rules:
            return

        # Rate limiting: check if user recently got a reply
        now = time.time()
        if user_id in self.last_reply:
            if now - self.last_reply[user_id] < self.RATE_LIMIT:
                return  # Skip if within rate limit

        content = message.content.strip().lower()

        for trigger, response in self.rules[user_id].items():
            # So sánh không phân biệt hoa/thường; dùng "in" để bắt cả câu chứa trigger
            if trigger.lower() in content:
                try:
                    await message.channel.send(response)
                    self.last_reply[user_id] = now  # Update last reply time
                    break   # Chỉ gửi 1 reply đầu tiên khớp, bỏ break nếu muốn gửi tất cả
                except discord.Forbidden:
                    logger.warning(f"Bot không có quyền gửi tin nhắn trong channel {message.channel.id}")
                except Exception as e:
                    logger.error(f"Lỗi khi gửi auto-reply: {e}")

    # ------------------------------------------------------------------
    # LỆNH QUẢN LÝ (chỉ admin / owner mới dùng được)
    # ------------------------------------------------------------------

    @commands.group(name="autoreply", aliases=["ar"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def autoreply(self, ctx: commands.Context):
        """Nhóm lệnh quản lý auto-reply."""
        embed = discord.Embed(
            title="📋 Auto Reply — Hướng dẫn",
            color=0x5865F2,
            description=(
                "```\n"
                "vmtd ar add  <user_id> <trigger> | <response>\n"
                "vmtd ar remove <user_id> <trigger>\n"
                "vmtd ar list [user_id]\n"
                "vmtd ar clear <user_id>\n"
                "```"
            ),
        )
        await ctx.send(embed=embed)

    # ── Thêm rule ──────────────────────────────────────────────────────
    @autoreply.command(name="add")
    @commands.has_permissions(administrator=True)
    async def ar_add(self, ctx: commands.Context, user_id: str, *, args: str):
        """
        Thêm rule mới.
        Cú pháp: vmtd ar add <user_id> <trigger> | <response>
        Ví dụ  : vmtd ar add 123456789 hello | Chào bạn! 👋
        """
        # Validate user_id format
        try:
            user_id_int = int(user_id)
            if user_id_int <= 0:
                return await ctx.send("❌ User ID phải là số dương.")
        except ValueError:
            return await ctx.send("❌ User ID không hợp lệ. Phải là số.")
        
        if "|" not in args:
            return await ctx.send("❌ Cần dùng dấu `|` để phân cách trigger và response.\nVí dụ: `vmtd ar add 123456 hello | Xin chào!`")

        trigger, _, response = args.partition("|")
        trigger = trigger.strip()
        response = response.strip()

        if not trigger or not response:
            return await ctx.send("❌ Trigger hoặc response không được để trống.")
        
        # Validate content length
        if len(trigger) > 100:
            return await ctx.send("❌ Trigger quá dài (tối đa 100 ký tự).")
        
        if len(response) > 1000:
            return await ctx.send("❌ Response quá dài (tối đa 1000 ký tự).")

        try:
            self.rules.setdefault(user_id, {})[trigger] = response
            save_rules(self.rules)
            
            await ctx.send(
                f"✅ Đã thêm rule cho user `{user_id}`:\n"
                f"**Trigger:** `{trigger}`\n"
                f"**Response:** {response}"
            )
        except Exception as e:
            logger.error(f"Lỗi khi lưu rule: {e}")
            await ctx.send("❌ Lỗi khi lưu rule. Vui lòng thử lại.")

    # ── Xóa rule ───────────────────────────────────────────────────────
    @autoreply.command(name="remove", aliases=["rm", "del"])
    @commands.has_permissions(administrator=True)
    async def ar_remove(self, ctx: commands.Context, user_id: str, *, trigger: str):
        """
        Xóa một trigger của user.
        Cú pháp: vmtd ar remove <user_id> <trigger>
        """
        trigger = trigger.strip()
        user_rules = self.rules.get(user_id, {})

        # Tìm key không phân biệt hoa/thường
        matched_key = next((k for k in user_rules if k.lower() == trigger.lower()), None)

        if matched_key is None:
            return await ctx.send(f"❌ Không tìm thấy trigger `{trigger}` cho user `{user_id}`.")

        del self.rules[user_id][matched_key]
        if not self.rules[user_id]:
            del self.rules[user_id]   # Dọn sạch nếu user không còn rule nào
        save_rules(self.rules)

        await ctx.send(f"🗑️ Đã xóa trigger `{matched_key}` của user `{user_id}`.")

    # ── Xóa toàn bộ rule của 1 user ────────────────────────────────────
    @autoreply.command(name="clear")
    @commands.has_permissions(administrator=True)
    async def ar_clear(self, ctx: commands.Context, user_id: str):
        """Xóa tất cả rule của một user."""
        if user_id not in self.rules:
            return await ctx.send(f"❌ User `{user_id}` chưa có rule nào.")

        del self.rules[user_id]
        save_rules(self.rules)
        await ctx.send(f"🗑️ Đã xóa tất cả rule của user `{user_id}`.")

    # ── Xem danh sách rule ─────────────────────────────────────────────
    @autoreply.command(name="list", aliases=["ls"])
    @commands.has_permissions(administrator=True)
    async def ar_list(self, ctx: commands.Context, user_id: str = None):
        """
        Xem danh sách rule.
        Nếu truyền user_id thì chỉ xem rule của user đó.
        """
        if not self.rules:
            return await ctx.send("📭 Chưa có rule nào được cài đặt.")

        embed = discord.Embed(title="📋 Danh sách Auto Reply", color=0x5865F2)

        targets = {user_id: self.rules[user_id]} if user_id and user_id in self.rules else self.rules

        if not targets:
            return await ctx.send(f"❌ Không tìm thấy rule nào cho user `{user_id}`.")

        for uid, triggers in targets.items():
            rules_text = "\n".join(f"`{t}` → {r}" for t, r in triggers.items())
            embed.add_field(name=f"👤 User ID: {uid}", value=rules_text or "*(trống)*", inline=False)

        await ctx.send(embed=embed)

    # ------------------------------------------------------------------
    # XỬ LÝ LỖI QUYỀN
    # ------------------------------------------------------------------
    @autoreply.error
    @ar_add.error
    @ar_remove.error
    @ar_clear.error
    @ar_list.error
    async def ar_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("🚫 Bạn cần quyền **Administrator** để dùng lệnh này.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Thiếu tham số: `{error.param.name}`. Dùng `!ar` để xem hướng dẫn.")
        else:
            raise error


# ------------------------------------------------------------------
# SETUP (bắt buộc để load cog)
# ------------------------------------------------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReply(bot))