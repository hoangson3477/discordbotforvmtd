import discord
from discord.ext import commands
from discord import app_commands
from supabase import create_client
import os
import re

def normalize_name(text: str) -> str:
    return text.strip().lower().replace(" ", "_")

# ================= VIEW =================

class ArmyInfoView(discord.ui.View):
    def __init__(self, cog, member):
        super().__init__(timeout=120)
        self.cog = cog
        self.member = member
        self.current_page = "info"
        self.update_buttons()

    def update_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "info":
                    item.disabled = self.current_page == "info"
                elif item.custom_id == "achievements":
                    item.disabled = self.current_page == "achievements"

    async def build_info_embed(self):
        embed = discord.Embed(title="Thông tin Quân nhân", color=discord.Color.green())
        embed.add_field(name="Tên", value=self.cog.clean_name(self.member.display_name), inline=False)
        embed.add_field(name="Quân hàm", value=self.cog.get_rank(self.member), inline=False)
        embed.add_field(name="Chức vụ", value=self.cog.get_position(self.member), inline=False)
        embed.set_footer(text=f"ID: {self.member.id}")
        return embed

    async def build_achievement_embed(self):
        data = self.cog.supabase.table("user_achievements") \
            .select("achievements(display_name)") \
            .eq("user_id", self.member.id) \
            .execute()

        names = []

        for row in data.data:
            a = row["achievements"]
            if a:
                names.append(a["display_name"])

        if not names:
            content = "Không có thành tựu"
        else:
            content = "\n".join(f"• {n}" for n in names)

        embed = discord.Embed(title="Thành tựu", color=discord.Color.gold())
        embed.description = content
        embed.set_footer(text=f"Tổng: {len(names)} thành tựu")

        return embed    

    @discord.ui.button(label="Thông tin cơ bản", style=discord.ButtonStyle.secondary, custom_id="info")
    async def show_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "info"
        self.update_buttons()
        embed = await self.build_info_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Thành tựu", style=discord.ButtonStyle.primary, custom_id="achievements")
    async def show_achievements(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = "achievements"
        self.update_buttons()
        embed = await self.build_achievement_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class AchievementHubView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    def parse_footer(self, embed):
        import re
        text = embed.footer.text if embed.footer else ""

        page_match = re.search(r"Page Name:(.*?) \|", text)
        page_key = page_match.group(1) if page_match else "all"

        num_match = re.search(r"Trang (\d+)/", text)
        page_num = int(num_match.group(1)) - 1 if num_match else 0

        return page_key, page_num

    async def build_embed(self, page_key="all", page=0):
        per_page = 10

        page_id = None
        page_display_name = None
        achievement_ids = None

        # --- Nếu lọc theo page ---
        if page_key != "all":
            p = self.cog.supabase.table("achievement_pages") \
                .select("id, name") \
                .eq("name", page_key) \
                .execute()

            if not p.data:
                return discord.Embed(description="Page không tồn tại."), 0

            page_id = p.data[0]["id"]
            page_display_name = p.data[0]["name"]

            # Lấy link
            links = self.cog.supabase.table("achievement_page_links") \
                .select("achievement_id") \
                .eq("page_id", page_id) \
                .execute()

            achievement_ids = [l["achievement_id"] for l in links.data]

            if not achievement_ids:
                embed = discord.Embed(
                    title=f"Danh sách Thành Tựu - {page_display_name}",
                    description="Không có thành tựu.",
                    color=discord.Color.blue()
                )
                embed.set_footer(text=f"Page Name:{page_key} | Trang 1/1")
                return embed, 0

        # --- Query achievements ---
        query = self.cog.supabase.table("achievements") \
            .select("id, display_name, description")

        if achievement_ids is not None:
            query = query.in_("id", achievement_ids)

        # --- Đếm tổng ---
        count_q = self.cog.supabase.table("achievements") \
            .select("id", count="exact")

        if achievement_ids is not None:
            count_q = count_q.in_("id", achievement_ids)

        total = count_q.execute()
        total_count = total.count or 0

        max_page = max(0, (total_count - 1) // per_page)
        page = max(0, min(page, max_page))
        offset = page * per_page

        data = query.order("id").range(offset, offset + per_page - 1).execute()

        # --- Build embed ---
        title = "Danh sách Thành Tựu"
        if page_display_name:
            title += f" - {page_display_name}"

        embed = discord.Embed(title=title, color=discord.Color.blue())

        if not data.data:
            embed.description = "Không có thành tựu."
        else:
            lines = []
            for a in data.data:
                desc = a.get("description") or "Không có mô tả"
                lines.append(f"**[{a['id']}] {a['display_name']}**\n└ {desc}")
            embed.description = "\n\n".join(lines)

        embed.set_footer(text=f"Page Name:{page_key} | Trang {page+1}/{max_page+1}")

        return embed, max_page

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="hub_prev")
    async def prev(self, interaction, button):
        await interaction.response.defer()

        page_name, page = self.parse_footer(interaction.message.embeds[0])
        page -= 1

        embed, _ = await self.build_embed(page_name, page)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="hub_next")
    async def next(self, interaction, button):
        await interaction.response.defer()

        page_name, page = self.parse_footer(interaction.message.embeds[0])
        page += 1

        embed, _ = await self.build_embed(page_name, page)
        await interaction.edit_original_response(embed=embed, view=self)

class CheckTTView(discord.ui.View):
    def __init__(self, cog, achievement_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.achievement_id = achievement_id

    def get_page_from_footer(self, embed):
        import re
        text = embed.footer.text or ""
        match = re.search(r"Trang (\d+)/", text)
        return int(match.group(1)) - 1 if match else 0

    async def build_embed(self, page: int):
        per_page = 10
        offset = page * per_page

        # Lấy achievement name
        ach = self.cog.supabase.table("achievements") \
            .select("display_name") \
            .eq("id", self.achievement_id) \
            .single() \
            .execute()

        if not ach.data:
            return discord.Embed(
                title="Lỗi",
                description="Không tìm thấy thành tựu.",
                color=discord.Color.red()
            )

        ach_name = ach.data["display_name"]

        # Tổng số người có thành tựu
        total = self.cog.supabase.table("user_achievements") \
            .select("id", count="exact") \
            .eq("achievement_id", self.achievement_id) \
            .execute()

        total_count = total.count or 0
        max_page = max(0, (total_count - 1) // per_page)

        # Lấy 10 người theo trang
        data = self.cog.supabase.table("user_achievements") \
            .select("user_id") \
            .eq("achievement_id", self.achievement_id) \
            .range(offset, offset + per_page - 1) \
            .execute()

        embed = discord.Embed(
            title=f"Người sở hữu: {ach_name}",
            color=discord.Color.green()
        )

        if not data.data:
            embed.description = "Không có ai có thành tựu này."
        else:
            lines = []
            for row in data.data:
                uid = row["user_id"]
                lines.append(f"<@{uid}> (`{uid}`)")

            embed.description = "\n".join(lines)

        embed.set_footer(text=f"Trang {page+1}/{max_page+1} • Tổng {total_count} người")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="checktt_prev")
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        page = self.get_page_from_footer(interaction.message.embeds[0])
        page = max(0, page - 1)

        embed = await self.build_embed(page)
        await interaction.edit_original_response(embed=embed, view=self)


    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="checktt_next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        page = self.get_page_from_footer(interaction.message.embeds[0])
        page += 1

        embed = await self.build_embed(page)
        await interaction.edit_original_response(embed=embed, view=self)

class BXHView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    def get_page_from_footer(self, embed):
        import re
        text = embed.footer.text or ""
        match = re.search(r"Trang (\d+)/", text)
        return int(match.group(1)) - 1 if match else 0

    async def build_embed(self, page=0):
        per_page = 10

        data = self.cog.supabase.table("user_achievements") \
            .select("user_id") \
            .execute()

        counts = {}

        for row in data.data or []:
            uid = row["user_id"]
            counts[uid] = counts.get(uid, 0) + 1

        sorted_users = sorted(counts.items(), key=lambda x: x[1], reverse=True)

        total_users = len(sorted_users)
        max_page = max(0, (total_users - 1) // per_page)

        page = max(0, min(page, max_page))
        start = page * per_page
        end = start + per_page

        embed = discord.Embed(
            title="Bảng Xếp Hạng Thành Tựu",
            color=discord.Color.gold()
        )

        if not sorted_users:
            embed.description = "Chưa có dữ liệu."
        else:
            lines = []
            for idx, (uid, total) in enumerate(sorted_users[start:end], start=start+1):
                lines.append(f"**#{idx}** <@{uid}> — {total} thành tựu")

            embed.description = "\n".join(lines)

        embed.set_footer(text=f"Trang {page+1}/{max_page+1} • Tổng {total_users} người")

        return embed, max_page

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="bxh_prev")
    async def prev(self, interaction, button):
        await interaction.response.defer()

        page = self.get_page_from_footer(interaction.message.embeds[0])
        page -= 1

        embed, _ = await self.build_embed(page)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="bxh_next")
    async def next(self, interaction, button):
        await interaction.response.defer()

        page = self.get_page_from_footer(interaction.message.embeds[0])
        page += 1

        embed, _ = await self.build_embed(page)
        await interaction.edit_original_response(embed=embed, view=self)

class TKETTView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.mode = "popular"  # popular | rare

    def get_page_from_footer(self, embed):
        import re
        text = embed.footer.text or ""
        match = re.search(r"Trang (\d+)/", text)
        return int(match.group(1)) - 1 if match else 0

    async def build_embed(self, page=0):
        per_page = 10

        # Lấy toàn bộ achievements
        ach_data = self.cog.supabase.table("achievements") \
            .select("id, display_name") \
            .execute()

        # Lấy toàn bộ user_achievements
        ua_data = self.cog.supabase.table("user_achievements") \
            .select("user_id, achievement_id") \
            .execute()

        achievements = ach_data.data or []
        user_achievements = ua_data.data or []

        # Đếm unique user
        unique_users = {row["user_id"] for row in user_achievements}
        total_users = len(unique_users) or 1  # tránh chia 0

        # Đếm số người đạt từng achievement
        counts = {a["id"]: 0 for a in achievements}

        for row in user_achievements:
            aid = row["achievement_id"]
            if aid in counts:
                counts[aid] += 1

        stats = []
        for a in achievements:
            total = counts.get(a["id"], 0)
            percent = (total / total_users) * 100
            stats.append((a["display_name"], total, percent))

        # Sort theo mode
        if self.mode == "popular":
            stats.sort(key=lambda x: x[1], reverse=True)
            title_mode = "Phổ biến nhất"
        else:
            stats.sort(key=lambda x: x[1])
            title_mode = "Hiếm nhất"

        total_items = len(stats)
        max_page = max(0, (total_items - 1) // per_page)

        page = max(0, min(page, max_page))
        start = page * per_page
        end = start + per_page

        embed = discord.Embed(
            title=f"Thống kê Thành Tựu — {title_mode}",
            color=discord.Color.blurple()
        )

        if not stats:
            embed.description = "Chưa có dữ liệu."
        else:
            lines = []
            for idx, (name, total, percent) in enumerate(stats[start:end], start=start+1):
                lines.append(
                    f"**{idx}. {name}** : {total} người đạt - {percent:.1f}%"
                )

            embed.description = "\n".join(lines)

        embed.set_footer(text=f"Trang {page+1}/{max_page+1} • Tổng {total_items} thành tựu")

        return embed

    # ===== NÚT CHUYỂN TIÊU CHÍ =====

    @discord.ui.button(label="Theo độ Phổ biến", style=discord.ButtonStyle.success,custom_id="tkett_popular", row=0)
    async def popular(self, interaction, button):
        await interaction.response.defer()
        self.mode = "popular"
        embed = await self.build_embed(0)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Theo độ Hiếm", style=discord.ButtonStyle.secondary,custom_id="tkett_rare", row=0)
    async def rare(self, interaction, button):
        await interaction.response.defer()
        self.mode = "rare"
        embed = await self.build_embed(0)
        await interaction.edit_original_response(embed=embed, view=self)
    # ===== PAGINATION =====

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary,custom_id="tkett_prev", row=4)
    async def prev(self, interaction, button):
        await interaction.response.defer()
        page = self.get_page_from_footer(interaction.message.embeds[0])
        page -= 1
        embed = await self.build_embed(page)
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary,custom_id="tkett_next", row=4)
    async def next(self, interaction, button):
        await interaction.response.defer()
        page = self.get_page_from_footer(interaction.message.embeds[0])
        page += 1
        embed = await self.build_embed(page)
        await interaction.edit_original_response(embed=embed, view=self)

# ================= COG =================

class ArmySystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        url = "https://dmvzxsbptahdfefclsru.supabase.co"
        key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRtdnp4c2JwdGFoZGZlZmNsc3J1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2OTQ0Mjk2MywiZXhwIjoyMDg1MDE4OTYzfQ.dQjmeH1zafdur4ViwTxJekV86HfkQ1ODQ8Rh4KXPj5A" # dùng service role
        self.supabase = create_client(url, key)

        self.rank_roles = {
            903551143337144320: "Binh nhì",
            903551643767951401: "Binh nhất",
            903562108661284914: "Hạ sĩ",
            903554567294316545: "Trung sĩ",
            903550234523758634: "Thượng sĩ",
            910819091118452737: "Học viên sĩ quan",
            903550376194748457: "Thiếu uý",
            903550810913402941: "Trung uý",
            903573757610823730: "Thượng uý",
            903573912548417576: "Đại uý",
            903574093733982219: "Thiếu tá",
            903574182321864714: "Trung tá",
            903574367995301939: "Thượng tá",
            903574532978262027: "Đại tá",
            903550575319351319: "Thiếu tướng",
            903574618164584459: "Trung tướng",
        }
        self.load_positions()

    async def cog_load(self):
        self.bot.add_view(AchievementHubView(self))
        self.bot.add_view(BXHView(self))
        self.bot.add_view(TKETTView(self))

    def load_positions(self):
        data = self.supabase.table("positions").select("*").execute()

        rules = []
        for row in data.data:
            roles = set(int(x) for x in row["role_ids"].split(",") if x)

            rules.append({
                "name": row["name"],
                "roles": roles,
                "priority": row["priority"]
            })
        
        self.position_rules = rules

    # ===== PERMISSION CHECK =====
    async def is_whitelisted(self, ctx, command_name: str):
        if ctx.author.guild_permissions.administrator:
            return True

        data = self.supabase.table("command_whitelist") \
            .select("*") \
            .eq("command_name", command_name) \
            .execute()

        if not data.data:
            return False

        allowed_roles = {r["role_id"] for r in data.data}
        user_roles = {role.id for role in ctx.author.roles}

        return bool(allowed_roles & user_roles)

    # ===== BASIC INFO =====
    def clean_name(self, name: str):
        return re.sub(r"^\[[^\]]+\]\s*", "", name)

    def get_rank(self, member):
        for role in member.roles:
            if role.id in self.rank_roles:
                return self.rank_roles[role.id]
        return "Không xác định"

    def get_position(self, member):
        role_ids = {r.id for r in member.roles}
        matched = []

        for rule in self.position_rules:
            if rule["roles"].issubset(role_ids):
                matched.append(rule)

        if not matched:
            return "Không có"

        matched.sort(key=lambda x: x["priority"], reverse=True)
        return matched[0]["name"]
    
    # ===== COMMANDS =====

    @commands.command(name="armyinfo")
    async def armyinfo(self, ctx, member: discord.Member = None):
        target = member or ctx.author

        view = ArmyInfoView(self, target)
        embed = await view.build_info_embed()
        await ctx.send(embed=embed, view=view)


    app_commands.command(name="armyinfo", description="Xem thông tin quân nhân")
    @app_commands.describe(member="Chọn người muốn xem (để trống = xem bản thân)")
    async def armyinfo_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user

        view = ArmyInfoView(self, target)
        embed = await view.build_info_embed()
        await interaction.response.send_message(embed=embed, view=view)

    @commands.command(name="whitelist")
    async def whitelist(self, ctx, command_name: str, role: discord.Role):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("Bạn không có quyền.")

        self.supabase.table("command_whitelist").insert({
            "command_name": command_name.lower(),
            "role_id": role.id
        }).execute()

        await ctx.send(f"Đã whitelist role {role.name} cho lệnh {command_name}")

    @commands.command(name="newtt")
    async def newtt(self, ctx, *, content: str):
        if not await self.is_whitelisted(ctx, "newtt"):
            return await ctx.send("Bạn không có quyền.")

        parts = content.split("|", 1)
        name = parts[0].strip()
        description = parts[1].strip() if len(parts) > 1 else ""

        if not name:
            return await ctx.send("Tên thành tựu không được để trống.")

        normalized = normalize_name(name)

        # kiểm tra trùng name
        exist = self.supabase.table("achievements") \
            .select("id") \
            .eq("name", normalized) \
            .execute()

        if exist.data:
            return await ctx.send("Thành tựu đã tồn tại.")

        # lấy toàn bộ id hiện có
        data = self.supabase.table("achievements") \
            .select("id") \
            .order("id") \
            .execute()

        used_ids = {row["id"] for row in data.data}

        # tìm số nhỏ nhất chưa dùng
        new_id = 1
        while new_id in used_ids:
            new_id += 1

        # insert
        self.supabase.table("achievements").insert({
            "id": new_id,
            "name": normalized,
            "display_name": name,
            "description": description
        }).execute()

        await ctx.send(f"Đã tạo thành tựu **{name}** với ID: **{new_id}**")

    @commands.command(name="givett")
    async def givett(self, ctx, member: discord.Member, achievement_id: int):
        if not await self.is_whitelisted(ctx, "assigntt"):
            return await ctx.send("Bạn không có quyền.")

        ach = self.supabase.table("achievements") \
            .select("display_name") \
            .eq("id", achievement_id) \
            .execute()

        if not ach.data:
            return await ctx.send("ID thành tựu không tồn tại.")

        try:
            self.supabase.table("user_achievements").insert({
                "user_id": member.id,
                "achievement_id": achievement_id
            }).execute()
        except:
            return await ctx.send("Người này đã có thành tựu này.")

        await ctx.send(f"Đã gán **{ach.data[0]['display_name']}** cho {member.display_name}")

    @commands.command(name="listtt")
    async def listtt(self, ctx):
        view = AchievementHubView(self)

        # ===== NÚT TOÀN BỘ =====
        btn_all = discord.ui.Button(
            label="Toàn bộ",
            style=discord.ButtonStyle.success,
            row=0
        )

        async def all_callback(interaction):
            await interaction.response.defer()
            embed, _ = await view.build_embed("all", 0)
            await interaction.edit_original_response(embed=embed, view=view)

        btn_all.callback = all_callback
        view.add_item(btn_all)

        # ===== LẤY PAGE =====
        pages = self.supabase.table("achievement_pages") \
            .select("name") \
            .order("id") \
            .execute()

        max_buttons = 15
        page_list = pages.data[:max_buttons]

        for index, p in enumerate(page_list):
            name = p["name"]

            # Chia hàng: mỗi 5 nút 1 hàng
            row = (index // 5) + 1  # row 1-3

            async def callback(interaction, page_name=name):
                await interaction.response.defer()
                embed, _ = await view.build_embed(page_name, 0)
                await interaction.edit_original_response(embed=embed, view=view)

            btn = discord.ui.Button(
                label=name,
                style=discord.ButtonStyle.primary,
                row=row
            )

            btn.callback = callback
            view.add_item(btn)

        # ===== EMBED BAN ĐẦU =====
        embed, _ = await view.build_embed("all", 0)
        await ctx.send(embed=embed, view=view)


    @commands.command(name="removett")
    async def removett(self, ctx, member: discord.Member, achievement_id: int):
        if not await self.is_whitelisted(ctx, "removett"):
            return await ctx.send("Bạn không có quyền.")

        res = self.supabase.table("user_achievements") \
            .delete() \
            .eq("user_id", member.id) \
            .eq("achievement_id", achievement_id) \
            .execute()

        if not res.data:
            return await ctx.send("Người này không có thành tựu đó.")

        await ctx.send(f"Đã gỡ thành tựu ID {achievement_id} khỏi {member.display_name}")

    @commands.command(name="deletett")
    async def deletett(self, ctx, achievement_id: int):
        if not await self.is_whitelisted(ctx, "deletett"):
            return await ctx.send("Bạn không có quyền.")

        ach = self.supabase.table("achievements") \
            .select("display_name") \
            .eq("id", achievement_id) \
            .execute()

        if not ach.data:
            return await ctx.send("ID không tồn tại.")

        name = ach.data[0]["display_name"]

        self.supabase.table("achievements") \
            .delete() \
            .eq("id", achievement_id) \
            .execute()

        await ctx.send(f"Đã xoá thành tựu **{name}** (ID: {achievement_id})")

    @commands.command(name="newpos")
    async def newpos(self, ctx, *, content: str):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("Bạn không có quyền.")

        roles = ctx.message.role_mentions
        if not roles:
            return await ctx.send("Phải tag ít nhất 1 role.")

        # Xoá toàn bộ role mention khỏi content
        clean_content = content
        for r in roles:
            clean_content = clean_content.replace(f"<@&{r.id}>", "")

        clean_content = clean_content.strip()

        # Nếu người dùng nhập kiểu: "@role | Tên | 5"
        # thì sau khi xoá role sẽ thành: "| Tên | 5"
        # Ta bỏ dấu | đầu nếu có
        if clean_content.startswith("|"):
            clean_content = clean_content[1:].strip()

        parts = [p.strip() for p in clean_content.split("|") if p.strip()]

        name = parts[0] if len(parts) >= 1 else ""
        priority = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0

        if not name:
            return await ctx.send(
                "Thiếu tên chức vụ. Cú pháp: !newpos @role1 @role2 | Tên | priority"
            )

        # Hỗ trợ nhiều role (đã có)
        role_ids_str = ",".join(str(r.id) for r in roles)

        self.supabase.table("positions").insert({
            "name": name,
            "role_ids": role_ids_str,
            "priority": priority
        }).execute()

        self.load_positions()

        role_names = ", ".join(r.name for r in roles)

        await ctx.send(
            f"Đã tạo chức vụ **{name}**\n"
            f"Role áp dụng: {role_names}\n"
            f"Priority: {priority}"
        )

    @commands.command(name="listpos")
    async def listpos(self, ctx):
        data = self.supabase.table("positions") \
            .select("*") \
            .order("priority", desc=True) \
            .execute()

        if not data.data:
            return await ctx.send("Chưa có chức vụ nào.")

        lines = []
        for row in data.data:
            lines.append(f"[{row['id']}] {row['name']} (priority: {row['priority']})")

        await ctx.send("\n".join(lines))

    @commands.command(name="checktt")
    async def checktt(self, ctx, achievement_id: int):
        # kiểm tra tồn tại
        ach = self.supabase.table("achievements") \
            .select("id") \
            .eq("id", achievement_id) \
            .execute()

        if not ach.data:
            return await ctx.send("Không tìm thấy thành tựu với ID này.")

        view = CheckTTView(self, achievement_id)
        embed = await view.build_embed(0)

        await ctx.send(embed=embed, view=view)

    @commands.command(name="createpage")
    async def createpage(self, ctx, *, name: str):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("Bạn không có quyền.")

        name = name.strip()

        # Tạo key tự động
        key = name.lower().replace(" ", "_")

        # Check trùng key
        exist = self.supabase.table("achievement_pages") \
            .select("id") \
            .eq("key", key) \
            .execute()

        if exist.data:
            return await ctx.send("Page đã tồn tại (trùng key).")

        self.supabase.table("achievement_pages").insert({
            "key": key,
            "name": name
        }).execute()

        await ctx.send(f"Đã tạo page **{name}** (key tự động: `{key}`)")

    @commands.command(name="delpage")
    async def delpage(self, ctx, *, name: str):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("Bạn không có quyền.")

        page = self.supabase.table("achievement_pages") \
            .select("id") \
            .eq("name", name) \
            .execute()

        if not page.data:
            return await ctx.send("Page không tồn tại.")

        self.supabase.table("achievement_pages") \
            .delete() \
            .eq("name", name) \
            .execute()

        await ctx.send(f"Đã xoá page **{name}**")

    @commands.command(name="addpage", aliases=["assignpage"])
    async def addpage(self, ctx, *, content: str):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("Bạn không có quyền.")

        parts = content.split("|")

        if len(parts) != 2:
            return await ctx.send("Cú pháp: !addpage <tên page> | <achievement_id>")

        page_name = parts[0].strip()
        achievement_id = parts[1].strip()

        if not achievement_id.isdigit():
            return await ctx.send("ID không hợp lệ.")

        achievement_id = int(achievement_id)

        # --- Kiểm tra page tồn tại ---
        page = self.supabase.table("achievement_pages") \
            .select("id") \
            .ilike("name", page_name) \
            .execute()

        if not page.data:
            return await ctx.send("Page không tồn tại.")

        page_id = page.data[0]["id"]

        # --- Kiểm tra achievement tồn tại ---
        ach = self.supabase.table("achievements") \
            .select("id, display_name") \
            .eq("id", achievement_id) \
            .execute()

        if not ach.data:
            return await ctx.send("ID thành tựu không tồn tại.")

        achievement_name = ach.data[0]["display_name"]

        # --- Kiểm tra đã tồn tại link chưa ---
        existing = self.supabase.table("achievement_page_links") \
            .select("id") \
            .eq("achievement_id", achievement_id) \
            .eq("page_id", page_id) \
            .execute()

        if existing.data:
            return await ctx.send("Thành tựu đã có trong page này rồi.")

        # --- Insert link ---
        self.supabase.table("achievement_page_links").insert({
            "achievement_id": achievement_id,
            "page_id": page_id
        }).execute()

        await ctx.send(
            f"Đã thêm **{achievement_name}** (ID {achievement_id}) "
            f"vào page **{page_name}**"
        )

    @commands.command(name="bxhtt")
    async def bxhtt(self, ctx):
        view = BXHView(self)
        embed, _ = await view.build_embed(0)
        await ctx.send(embed=embed, view=view)

    @commands.command(name="tkett")
    async def tkett(self, ctx):
        view = TKETTView(self)
        embed = await view.build_embed(0)
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(ArmySystem(bot))
