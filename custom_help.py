import discord
from discord.ext import commands
import logging

log = logging.getLogger('my_bot')


class CustomHelpCommand(commands.HelpCommand):
    """
    Custom Help Command để trình bày các lệnh của bot một cách đẹp mắt bằng Embeds.
    """

    EMBED_COLOR = discord.Color.blue()

    # ──────────────────────────────────────────
    # Helpers dùng chung
    # ──────────────────────────────────────────

    def _base_embed(self, title: str, description: str = "") -> discord.Embed:
        """Tạo embed cơ bản với thumbnail và footer."""
        bot = self.context.bot
        author = self.context.author

        embed = discord.Embed(title=title, description=description, color=self.EMBED_COLOR)
        embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else None)
        embed.set_footer(
            text=f"Prefix: {self.context.clean_prefix} | Yêu cầu bởi: {author.name}",
            icon_url=author.avatar.url if author.avatar else None,
        )
        return embed

    async def _send_fields_paginated(
        self,
        fields: list[tuple[str, str]],
        base_title: str,
        description: str = "",
    ) -> None:
        """
        Gửi danh sách fields dưới dạng embed, tự động chia trang nếu > 25 fields.
        base_title: tiêu đề không có phần "(Trang x/y)".
        """
        chunk_size = 25
        pages = [fields[i : i + chunk_size] for i in range(0, len(fields), chunk_size)]
        total = len(pages)

        for i, page in enumerate(pages, 1):
            title = base_title if total == 1 else f"{base_title} (Trang {i}/{total})"
            embed = self._base_embed(title, description)
            for name, value in page:
                embed.add_field(name=name, value=value, inline=False)
            await self.get_destination().send(embed=embed)

    # ──────────────────────────────────────────
    # send_bot_help
    # ──────────────────────────────────────────

    async def send_bot_help(self, mapping) -> None:
        """Gửi danh sách tất cả lệnh (khi người dùng gõ !help)."""
        prefix = self.context.clean_prefix
        description = (
            f"Sử dụng `{prefix}help <lệnh>` để xem chi tiết về một lệnh cụ thể.\n"
            f"Ví dụ: `{prefix}help addpoint`\n\n"
        )

        fields: list[tuple[str, str]] = []
        for cog, cmds in mapping.items():
            visible = await self.filter_commands(cmds, sort=True)
            if not visible:
                continue

            cog_name = cog.qualified_name if cog else "Lệnh Chung"
            prefix_cmds = [
                f"`{prefix}{cmd.name}`"
                for cmd in visible
                if isinstance(cmd, commands.Command)
            ]
            slash_cmds = [
                f"`/{cmd.name}`"
                for cmd in visible
                if isinstance(cmd, discord.app_commands.Command)
            ]

            parts = []
            if prefix_cmds:
                parts.append(f"**Lệnh Tiền Tố:** {', '.join(prefix_cmds)}")
            if slash_cmds:
                parts.append(f"**Slash Commands:** {', '.join(slash_cmds)}")

            if parts:
                fields.append((cog_name, "\n".join(parts)))

        await self._send_fields_paginated(fields, "📚 Danh Sách Lệnh Của Bot", description)

    # ──────────────────────────────────────────
    # send_cog_help
    # ──────────────────────────────────────────

    async def send_cog_help(self, cog) -> None:
        """Gửi danh sách lệnh trong một cog cụ thể."""
        visible = await self.filter_commands(cog.get_commands(), sort=True)
        if not visible:
            return

        prefix = self.context.clean_prefix
        fields = [
            (f"`{prefix}{cmd.name}`", cmd.help or "Không có mô tả.")
            for cmd in visible
        ]
        await self._send_fields_paginated(
            fields,
            f"📚 Lệnh trong {cog.qualified_name}",
            cog.description or "Không có mô tả cho cog này.",
        )

    # ──────────────────────────────────────────
    # send_command_help
    # ──────────────────────────────────────────

    async def send_command_help(self, command) -> None:
        """Gửi chi tiết về một lệnh cụ thể (khi người dùng gõ !help <tên_lệnh>)."""
        embed = self._base_embed(
            f"📖 Trợ Giúp Lệnh: `{command.name}`",
            command.help or "Không có mô tả chi tiết cho lệnh này.",
        )

        if isinstance(command, commands.Command):
            prefix = self.context.clean_prefix
            embed.add_field(
                name="Cách Dùng (Prefix):",
                value=f"`{prefix}{command.name} {command.signature}`",
                inline=False,
            )

            examples = self._extract_examples_from_help(command.help)
            if examples:
                embed.add_field(
                    name="Ví Dụ (Prefix):",
                    value="\n".join(f"`{ex}`" for ex in examples),
                    inline=False,
                )

            embed.add_field(
                name="Aliases:",
                value=f"`{', '.join(command.aliases)}`" if command.aliases else "Không có",
                inline=False,
            )

            # Dùng set để tra cứu O(1) thay vì vòng lặp O(n)
            slash_names = {cmd.name for cmd in self.context.bot.tree.get_commands()}
            slash_info = f"Có: `/{command.name}`" if command.name in slash_names else "Không"
            embed.add_field(name="Slash Command Tương Ứng:", value=slash_info, inline=False)

        elif isinstance(command, discord.app_commands.Command):
            options = []
            for param in command.parameters:
                if param.required:
                    suffix = " (bắt buộc)"
                elif param.default is not discord.app_commands.MISSING:
                    suffix = f" (mặc định: {param.default})"
                else:
                    suffix = ""
                options.append(f"`<{param.name}: {param.description or 'Không mô tả'}{suffix}>`")

            embed.add_field(
                name="Cách Dùng (Slash):",
                value=f"`/{command.name} {' '.join(options)}`",
                inline=False,
            )

        await self.get_destination().send(embed=embed)

    # ──────────────────────────────────────────
    # send_group_help
    # ──────────────────────────────────────────

    async def send_group_help(self, group) -> None:
        """Gửi danh sách các lệnh trong một nhóm lệnh."""
        # filter_commands để ẩn các lệnh không có quyền truy cập
        visible = await self.filter_commands(group.commands, sort=True)
        if not visible:
            return

        prefix = self.context.clean_prefix
        fields = [
            (f"`{prefix}{cmd.qualified_name}`", cmd.short_doc or "Không có mô tả.")
            for cmd in visible
        ]
        await self._send_fields_paginated(
            fields,
            f"📚 Trợ Giúp Nhóm Lệnh: `{group.name}`",
            group.help or "Không có mô tả cho nhóm lệnh này.",
        )

    # ──────────────────────────────────────────
    # send_error_message
    # ──────────────────────────────────────────

    async def send_error_message(self, error: str) -> None:
        """Gửi thông báo lỗi khi không tìm thấy lệnh."""
        embed = discord.Embed(
            title="❌ Không Tìm Thấy Lệnh",
            description=error,
            color=discord.Color.red(),
        )
        embed.set_footer(
            text=f"Thử `{self.context.clean_prefix}help` để xem danh sách lệnh."
        )
        await self.get_destination().send(embed=embed)

    # ──────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────

    def _extract_examples_from_help(self, help_string: str) -> list[str]:
        """
        Trích xuất các ví dụ từ chuỗi help của lệnh.
        Giả định các ví dụ nằm sau dòng "Ví dụ:" và bắt đầu bằng ! hoặc /.
        """
        if not help_string:
            return []

        examples: list[str] = []
        in_examples = False

        for line in help_string.split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith("ví dụ:"):
                in_examples = True
                continue
            if in_examples:
                if not stripped or stripped.lower().startswith("cách dùng:"):
                    break
                if stripped.startswith("!") or stripped.startswith("/"):
                    examples.append(stripped)

        return examples


async def setup(bot):
    bot.help_command = CustomHelpCommand()
    log.info("CustomHelpCommand đã được thiết lập.")