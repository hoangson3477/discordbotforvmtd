"""
support_hub.py — Discord.py Cog
Multi-guild support hub: panel, modals, forwarding, reply flow.
Storage: Supabase (persistent trên Railway).
Persistent views survive bot restart.

Supabase SQL cần chạy trước (1 lần duy nhất trong SQL Editor):
────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hub_guilds (
    guild_id         BIGINT PRIMARY KEY,
    panel_channel_id BIGINT NOT NULL,
    reply_channel_id BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS hub_submissions (
    sub_id           TEXT PRIMARY KEY,
    type             TEXT NOT NULL,
    guild_id         BIGINT NOT NULL,
    guild_name       TEXT NOT NULL,
    user_id          BIGINT NOT NULL,
    username         TEXT NOT NULL,
    reply_channel_id BIGINT NOT NULL,
    content          TEXT NOT NULL,
    replied          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
────────────────────────────────────────────────────────────────
"""

import discord
from discord.ext import commands
from discord import app_commands
import os
import uuid
import logging
import aiohttp

# ─────────────────────────────────────────
#  CONFIG — chỉnh 3 dòng này
# ─────────────────────────────────────────
HUB_GUILD_ID            = 1504540055153283092
HUB_SUPPORT_CHANNEL_ID  = 1504540147293618267
HUB_MESSAGE_CHANNEL_ID  = 1504540056000663585
# ─────────────────────────────────────────

logger = logging.getLogger("support_hub")


# ══════════════════════════════════════════
#  SUPABASE CLIENT (REST API qua aiohttp)
# ══════════════════════════════════════════

class SupabaseClient:
    """
    Wrapper nhẹ cho Supabase REST API.
    Không cần thêm lib — dùng aiohttp có sẵn trong bot.
    """

    def __init__(self, url: str, key: str, session: aiohttp.ClientSession):
        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self.session = session

    async def select(self, table: str, filters: dict = None) -> list[dict]:
        """SELECT với optional eq filters."""
        params = {}
        if filters:
            for k, v in filters.items():
                params[k] = f"eq.{v}"
        async with self.session.get(
            f"{self.base}/{table}", headers=self.headers, params=params
        ) as r:
            r.raise_for_status()
            return await r.json()

    async def upsert(self, table: str, data: dict) -> list[dict]:
        """INSERT hoặc UPDATE theo PK."""
        headers = {
            **self.headers,
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        async with self.session.post(
            f"{self.base}/{table}", headers=headers, json=data
        ) as r:
            r.raise_for_status()
            return await r.json()

    async def update(self, table: str, filters: dict, data: dict) -> list[dict]:
        """PATCH với eq filters."""
        params = {k: f"eq.{v}" for k, v in filters.items()}
        async with self.session.patch(
            f"{self.base}/{table}", headers=self.headers, params=params, json=data
        ) as r:
            r.raise_for_status()
            return await r.json()


# ── Module-level client, khởi tạo trong cog_load ──
_db: SupabaseClient | None = None


async def _get_submission(sub_id: str) -> dict | None:
    rows = await _db.select("hub_submissions", {"sub_id": sub_id})
    return rows[0] if rows else None


async def _mark_replied(sub_id: str) -> None:
    await _db.update("hub_submissions", {"sub_id": sub_id}, {"replied": True})


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
        sub = await _get_submission(self.sub_id)
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

        try:
            reply_channel = self.bot.get_channel(sub["reply_channel_id"])
            if reply_channel is None:
                reply_channel = await self.bot.fetch_channel(sub["reply_channel_id"])

            sub_type_label = "Hỗ trợ" if sub["type"] == "support" else "Tin nhắn"
            embed = discord.Embed(
                title=f"Phản hồi cho yêu cầu [{sub_type_label}]",
                description=self.reply_content.value,
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Mã submission",
                value=f"`{self.sub_id}`",
                inline=False,
            )
            embed.set_footer(text="Phản hồi từ Hub Support")

            await reply_channel.send(
                content=f"<@{sub['user_id']}>",
                embed=embed,
            )

            await _mark_replied(self.sub_id)
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


class HubSendModal(discord.ui.Modal, title="Gửi tin nhắn trực tiếp"):
    """Modal cho lệnh hubsend — nhập nội dung."""
    message_content = discord.ui.TextInput(
        label="Nội dung tin nhắn",
        style=discord.TextStyle.paragraph,
        placeholder="Nhập nội dung muốn gửi...",
        max_length=2000,
    )

    def __init__(self, bot: commands.Bot, target_guild_id: int, target_channel_id: int):
        super().__init__()
        self.bot = bot
        self.target_guild_id = target_guild_id
        self.target_channel_id = target_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_channel = self.bot.get_channel(self.target_channel_id)
            if target_channel is None:
                target_channel = await self.bot.fetch_channel(self.target_channel_id)

            target_guild = self.bot.get_guild(self.target_guild_id)
            guild_name = target_guild.name if target_guild else str(self.target_guild_id)

            embed = discord.Embed(
                title="📢 Tin nhắn từ Hub",
                description=self.message_content.value,
                color=discord.Color.gold(),
            )
            embed.set_footer(
                text=f"Gửi bởi {interaction.user} | Hub Admin",
                icon_url=interaction.user.display_avatar.url,
            )

            await target_channel.send(embed=embed)
            await interaction.response.send_message(
                f"✅ Đã gửi đến <#{self.target_channel_id}> (guild: `{guild_name}`).",
                ephemeral=True,
            )
            logger.info(
                f"[HUBSEND] {interaction.user} → guild {self.target_guild_id} "
                f"/ channel {self.target_channel_id}"
            )

        except discord.NotFound:
            await interaction.response.send_message(
                "❌ Không tìm thấy channel.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Bot không có quyền gửi tin vào channel đó.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"[HUBSEND MODAL ERROR] {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Lỗi: `{e}`", ephemeral=True
            )


# ══════════════════════════════════════════
#  PERSISTENT VIEWS
# ══════════════════════════════════════════

class PanelView(discord.ui.View):
    """
    Panel tại guild thành viên.
    reply_channel_id encode vào custom_id → survive restart không cần DB lookup.
    """

    def __init__(self, reply_channel_id: int):
        super().__init__(timeout=None)
        self.reply_channel_id = reply_channel_id

        support_btn = discord.ui.Button(
            label="🎫 Support",
            style=discord.ButtonStyle.primary,
            custom_id=f"panel_support_{reply_channel_id}",
        )
        support_btn.callback = self._support_callback
        self.add_item(support_btn)

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
    """Hub embed reply view. sub_id encode vào custom_id → survive restart."""

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
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Chỉ Administrator mới có thể trả lời.", ephemeral=True
            )
            return

        sub = await _get_submission(self.sub_id)
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
    """Tạo submission, lưu Supabase, forward lên hub."""
    sub_id = str(uuid.uuid4())[:8].upper()

    await _db.upsert("hub_submissions", {
        "sub_id": sub_id,
        "type": sub_type,
        "guild_id": interaction.guild.id,
        "guild_name": interaction.guild.name,
        "user_id": interaction.user.id,
        "username": str(interaction.user),
        "reply_channel_id": reply_channel_id,
        "content": content,
        "replied": False,
    })

    bot: commands.Bot = interaction.client
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
        bot.add_view(view)
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
    """Tìm hub embed theo sub_id và disable nút Reply."""
    try:
        bot: commands.Bot = interaction.client
        hub_guild = bot.get_guild(HUB_GUILD_ID)
        if not hub_guild:
            return

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
                    await msg.edit(
                        view=HubReplyView(sub_id=sub_id, bot=bot, disabled=True)
                    )
                    return
    except Exception as e:
        logger.warning(f"[DISABLE BUTTON] {e}")


# ══════════════════════════════════════════
#  COG
# ══════════════════════════════════════════

class SupportHub(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Khởi tạo Supabase client và đăng ký persistent views từ DB."""
        global _db

        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        if not supabase_url or not supabase_key:
            raise EnvironmentError(
                "Thiếu SUPABASE_URL hoặc SUPABASE_KEY trong .env"
            )

        # Dùng lại aiohttp session của bot nếu có, fallback tạo mới
        session = getattr(self.bot, "http_session", None) or aiohttp.ClientSession()
        _db = SupabaseClient(supabase_url, supabase_key, session)

        # 1) Panel views từ hub_guilds
        registered: set[int] = set()
        try:
            guilds = await _db.select("hub_guilds")
            for g in guilds:
                rch = g["reply_channel_id"]
                if rch not in registered:
                    self.bot.add_view(PanelView(reply_channel_id=rch))
                    registered.add(rch)
        except Exception as e:
            logger.error(f"[SUPPORT-HUB] Load hub_guilds thất bại: {e}", exc_info=True)

        # 2) Hub reply views từ hub_submissions
        sub_count = 0
        try:
            submissions = await _db.select("hub_submissions")
            for sub in submissions:
                self.bot.add_view(
                    HubReplyView(
                        sub_id=sub["sub_id"],
                        bot=self.bot,
                        disabled=sub.get("replied", False),
                    )
                )
                sub_count += 1
        except Exception as e:
            logger.error(f"[SUPPORT-HUB] Load hub_submissions thất bại: {e}", exc_info=True)

        logger.info(
            f"[SUPPORT-HUB] Registered {len(registered)} panel view(s), "
            f"{sub_count} hub reply view(s)."
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
        ping_role_id="(Tuỳ chọn) ID role sẽ được ping khi gửi panel",
    )
    async def postpanel_slash(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        channel_id: str,
        reply_channel_id: str,
        ping_role_id: str = None,
    ):
        await interaction.response.defer(ephemeral=True)
        result = await self._do_postpanel(
            int(guild_id), int(channel_id), int(reply_channel_id),
            ping_role_id=int(ping_role_id) if ping_role_id else None,
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
        ping_role_id: int = None,
    ):
        result = await self._do_postpanel(
            guild_id, channel_id, reply_channel_id, ping_role_id=ping_role_id
        )
        await ctx.reply(result)

    async def _do_postpanel(
        self,
        guild_id: int,
        channel_id: int,
        reply_channel_id: int,
        ping_role_id: int = None,
    ) -> str:
        target_guild = self.bot.get_guild(guild_id)
        if not target_guild:
            return (
                f"❌ Bot không có trong guild `{guild_id}`. "
                "Hãy mời bot vào guild đó trước."
            )

        target_channel = target_guild.get_channel(channel_id)
        if not target_channel:
            try:
                target_channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                return f"❌ Không tìm thấy channel `{channel_id}` trong guild `{guild_id}`."
            except discord.Forbidden:
                return f"❌ Bot không có quyền truy cập channel `{channel_id}`."

        ping_role = None
        if ping_role_id:
            ping_role = target_guild.get_role(ping_role_id)
            if not ping_role:
                return f"❌ Không tìm thấy role `{ping_role_id}` trong guild `{target_guild.name}`."

        # Lưu vào Supabase
        try:
            await _db.upsert("hub_guilds", {
                "guild_id": guild_id,
                "panel_channel_id": channel_id,
                "reply_channel_id": reply_channel_id,
            })
        except Exception as e:
            logger.error(f"[POSTPANEL DB ERROR] {e}", exc_info=True)
            return f"❌ Lỗi lưu DB: `{e}`"

        embed = discord.Embed(
            title="Support/Message Hub",
            description=(
                "Trong khoảng tgian bloxshit cai game làm đồ án thì ae có hỗ trợ gì thì như dưới. Mọi tin nhắn sẽ về Zalo thg bloxshit (not discord)\n\n"
                "• **Support** — Mở ticket hỗ trợ về vấn đề con RoVMTD\n"
                "• **Message** — Gửi tin nhắn về Zalo cho thg bloxshit (do bloxshit cai discord + code không thèm vào dis lấy ttin fr)"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Nhấn nút bên dưới để bắt đầu")

        view = PanelView(reply_channel_id=reply_channel_id)
        self.bot.add_view(view)

        try:
            await target_channel.send(
                content=ping_role.mention if ping_role else None,
                embed=embed,
                view=view,
                allowed_mentions=(
                    discord.AllowedMentions(roles=True)
                    if ping_role
                    else discord.AllowedMentions.none()
                ),
            )
        except discord.Forbidden:
            return f"❌ Bot không có quyền gửi tin vào channel `{channel_id}`."
        except Exception as e:
            logger.error(f"[POSTPANEL ERROR] {e}", exc_info=True)
            return f"❌ Lỗi: `{e}`"

        ping_info = f" (đã ping {ping_role.mention})" if ping_role else ""
        return (
            f"✅ Đã gửi panel vào <#{channel_id}> (guild: `{target_guild.name}`){ping_info}. "
            f"Reply channel: <#{reply_channel_id}>"
        )

    # ──────────────────────────────────────
    #  /hubsend  (slash)
    # ──────────────────────────────────────
    @app_commands.command(
        name="hubsend",
        description="[Hub Admin] Gửi tin nhắn trực tiếp đến channel trong guild bất kỳ",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        guild_id="ID của guild đích",
        channel_id="ID của channel đích",
    )
    async def hubsend_slash(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        channel_id: str,
    ):
        # Chỉ dùng được trong hub guild
        if interaction.guild_id != HUB_GUILD_ID:
            await interaction.response.send_message(
                "❌ Lệnh này chỉ dùng được trong Hub Guild.", ephemeral=True
            )
            return

        target_guild = self.bot.get_guild(int(guild_id))
        if not target_guild:
            await interaction.response.send_message(
                f"❌ Bot không có trong guild `{guild_id}`.", ephemeral=True
            )
            return

        # Verify channel trước khi mở modal
        target_channel = target_guild.get_channel(int(channel_id))
        if not target_channel:
            try:
                target_channel = await self.bot.fetch_channel(int(channel_id))
            except discord.NotFound:
                await interaction.response.send_message(
                    f"❌ Không tìm thấy channel `{channel_id}`.", ephemeral=True
                )
                return
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"❌ Bot không có quyền truy cập channel `{channel_id}`.", ephemeral=True
                )
                return

        await interaction.response.send_modal(
            HubSendModal(
                bot=self.bot,
                target_guild_id=int(guild_id),
                target_channel_id=int(channel_id),
            )
        )

    # ──────────────────────────────────────
    #  !hubsend  (prefix)
    # ──────────────────────────────────────
    @commands.command(name="hubsend")
    @commands.has_permissions(administrator=True)
    async def hubsend_prefix(
        self,
        ctx: commands.Context,
        guild_id: int,
        channel_id: int,
        *,
        message: str,
    ):
        """Cú pháp: !hubsend <guild_id> <channel_id> <nội dung>"""
        if ctx.guild.id != HUB_GUILD_ID:
            await ctx.reply("❌ Lệnh này chỉ dùng được trong Hub Guild.")
            return

        target_guild = self.bot.get_guild(guild_id)
        if not target_guild:
            await ctx.reply(f"❌ Bot không có trong guild `{guild_id}`.")
            return

        target_channel = target_guild.get_channel(channel_id)
        if not target_channel:
            try:
                target_channel = await self.bot.fetch_channel(channel_id)
            except discord.NotFound:
                await ctx.reply(f"❌ Không tìm thấy channel `{channel_id}`.")
                return
            except discord.Forbidden:
                await ctx.reply(f"❌ Bot không có quyền truy cập channel `{channel_id}`.")
                return

        try:
            embed = discord.Embed(
                title="📢 Tin nhắn từ Hub",
                description=message,
                color=discord.Color.gold(),
            )
            embed.set_footer(
                text=f"Gửi bởi {ctx.author} | Hub Admin",
                icon_url=ctx.author.display_avatar.url,
            )
            await target_channel.send(embed=embed)
            await ctx.reply(
                f"✅ Đã gửi đến <#{channel_id}> (guild: `{target_guild.name}`)."
            )
            logger.info(
                f"[HUBSEND] {ctx.author} → guild {guild_id} / channel {channel_id}"
            )
        except discord.Forbidden:
            await ctx.reply("❌ Bot không có quyền gửi tin vào channel đó.")
        except Exception as e:
            logger.error(f"[HUBSEND PREFIX ERROR] {e}", exc_info=True)
            await ctx.reply(f"❌ Lỗi: `{e}`")

    # ──────────────────────────────────────
    #  Error handlers
    # ──────────────────────────────────────
    @postpanel_slash.error
    async def postpanel_slash_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Bạn cần quyền **Administrator**.", ephemeral=True
            )
        else:
            logger.error(f"[POSTPANEL SLASH ERROR] {error}", exc_info=True)
            await interaction.response.send_message(f"❌ Lỗi: `{error}`", ephemeral=True)

    @postpanel_prefix.error
    async def postpanel_prefix_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("❌ Bạn cần quyền **Administrator**.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                "❌ Thiếu tham số. Cú pháp: `!postpanel <guild_id> <channel_id> <reply_channel_id> [ping_role_id]`"
            )
        else:
            logger.error(f"[POSTPANEL PREFIX ERROR] {error}", exc_info=True)
            await ctx.reply(f"❌ Lỗi: `{error}`")

    @hubsend_slash.error
    async def hubsend_slash_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ Bạn cần quyền **Administrator**.", ephemeral=True
            )
        else:
            logger.error(f"[HUBSEND SLASH ERROR] {error}", exc_info=True)
            await interaction.response.send_message(f"❌ Lỗi: `{error}`", ephemeral=True)

    @hubsend_prefix.error
    async def hubsend_prefix_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("❌ Bạn cần quyền **Administrator**.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                "❌ Thiếu tham số. Cú pháp: `!hubsend <guild_id> <channel_id> <nội dung>`"
            )
        else:
            logger.error(f"[HUBSEND PREFIX ERROR] {error}", exc_info=True)
            await ctx.reply(f"❌ Lỗi: `{error}`")


# ══════════════════════════════════════════
#  SETUP
# ══════════════════════════════════════════

async def setup(bot: commands.Bot):
    await bot.add_cog(SupportHub(bot))
    logger.info("[SUPPORT-HUB] Cog loaded.")