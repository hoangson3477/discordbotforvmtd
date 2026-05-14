"""
support_hub.py — Discord.py Cog
Multi-guild support hub: panel, modals, forwarding, reply flow.
Persistent views survive bot restart.
"""

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import uuid
import logging

# ─────────────────────────────────────────
#  CONFIG — chỉnh 3 dòng này
# ─────────────────────────────────────────
HUB_GUILD_ID         = 1504540055153283092   # ID guild trung tâm
HUB_SUPPORT_CHANNEL_ID = 1504540147293618267  # channel nhận ticket support
HUB_MESSAGE_CHANNEL_ID = 1504540056000663585  # channel nhận message thường
# ─────────────────────────────────────────

DATA_FILE = "support_hub_data.json"

logger = logging.getLogger("support_hub")


# ══════════════════════════════════════════
#  JSON HELPERS
# ══════════════════════════════════════════

def _load() -> dict:
    """Đọc dữ liệu từ JSON, tự tạo file nếu chưa có."""
    if not os.path.exists(DATA_FILE):
        _save({"guilds": {}, "submissions": {}})
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    """Ghi toàn bộ dữ liệu xuống JSON."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_submission(sub_id: str) -> dict | None:
    return _load()["submissions"].get(sub_id)


def _mark_replied(sub_id: str) -> None:
    data = _load()
    if sub_id in data["submissions"]:
        data["submissions"][sub_id]["replied"] = True
        _save(data)


# ══════════════════════════════════════════
#  MODALS
# ══════════════════════════════════════════

class SupportModal(discord.ui.Modal, title="Gửi yêu cầu hỗ trợ"):
    issue_title = discord.ui.TextInput(
        label="Tiêu đề vấn đề",
        placeholder="Mô tả ngắn về vấn đề của bạn...",
        max_length=100,
    )
    description = discord.ui.TextInput(
        label="Mô tả chi tiết",
        style=discord.TextStyle.paragraph,
        placeholder="Cung cấp thêm thông tin chi tiết...",
        max_length=1000,
    )

    def __init__(self, reply_channel_id: int):
        super().__init__()
        self.reply_channel_id = reply_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        await _handle_submission(
            interaction=interaction,
            sub_type="support",
            content=f"**{self.issue_title.value}**\n\n{self.description.value}",
            reply_channel_id=self.reply_channel_id,
        )


class MessageModal(discord.ui.Modal, title="Gửi tin nhắn"):
    content = discord.ui.TextInput(
        label="Nội dung",
        style=discord.TextStyle.paragraph,
        placeholder="Nhập nội dung tin nhắn...",
        max_length=1000,
    )

    def __init__(self, reply_channel_id: int):
        super().__init__()
        self.reply_channel_id = reply_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        await _handle_submission(
            interaction=interaction,
            sub_type="message",
            content=self.content.value,
            reply_channel_id=self.reply_channel_id,
        )


class ReplyModal(discord.ui.Modal, title="Trả lời submission"):
    reply_content = discord.ui.TextInput(
        label="Nội dung trả lời",
        style=discord.TextStyle.paragraph,
        placeholder="Nhập nội dung trả lời...",
        max_length=1000,
    )

    def __init__(self, sub_id: str, bot: commands.Bot):
        super().__init__()
        self.sub_id = sub_id
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        sub = _get_submission(self.sub_id)
        if not sub:
            await interaction.response.send_message(
                "❌ Không tìm thấy submission.", ephemeral=True
            )
            return

        if sub.get("replied"):
            await interaction.response.send_message(
                "⚠️ Submission này đã được trả lời rồi.", ephemeral=True
            )
            return

        # Gửi reply về guild gốc
        try:
            reply_channel = self.bot.get_channel(sub["reply_channel_id"])
            if reply_channel is None:
                reply_channel = await self.bot.fetch_channel(sub["reply_channel_id"])

            sub_type_label = "Hỗ trợ" if sub["type"] == "support" else "Tin nhắn"
            embed = discord.Embed(
                title=f"📬 Phản hồi cho yêu cầu [{sub_type_label}]",
                description=self.reply_content.value,
                color=discord.Color.green(),
            )
            embed.add_field(
                name="📋 Mã submission",
                value=f"`{self.sub_id}`",
                inline=False,
            )
            embed.set_footer(text="Phản hồi từ Hub Support")

            await reply_channel.send(
                content=f"<@{sub['user_id']}>",
                embed=embed,
            )

            _mark_replied(self.sub_id)

            # Disable nút Reply trên hub embed
            await _disable_reply_button(interaction, self.sub_id)

            await interaction.response.send_message(
                f"✅ Đã gửi reply cho `{self.sub_id}`.", ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot không có quyền gửi tin vào channel reply.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"[REPLY ERROR] {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Lỗi khi gửi reply: `{e}`", ephemeral=True
            )


# ══════════════════════════════════════════
#  PERSISTENT VIEWS
# ══════════════════════════════════════════

class PanelView(discord.ui.View):
    """
    View cho embed panel tại các guild thành viên.
    custom_id cố định → survive restart.
    reply_channel_id được encode vào custom_id.
    """

    def __init__(self, reply_channel_id: int):
        super().__init__(timeout=None)  # persistent
        self.reply_channel_id = reply_channel_id

        # Tạo button Support
        support_btn = discord.ui.Button(
            label="🎫 Support",
            style=discord.ButtonStyle.primary,
            custom_id=f"panel_support_{reply_channel_id}",
        )
        support_btn.callback = self._support_callback
        self.add_item(support_btn)

        # Tạo button Message
        message_btn = discord.ui.Button(
            label="✉️ Message",
            style=discord.ButtonStyle.secondary,
            custom_id=f"panel_message_{reply_channel_id}",
        )
        message_btn.callback = self._message_callback
        self.add_item(message_btn)

    async def _support_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            SupportModal(reply_channel_id=self.reply_channel_id)
        )

    async def _message_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            MessageModal(reply_channel_id=self.reply_channel_id)
        )


class HubReplyView(discord.ui.View):
    """
    View trên hub embed — có nút Reply.
    custom_id encode submission_id → survive restart.
    """

    def __init__(self, sub_id: str, bot: commands.Bot, disabled: bool = False):
        super().__init__(timeout=None)
        self.sub_id = sub_id
        self.bot = bot

        reply_btn = discord.ui.Button(
            label="💬 Reply",
            style=discord.ButtonStyle.success,
            custom_id=f"hub_reply_{sub_id}",
            disabled=disabled,
        )
        reply_btn.callback = self._reply_callback
        self.add_item(reply_btn)

    async def _reply_callback(self, interaction: discord.Interaction):
        # Chỉ admin mới được reply
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Chỉ Administrator mới có thể trả lời.", ephemeral=True
            )
            return

        sub = _get_submission(self.sub_id)
        if not sub:
            await interaction.response.send_message(
                "❌ Submission không tồn tại.", ephemeral=True
            )
            return

        if sub.get("replied"):
            await interaction.response.send_message(
                "⚠️ Submission này đã được trả lời rồi.", ephemeral=True
            )
            return

        await interaction.response.send_modal(
            ReplyModal(sub_id=self.sub_id, bot=self.bot)
        )


# ══════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════

async def _handle_submission(
    interaction: discord.Interaction,
    sub_type: str,
    content: str,
    reply_channel_id: int,
):
    """Tạo submission, lưu JSON, forward lên hub."""
    sub_id = str(uuid.uuid4())[:8].upper()

    data = _load()
    data["submissions"][sub_id] = {
        "type": sub_type,
        "guild_id": interaction.guild.id,
        "guild_name": interaction.guild.name,
        "user_id": interaction.user.id,
        "username": str(interaction.user),
        "reply_channel_id": reply_channel_id,
        "content": content,
        "replied": False,
    }
    _save(data)

    bot: commands.Bot = interaction.client

    # Xác định hub channel
    hub_channel_id = (
        HUB_SUPPORT_CHANNEL_ID if sub_type == "support" else HUB_MESSAGE_CHANNEL_ID
    )

    try:
        hub_channel = bot.get_channel(hub_channel_id)
        if hub_channel is None:
            hub_channel = await bot.fetch_channel(hub_channel_id)

        sub_type_label = "🎫 Support" if sub_type == "support" else "✉️ Message"
        embed = discord.Embed(
            title=f"{sub_type_label} — `{sub_id}`",
            description=content,
            color=discord.Color.orange() if sub_type == "support" else discord.Color.blue(),
        )
        embed.add_field(
            name="🏠 Guild",
            value=f"{interaction.guild.name} (`{interaction.guild.id}`)",
            inline=True,
        )
        embed.add_field(
            name="👤 User",
            value=f"{interaction.user.mention} — `{interaction.user}`",
            inline=True,
        )
        embed.set_footer(text=f"Submission ID: {sub_id}")

        view = HubReplyView(sub_id=sub_id, bot=bot)
        await hub_channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            f"✅ Đã gửi thành công! Mã của bạn: `{sub_id}`",
            ephemeral=True,
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Bot không có quyền gửi tin vào hub channel.", ephemeral=True
        )
    except Exception as e:
        logger.error(f"[SUBMISSION ERROR] {e}", exc_info=True)
        await interaction.response.send_message(
            f"❌ Lỗi khi xử lý submission: `{e}`", ephemeral=True
        )


async def _disable_reply_button(interaction: discord.Interaction, sub_id: str):
    """
    Edit message trên hub để disable nút Reply sau khi đã trả lời.
    interaction ở đây là từ ReplyModal — message gốc không dễ lấy,
    nên ta search trong hub channel.
    """
    try:
        bot: commands.Bot = interaction.client
        hub_guild = bot.get_guild(HUB_GUILD_ID)
        if not hub_guild:
            return

        # Tìm trong cả 2 hub channel
        for ch_id in (HUB_SUPPORT_CHANNEL_ID, HUB_MESSAGE_CHANNEL_ID):
            channel = hub_guild.get_channel(ch_id)
            if not channel:
                continue
            async for msg in channel.history(limit=200):
                if (
                    msg.author == bot.user
                    and msg.embeds
                    and sub_id in (msg.embeds[0].footer.text or "")
                ):
                    disabled_view = HubReplyView(sub_id=sub_id, bot=bot, disabled=True)
                    await msg.edit(view=disabled_view)
                    return
    except Exception as e:
        logger.warning(f"[DISABLE BUTTON] Không thể disable button: {e}")


# ══════════════════════════════════════════
#  COG
# ══════════════════════════════════════════

class SupportHub(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Đảm bảo file JSON tồn tại ngay khi cog load
        _load()

    async def cog_load(self):
        """
        Đăng ký lại tất cả persistent views từ JSON khi bot restart.
        Gọi sau khi cog được add vào bot.
        """
        data = _load()

        # 1) Panel views — mỗi guild có reply_channel_id riêng
        registered_reply_channels: set[int] = set()
        for guild_data in data["guilds"].values():
            rch = guild_data.get("reply_channel_id")
            if rch and rch not in registered_reply_channels:
                self.bot.add_view(PanelView(reply_channel_id=rch))
                registered_reply_channels.add(rch)

        # 2) Hub reply views — mỗi submission chưa replied
        for sub_id, sub in data["submissions"].items():
            replied = sub.get("replied", False)
            self.bot.add_view(
                HubReplyView(sub_id=sub_id, bot=self.bot, disabled=replied)
            )

        logger.info(
            f"[SUPPORT-HUB] Registered {len(registered_reply_channels)} panel view(s), "
            f"{len(data['submissions'])} hub reply view(s)."
        )

    # ──────────────────────────────────────
    #  /postpanel  (slash)
    # ──────────────────────────────────────
    @app_commands.command(
        name="postpanel",
        description="Gửi support panel vào một channel của guild chỉ định",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        guild_id="ID của guild muốn đặt panel",
        channel_id="ID của channel sẽ nhận panel embed",
        reply_channel_id="ID channel tại guild đó để nhận reply từ hub",
    )
    async def postpanel_slash(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        channel_id: str,
        reply_channel_id: str,
    ):
        await interaction.response.defer(ephemeral=True)
        result = await self._do_postpanel(
            int(guild_id), int(channel_id), int(reply_channel_id)
        )
        await interaction.followup.send(result, ephemeral=True)

    # ──────────────────────────────────────
    #  !postpanel  (prefix)
    # ──────────────────────────────────────
    @commands.command(name="postpanel")
    @commands.has_permissions(administrator=True)
    async def postpanel_prefix(
        self,
        ctx: commands.Context,
        guild_id: int,
        channel_id: int,
        reply_channel_id: int,
    ):
        result = await self._do_postpanel(guild_id, channel_id, reply_channel_id)
        await ctx.reply(result)

    # ──────────────────────────────────────
    #  Logic chung cho postpanel
    # ──────────────────────────────────────
    async def _do_postpanel(
        self,
        guild_id: int,
        channel_id: int,
        reply_channel_id: int,
    ) -> str:
        # Verify bot có trong guild
        target_guild = self.bot.get_guild(guild_id)
        if not target_guild:
            return (
                f"❌ Bot không có trong guild `{guild_id}`. "
                "Hãy mời bot vào guild đó trước."
            )

        # Verify channel tồn tại
        target_channel = target_guild.get_channel(channel_id)
        if not target_channel:
            try:
                target_channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                return f"❌ Không tìm thấy channel `{channel_id}` trong guild `{guild_id}`."
            except discord.Forbidden:
                return f"❌ Bot không có quyền truy cập channel `{channel_id}`."

        # Lưu vào JSON
        data = _load()
        data["guilds"][str(guild_id)] = {
            "panel_channel_id": channel_id,
            "reply_channel_id": reply_channel_id,
        }
        _save(data)

        # Tạo panel embed + persistent view
        embed = discord.Embed(
            title="🛎️ Support Hub",
            description=(
                "Cần hỗ trợ hoặc muốn gửi tin nhắn đến ban quản trị?\n\n"
                "• **🎫 Support** — Mở ticket hỗ trợ kỹ thuật\n"
                "• **✉️ Message** — Gửi tin nhắn trực tiếp"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Nhấn nút bên dưới để bắt đầu")

        view = PanelView(reply_channel_id=reply_channel_id)

        # Đăng ký persistent view
        self.bot.add_view(view)

        try:
            await target_channel.send(embed=embed, view=view)
        except discord.Forbidden:
            return f"❌ Bot không có quyền gửi tin vào channel `{channel_id}`."
        except Exception as e:
            logger.error(f"[POSTPANEL ERROR] {e}", exc_info=True)
            return f"❌ Lỗi: `{e}`"

        return (
            f"✅ Đã gửi panel vào <#{channel_id}> (guild: `{target_guild.name}`). "
            f"Reply channel: <#{reply_channel_id}>"
        )

    # ──────────────────────────────────────
    #  Error handlers
    # ──────────────────────────────────────
    @postpanel_slash.error
    async def postpanel_slash_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Bạn cần quyền **Administrator** để dùng lệnh này.", ephemeral=True
            )
        else:
            logger.error(f"[POSTPANEL SLASH ERROR] {error}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Lỗi: `{error}`", ephemeral=True
            )

    @postpanel_prefix.error
    async def postpanel_prefix_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("❌ Bạn cần quyền **Administrator** để dùng lệnh này.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                "❌ Thiếu tham số. Cú pháp: `!postpanel <guild_id> <channel_id> <reply_channel_id>`"
            )
        else:
            logger.error(f"[POSTPANEL PREFIX ERROR] {error}", exc_info=True)
            await ctx.reply(f"❌ Lỗi: `{error}`")


# ══════════════════════════════════════════
#  SETUP
# ══════════════════════════════════════════

async def setup(bot: commands.Bot):
    await bot.add_cog(SupportHub(bot))
    logger.info("[SUPPORT-HUB] Cog loaded.")
