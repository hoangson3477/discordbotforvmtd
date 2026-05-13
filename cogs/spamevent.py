import discord
from discord.ext import commands
import asyncio

ALLOWED_ROLES = [
    1413571646501027861,
    1413571707062452275,
    904258043112480779,
    1413571594223222804,
    897810289234411550,
    1401565217087033456
]

SPAM_TIMES = 100
SPAM_DELAY = 1  # giây


class SpamEvent(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_spams = {}  # user_id : asyncio.Task

    def has_allowed_role(self, member: discord.Member) -> bool:
        return any(r.id in ALLOWED_ROLES for r in member.roles)

    def extract_targets(self, ctx, targets):
        users = set()

        for target in targets:
            if isinstance(target, discord.Member):
                if not target.bot:
                    users.add(target)
            elif isinstance(target, discord.Role):
                for m in target.members:
                    if not m.bot:
                        users.add(m)

        return list(users)

    def parse_message(self, ctx) -> str:
        """
        FIX #2: Parse nội dung tin nhắn chính xác bằng cách loại bỏ
        prefix lệnh và tất cả các mention (dạng <@id>, <@!id>, <@&id>)
        thay vì split theo số lượng targets (dễ bị lệch).
        """
        import re
        content = ctx.message.content
        # Xóa prefix + tên lệnh (vd: "!spam ")
        content = content.split(maxsplit=1)[1] if ' ' in content else ''
        # Xóa toàn bộ mention user/role
        content = re.sub(r'<@[!&]?\d+>', '', content).strip()
        return content

    @commands.command(name="spam")
    async def spam(self, ctx, *args):
        if not self.has_allowed_role(ctx.author):
            return await ctx.reply("Bạn không có quyền dùng lệnh này.")

        targets = ctx.message.mentions + ctx.message.role_mentions

        # FIX #2: Dùng parse_message thay vì split theo len(targets)
        message = self.parse_message(ctx)

        if not targets or not message:
            return await ctx.reply("Cú pháp: `!spam @user/@role <nội dung>`")

        users = self.extract_targets(ctx, targets)
        if not users:
            return await ctx.reply("Không có user hợp lệ để spam.")

        status_msg = await ctx.send(
            f"**BẮT ĐẦU SPAM EVENT**\n"
            f"Tổng người nhận: **{len(users)}**\n"
            f"Đang chuẩn bị..."
        )

        async def spam_task(member: discord.Member) -> int:
            sent = 0
            try:
                for _ in range(SPAM_TIMES):
                    await member.send(message)
                    sent += 1
                    await asyncio.sleep(SPAM_DELAY)
            except discord.Forbidden:
                pass
            except asyncio.CancelledError:
                # Trả về số đã gửi trước khi bị cancel
                pass
            return sent

        # Chỉ tạo task cho user chưa có spam đang chạy
        tasks: list[tuple[discord.Member, asyncio.Task]] = []
        for member in users:
            if member.id in self.active_spams:
                continue
            task = asyncio.create_task(spam_task(member))
            self.active_spams[member.id] = task
            tasks.append((member, task))

        if not tasks:
            return await status_msg.edit(content="Tất cả user đang có spam chạy rồi.")

        # FIX #1: Dùng asyncio.gather thay vì as_completed để giữ đúng
        # mapping member ↔ task. as_completed trả về wrapper futures mới
        # nên không thể so sánh với task gốc để tìm member tương ứng.
        completed = 0
        total_sent = 0

        raw_tasks = [t for _, t in tasks]
        results = await asyncio.gather(*raw_tasks, return_exceptions=True)

        for (member, _), result in zip(tasks, results):
            # FIX #4: Cleanup active_spams dù task thành công hay lỗi
            self.active_spams.pop(member.id, None)
            completed += 1

            if isinstance(result, Exception):
                sent_count = 0
            else:
                sent_count = result or 0

            total_sent += sent_count

            await status_msg.edit(
                content=(
                    f"**ĐANG SPAM EVENT**\n"
                    f"Vừa xong: `{member}`\n"
                    f"Completed: **{completed}/{len(tasks)}**\n"
                    f"Tổng DM đã gửi: **{total_sent}**"
                )
            )

        await status_msg.edit(
            content=(
                f"**SPAM HOÀN TẤT**\n"
                f"Tổng người nhận: **{len(tasks)}**\n"
                f"Tổng DM đã gửi: **{total_sent}**"
            )
        )

    @commands.command(name="stopspam")
    async def stopspam(self, ctx, *targets):
        if not self.has_allowed_role(ctx.author):
            return await ctx.reply("Bạn không có quyền dùng lệnh này.")

        if not targets:
            return await ctx.reply("Cú pháp: `!stopspam @user/@role`")

        stop_users = set()

        for user in ctx.message.mentions:
            stop_users.add(user.id)

        for role in ctx.message.role_mentions:
            for member in role.members:
                stop_users.add(member.id)

        if not stop_users:
            return await ctx.reply("Không tìm thấy user hợp lệ để dừng spam.")

        stopped = 0

        for uid in stop_users:
            task = self.active_spams.get(uid)
            if task and not task.cancelled() and not task.done():
                task.cancel()
                stopped += 1

            # FIX #5: Xóa khỏi active_spams ngay sau khi cancel,
            # tránh block lần spam tiếp theo cho cùng member.
            self.active_spams.pop(uid, None)

        await ctx.reply(f"🛑 Đã dừng spam cho **{stopped}** người.")

    @commands.command(name="stopall")
    async def stopall(self, ctx):
        if not self.has_allowed_role(ctx.author):
            return await ctx.reply("Bạn không có quyền dùng lệnh này.")

        if not self.active_spams:
            return await ctx.reply("Hiện không có tác vụ spam nào đang chạy.")

        stopped = 0

        for uid, task in list(self.active_spams.items()):
            if task and not task.done():
                task.cancel()
                stopped += 1

        self.active_spams.clear()

        await ctx.reply(f"🛑 Đã dừng toàn bộ spam đang chạy (**{stopped}** tác vụ).")

    @commands.command(name="checkblock")
    async def checkblock(self, ctx, role: discord.Role = None):
        if not self.has_allowed_role(ctx.author):
            return await ctx.reply("Bạn không có quyền dùng lệnh này.")

        if not role:
            return await ctx.reply("Cú pháp: `!checkblock @role`")

        members = [m for m in role.members if not m.bot]

        if not members:
            return await ctx.reply("Role này không có member hợp lệ.")

        status = await ctx.send(
            f"🔍 Đang kiểm tra DM cho role **{role.name}**...\n"
            f"Tổng kiểm tra: **{len(members)}**"
        )

        can_receive = 0
        blocked_members = []

        # FIX #3: Thay vì gửi DM thật rồi xóa (user vẫn nhận notification),
        # dùng create_dm() để mở kênh DM mà không gửi tin nhắn nào.
        # Nếu user tắt DM → create_dm vẫn thành công nhưng send sẽ raise Forbidden,
        # nên ta vẫn cần thử gửi 1 tin — dùng fetch_user để kiểm tra qua API
        # là cách an toàn nhất hiện tại với discord.py.
        # Giải pháp thực tế: gửi tin nhắn kiểm tra nhưng chọn nội dung trung tính,
        # và xóa ngay — đây là cách duy nhất discord.py hỗ trợ kiểm tra DM.
        # (Không có API nào của Discord cho phép check khả năng DM mà không gửi)
        for index, member in enumerate(members, 1):
            try:
                dm = await member.create_dm()
                # Gửi tin nhắn kiểm tra ngắn gọn, xóa ngay lập tức
                msg = await dm.send("📋 Bot đang kiểm tra kết nối DM — tin nhắn này sẽ tự xóa.")
                await msg.delete()
                can_receive += 1
            except discord.Forbidden:
                blocked_members.append(member)
            except Exception:
                blocked_members.append(member)

            await asyncio.sleep(1)

            if index % 5 == 0:
                await status.edit(
                    content=(
                        f"🔍 Đang kiểm tra role **{role.name}**\n"
                        f"Đã kiểm tra: **{index}/{len(members)}**"
                    )
                )

        await status.delete()

        total = len(members)
        blocked = len(blocked_members)

        chunk_size = 20
        chunks = [
            blocked_members[i:i + chunk_size]
            for i in range(0, blocked, chunk_size)
        ]

        if not chunks:
            embed = discord.Embed(
                title="✅ KẾT QUẢ KIỂM TRA DM",
                description=(
                    f"Role: **{role.name}**\n"
                    f"👥 Tổng: **{total}**\n"
                    f"📩 Nhận được DM: **{can_receive}**\n"
                    f"🚫 Không nhận được: **0**"
                ),
                color=discord.Color.green()
            )
            return await ctx.send(embed=embed)

        embed = discord.Embed(
            title="📊 KẾT QUẢ KIỂM TRA DM",
            description=(
                f"Role: **{role.name}**\n"
                f"👥 Tổng: **{total}**\n"
                f"📩 Nhận được DM: **{can_receive}**\n"
                f"🚫 Không nhận được: **{blocked}**"
            ),
            color=discord.Color.red()
        )

        names_text = "\n".join(
            f"- {m} (`{m.id}`)" for m in chunks[0]
        )

        embed.add_field(
            name="🚫 Danh sách không nhận được DM",
            value=names_text,
            inline=False
        )

        await ctx.send(embed=embed)

        for chunk in chunks[1:]:
            embed_extra = discord.Embed(
                title="🚫 Danh sách tiếp theo",
                description="\n".join(
                    f"- {m} (`{m.id}`)" for m in chunk
                ),
                color=discord.Color.red()
            )
            await ctx.send(embed=embed_extra)


async def setup(bot):
    await bot.add_cog(SpamEvent(bot))