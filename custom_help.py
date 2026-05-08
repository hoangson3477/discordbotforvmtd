import discord
from discord.ext import commands
import logging

log = logging.getLogger('my_bot')

class CustomHelpCommand(commands.HelpCommand):
    """
    Custom Help Command để trình bày các lệnh của bot một cách đẹp mắt bằng Embeds.
    """

    # Màu sắc cho embed, có thể tùy chỉnh
    EMBED_COLOR = discord.Color.blue() # Hoặc một màu khác bạn thích

    async def send_bot_help(self, mapping):
        """
        Gửi tin nhắn trợ giúp chung (khi người dùng chỉ gõ !help).
        """
        # Thu thập tất cả cog data trước
        cog_data = []
        for cog in mapping.keys():
            commands_in_cog = await self.filter_commands(mapping[cog], sort=True)
            if commands_in_cog: # Chỉ hiển thị cog nếu có lệnh có thể truy cập
                name = cog.qualified_name if cog else "Lệnh Chung"
                
                # Thu thập các lệnh tiền tố và slash command cho cog này
                prefix_commands = []
                slash_commands = []
                for command in commands_in_cog:
                    if isinstance(command, commands.Command): # Lệnh tiền tố
                        prefix_commands.append(f"`{self.context.clean_prefix}{command.name}`")
                    elif isinstance(command, discord.app_commands.Command): # Slash command
                        slash_commands.append(f"`/{command.name}`")

                commands_str = ""
                if prefix_commands:
                    commands_str += f"**Lệnh Tiền Tố:** {', '.join(prefix_commands)}\n"
                if slash_commands:
                    commands_str += f"**Slash Commands:** {', '.join(slash_commands)}\n"
                
                if commands_str:
                    cog_data.append((name, commands_str))

        # Nếu có quá nhiều cog, chia thành nhiều embed
        if len(cog_data) <= 25:
            # Gửi trong một embed
            embed = discord.Embed(
                title="📚 Danh Sách Lệnh Của Bot",
                description="Sử dụng `!help <lệnh>` để xem chi tiết về một lệnh cụ thể.\n"
                            "Ví dụ: `!help addpoint`\n\n",
                color=self.EMBED_COLOR
            )
            embed.set_thumbnail(url=self.context.bot.user.avatar.url if self.context.bot.user.avatar else None)
            embed.set_footer(text=f"Prefix: {self.context.clean_prefix} | Yêu cầu bởi: {self.context.author.name}", 
                             icon_url=self.context.author.avatar.url if self.context.author.avatar else None)

            for name, commands_str in cog_data:
                embed.add_field(name=name, value=commands_str, inline=False)

            await self.get_destination().send(embed=embed)
        else:
            # Chia thành nhiều embed
            await self._send_paginated_help(cog_data)

    async def _send_paginated_help(self, cog_data):
        """
        Gửi tin nhắn trợ giúp chung nhưng chia thành nhiều trang.
        """
        pages = []
        current_page = []
        for name, commands_str in cog_data:
            if len(current_page) >= 25:
                pages.append(current_page)
                current_page = []
            current_page.append((name, commands_str))
        if current_page:
            pages.append(current_page)

        for i, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title=f"📚 Danh Sách Lệnh Của Bot (Trang {i}/{len(pages)})",
                description="Sử dụng `!help <lệnh>` để xem chi tiết về một lệnh cụ thể.\n"
                            "Ví dụ: `!help addpoint`\n\n",
                color=self.EMBED_COLOR
            )
            embed.set_thumbnail(url=self.context.bot.user.avatar.url if self.context.bot.user.avatar else None)
            embed.set_footer(text=f"Prefix: {self.context.clean_prefix} | Yêu cầu bởi: {self.context.author.name}", 
                             icon_url=self.context.author.avatar.url if self.context.author.avatar else None)

            for name, commands_str in page:
                embed.add_field(name=name, value=commands_str, inline=False)

            await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog):
        """
        Gửi tin nhắn trợ giúp cho một cog cụ thể (nếu có).
        (Hiện tại chúng ta không có lệnh `!help <cog_name>`, nên hàm này có thể không được gọi trực tiếp,
        nhưng tốt nhất là vẫn định nghĩa).
        """
        commands_in_cog = await self.filter_commands(cog.get_commands(), sort=True)
        if not commands_in_cog:
            return # Không có lệnh nào để hiển thị trong cog này

        # Giới hạn số lệnh hiển thị để tránh vượt quá 25 fields
        if len(commands_in_cog) <= 25:
            embed = discord.Embed(
                title=f"📚 Lệnh trong {cog.qualified_name}",
                description=cog.description or "Không có mô tả cho cog này.",
                color=self.EMBED_COLOR
            )
            for command in commands_in_cog:
                embed.add_field(name=f"`{self.context.clean_prefix}{command.name}`",
                                value=command.help or "Không có mô tả.",
                                inline=False)
            embed.set_footer(text=f"Prefix: {self.context.clean_prefix} | Yêu cầu bởi: {self.context.author.name}", 
                             icon_url=self.context.author.avatar.url if self.context.author.avatar else None)
            await self.get_destination().send(embed=embed)
        else:
            # Chia thành nhiều trang nếu quá nhiều lệnh
            await self._send_paginated_cog_help(cog, commands_in_cog)

    async def _send_paginated_cog_help(self, cog, commands_in_cog):
        """
        Gửi tin nhắn trợ giúp cho một cog cụ thể nhưng chia thành nhiều trang.
        """
        pages = []
        current_page = []
        for command in commands_in_cog:
            if len(current_page) >= 25:
                pages.append(current_page)
                current_page = []
            current_page.append(command)
        if current_page:
            pages.append(current_page)

        for i, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title=f"📚 Lệnh trong {cog.qualified_name} (Trang {i}/{len(pages)})",
                description=cog.description or "Không có mô tả cho cog này.",
                color=self.EMBED_COLOR
            )
            for command in page:
                embed.add_field(name=f"`{self.context.clean_prefix}{command.name}`",
                                value=command.help or "Không có mô tả.",
                                inline=False)
            embed.set_footer(text=f"Prefix: {self.context.clean_prefix} | Yêu cầu bởi: {self.context.author.name}", 
                             icon_url=self.context.author.avatar.url if self.context.author.avatar else None)
            await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        """
        Gửi tin nhắn trợ giúp cho một lệnh cụ thể (khi người dùng gõ !help <tên_lệnh>).
        """
        embed = discord.Embed(
            title=f"📖 Trợ Giúp Lệnh: `{command.name}`",
            description=command.help or "Không có mô tả chi tiết cho lệnh này.",
            color=self.EMBED_COLOR
        )
        embed.set_footer(text=f"Prefix: {self.context.clean_prefix} | Yêu cầu bởi: {self.context.author.name}", 
                         icon_url=self.context.author.avatar.url if self.context.author.avatar else None)

        # Kiểm tra nếu là lệnh tiền tố
        if isinstance(command, commands.Command):
            usage = f"`{self.context.clean_prefix}{command.name} {command.signature}`"
            embed.add_field(name="Cách Dùng (Prefix):", value=usage, inline=False)
            
            # Thêm ví dụ nếu có (cần parse từ command.help)
            examples = self._extract_examples_from_help(command.help)
            if examples:
                embed.add_field(name="Ví Dụ (Prefix):", value="\n".join(f"`{ex}`" for ex in examples), inline=False)
            
            embed.add_field(name="Aliases:", value=f"`{', '.join(command.aliases)}`" if command.aliases else "Không có", inline=False)
            
            # Kiểm tra xem có slash command tương ứng không
            slash_command_exists = False
            for app_cmd in self.context.bot.tree.get_commands():
                if app_cmd.name == command.name:
                    slash_command_exists = True
                    break
            if slash_command_exists:
                embed.add_field(name="Slash Command Tương Ứng:", value=f"Có: `/{command.name}`", inline=False)
            else:
                embed.add_field(name="Slash Command Tương Ứng:", value="Không", inline=False)

        # Kiểm tra nếu là slash command (discord.app_commands.Command)
        elif isinstance(command, discord.app_commands.Command):
            usage_options = []
            for param in command.parameters:
                required_str = ""
                if param.required:
                    required_str = " (bắt buộc)"
                elif param.default is not discord.app_commands.MISSING:
                    required_str = f" (mặc định: {param.default})"
                
                usage_options.append(f"`<{param.name}: {param.description or 'Không mô tả'}{required_str}>`")
            
            usage = f"`/{command.name} {' '.join(usage_options)}`"
            embed.add_field(name="Cách Dùng (Slash):", value=usage, inline=False)

            # Slash commands không có aliases hay mô tả ví dụ trong .help string theo cách prefix command
            # Bạn có thể tự thêm một trường 'examples' vào Slash command nếu muốn
        
        await self.get_destination().send(embed=embed)


    async def send_group_help(self, group):
        """
        Gửi tin nhắn trợ giúp cho một nhóm lệnh (chưa có trong bot hiện tại).
        """
        commands_in_group = group.commands
        if not commands_in_group:
            return

        # Giới hạn số lệnh hiển thị để tránh vượt quá 25 fields
        if len(commands_in_group) <= 25:
            embed = discord.Embed(
                title=f"📚 Trợ Giúp Nhóm Lệnh: `{group.name}`",
                description=group.help or "Không có mô tả cho nhóm lệnh này.",
                color=self.EMBED_COLOR
            )
            for command in commands_in_group:
                embed.add_field(name=f"`{self.context.clean_prefix}{command.qualified_name}`",
                                value=command.short_doc or "Không có mô tả.",
                                inline=False)
            embed.set_footer(text=f"Prefix: {self.context.clean_prefix} | Yêu cầu bởi: {self.context.author.name}", 
                             icon_url=self.context.author.avatar.url if self.context.author.avatar else None)
            await self.get_destination().send(embed=embed)
        else:
            # Chia thành nhiều trang nếu quá nhiều lệnh
            await self._send_paginated_group_help(group, commands_in_group)

    async def _send_paginated_group_help(self, group, commands_in_group):
        """
        Gửi tin nhắn trợ giúp cho một nhóm lệnh nhưng chia thành nhiều trang.
        """
        pages = []
        current_page = []
        for command in commands_in_group:
            if len(current_page) >= 25:
                pages.append(current_page)
                current_page = []
            current_page.append(command)
        if current_page:
            pages.append(current_page)

        for i, page in enumerate(pages, start=1):
            embed = discord.Embed(
                title=f"📚 Trợ Giúp Nhóm Lệnh: `{group.name}` (Trang {i}/{len(pages)})",
                description=group.help or "Không có mô tả cho nhóm lệnh này.",
                color=self.EMBED_COLOR
            )
            for command in page:
                embed.add_field(name=f"`{self.context.clean_prefix}{command.qualified_name}`",
                                value=command.short_doc or "Không có mô tả.",
                                inline=False)
            embed.set_footer(text=f"Prefix: {self.context.clean_prefix} | Yêu cầu bởi: {self.context.author.name}", 
                             icon_url=self.context.author.avatar.url if self.context.author.avatar else None)
            await self.get_destination().send(embed=embed)
    
    def _extract_examples_from_help(self, help_string: str) -> list[str]:
        """
        Trích xuất các ví dụ từ chuỗi help của lệnh.
        Giả định các ví dụ nằm sau "Ví dụ:" và mỗi ví dụ nằm trên một dòng mới.
        """
        if not help_string:
            return []
        
        lines = help_string.split('\n')
        examples_found = False
        examples = []
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.lower().startswith("ví dụ:"):
                examples_found = True
                continue
            if examples_found:
                if stripped_line:
                    # Loại bỏ "Cách dùng:" hoặc bất kỳ dòng không phải ví dụ nào sau "Ví dụ:"
                    if stripped_line.lower().startswith("cách dùng:"):
                        break
                    # Ví dụ: !addpoint bloxfrui,abinll,cgg BT 100
                    # Chúng ta chỉ muốn "bloxfrui,abinll,cgg BT 100" hoặc toàn bộ lệnh nếu cần
                    # Để đơn giản, cứ lấy toàn bộ dòng có ! hoặc /
                    if stripped_line.startswith("!") or stripped_line.startswith("/"):
                        examples.append(stripped_line)
                else: # Dòng trống, kết thúc phần ví dụ
                    break
        return examples


async def setup(bot):
    # Thay thế lệnh help mặc định của bot bằng CustomHelpCommand
    bot.help_command = CustomHelpCommand()
    log.info("CustomHelpCommand đã được thiết lập.")