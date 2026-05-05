import discord
from discord.ext import commands
from discord import app_commands
from supabase import create_client
import os
import re

# Environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://dmvzxsbptahdfefclsru.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_KEY:
    raise EnvironmentError("[quan_nhan_info] Thiếu SUPABASE_KEY trong .env")

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
    """Permanent shared view - state stored in message footer"""
    
    def __init__(self, cog):
        super().__init__(timeout=None)  # No timeout = permanent
        self.cog = cog
        self.per_page = 10
        self.add_page_select()
        self.add_filter_select()

    def parse_footer(self, embed: discord.Embed):
        """Parse state from footer text"""
        text = embed.footer.text if embed.footer else ""
        
        # Default values
        page = 0
        page_key = "all"
        filter_rarity = None
        search_query = None
        
        # Parse: "Trang 1/5 | Page: Event | Filter: rare | Search: keyword"
        page_match = re.search(r"Trang (\d+)/", text)
        if page_match:
            page = int(page_match.group(1)) - 1
        
        page_key_match = re.search(r"\| Page: ([^|]+)", text)
        if page_key_match:
            page_key = page_key_match.group(1).strip()
        
        filter_match = re.search(r"\| Filter: ([^|]+)", text)
        if filter_match:
            filter_rarity = filter_match.group(1).strip()
        
        search_match = re.search(r"\| Search: (.+)$", text)
        if search_match:
            search_query = search_match.group(1).strip()
        
        return page, page_key, filter_rarity, search_query

    def build_footer(self, page, max_page, page_key, filter_rarity, search_query, total):
        """Build footer with all state info"""
        parts = [f"Trang {page + 1}/{max_page + 1}"]
        if total > 0:
            parts.append(f"Tổng: {total}")
        if page_key != "all":
            parts.append(f"Page: {page_key}")
        if filter_rarity:
            parts.append(f"Filter: {filter_rarity}")
        if search_query:
            parts.append(f"Search: {search_query}")
        return " | ".join(parts)

    def add_page_select(self):
        """Thêm dropdown chọn page"""
        pages = self.cog.supabase.table("achievement_pages").select("id, name, key").order("id").execute()
        
        options = [discord.SelectOption(label="📋 Toàn bộ", value="all", description="Xem tất cả thành tựu")]
        
        for p in pages.data:
            if len(options) >= 25:
                break
            # Use 'key' for value (shorter, URL-safe), 'name' for label
            page_key = p.get("key") or p["name"].lower().replace(" ", "_")[:50]
            page_name = p["name"][:100] if p["name"].strip() else f"Page {p['id']}"
            
            options.append(discord.SelectOption(
                label=page_name,
                value=page_key[:100],  # Discord limit: 1-100 chars
                description=f"Page {p['id']}"
            ))
        
        select = discord.ui.Select(
            placeholder="📁 Chọn Page...",
            options=options,
            custom_id="page_select",
            row=0
        )
        
        async def select_callback(interaction: discord.Interaction):
            await interaction.response.defer()
            
            # Parse current state from message
            embed = interaction.message.embeds[0]
            page, page_key, filter_rarity, search_query = self.parse_footer(embed)
            
            # Update page_key, reset to page 0
            new_page_key = select.values[0]
            
            new_embed, _ = await self.build_embed_with_state(
                page=0, page_key=new_page_key, filter_rarity=filter_rarity, search_query=search_query
            )
            await interaction.edit_original_response(embed=new_embed, view=self)
        
        select.callback = select_callback
        self.add_item(select)

    def add_filter_select(self):
        """Thêm dropdown filter độ hiếm"""
        filter_options = [
            discord.SelectOption(label="🌟 Tất cả", value="all"),
            discord.SelectOption(label="📗 Phổ biến (>20%)", value="common"),
            discord.SelectOption(label="📙 Hiếm (5-20%)", value="rare"),
            discord.SelectOption(label="📕 Cực hiếm (<5%)", value="legendary"),
        ]
        
        select = discord.ui.Select(
            placeholder="🔍 Lọc theo độ hiếm...",
            options=filter_options,
            custom_id="filter_select",
            row=1
        )
        
        async def filter_callback(interaction: discord.Interaction):
            await interaction.response.defer()
            
            # Parse current state from message
            embed = interaction.message.embeds[0]
            page, page_key, _, search_query = self.parse_footer(embed)
            
            # Update filter, reset to page 0
            value = select.values[0]
            new_filter = None if value == "all" else value
            
            new_embed, _ = await self.build_embed_with_state(
                page=0, page_key=page_key, filter_rarity=new_filter, search_query=search_query
            )
            await interaction.edit_original_response(embed=new_embed, view=self)
        
        select.callback = filter_callback
        self.add_item(select)

    async def build_embed_with_state(self, page, page_key, filter_rarity, search_query):
        """Build embed with specific state"""
        query = self.cog.supabase.table("achievements").select("id, display_name, description, name")
        
        # Filter theo page
        if page_key != "all":
            page_data = self.cog.supabase.table("achievement_pages").select("id").eq("key", page_key).execute()
            if page_data.data:
                links = self.cog.supabase.table("achievement_page_links").select("achievement_id").eq("page_id", page_data.data[0]["id"]).execute()
                achievement_ids = [l["achievement_id"] for l in links.data]
                if achievement_ids:
                    query = query.in_("id", achievement_ids)
                else:
                    embed = discord.Embed(
                        title="Danh sách Thành Tựu",
                        description=f"Page **{page_key}** không có thành tựu nào.",
                        color=discord.Color.blue()
                    )
                    embed.set_footer(text=self.build_footer(0, 0, page_key, filter_rarity, search_query, 0))
                    return embed, 0

        # Lấy data
        all_data = query.execute().data or []
        
        # Filter by search
        if search_query:
            search_lower = search_query.lower()
            all_data = [a for a in all_data if search_lower in a.get("display_name", "").lower() 
                       or search_lower in a.get("description", "").lower()
                       or search_lower in a.get("name", "").lower()]
        
        # Filter by rarity
        if filter_rarity:
            all_data = await self._filter_by_rarity(all_data, filter_rarity)
        
        # Pagination
        total = len(all_data)
        max_page = max(0, (total - 1) // self.per_page) if total > 0 else 0
        page = max(0, min(page, max_page))
        
        start = page * self.per_page
        end = start + self.per_page
        page_data = all_data[start:end]
        
        # Build embed title
        title = "🏆 Danh sách Thành Tựu"
        if page_key != "all":
            title += f" - {page_key}"
        if search_query:
            title = f"🔍 Tìm kiếm: '{search_query}'"
        
        embed = discord.Embed(title=title, color=discord.Color.blue())
        
        if not page_data:
            embed.description = "Không tìm thấy thành tựu nào."
        else:
            lines = []
            for a in page_data:
                desc = a.get("description") or "Không có mô tả"
                if len(desc) > 50:
                    desc = desc[:47] + "..."
                rarity_emoji = await self._get_rarity_emoji(a["id"])
                lines.append(f"{rarity_emoji} **[{a['id']}] {a['display_name']}**\n└ {desc}")
            embed.description = "\n\n".join(lines)
        
        # Build footer with state
        embed.set_footer(text=self.build_footer(page, max_page, page_key, filter_rarity, search_query, total))
        
        return embed, max_page

    async def _filter_by_rarity(self, achievements, filter_rarity):
        """Filter by rarity"""
        total_users = len(set(
            row["user_id"] for row in 
            self.cog.supabase.table("user_achievements").select("user_id").execute().data or []
        ))
        
        if total_users == 0:
            return achievements
        
        filtered = []
        for ach in achievements:
            count = self.cog.supabase.table("user_achievements").select("id", count="exact").eq("achievement_id", ach["id"]).execute().count or 0
            percent = (count / total_users) * 100
            
            if filter_rarity == "common" and percent > 20:
                filtered.append(ach)
            elif filter_rarity == "rare" and 5 <= percent <= 20:
                filtered.append(ach)
            elif filter_rarity == "legendary" and percent < 5:
                filtered.append(ach)
        
        return filtered

    async def _get_rarity_emoji(self, achievement_id):
        """Lấy emoji theo độ hiếm"""
        total_users = len(set(
            row["user_id"] for row in 
            self.cog.supabase.table("user_achievements").select("user_id").execute().data or []
        ))
        
        if total_users == 0:
            return "📄"
        
        count = self.cog.supabase.table("user_achievements").select("id", count="exact").eq("achievement_id", achievement_id).execute().count or 0
        percent = (count / total_users) * 100
        
        if percent > 20:
            return "📗"
        elif percent > 5:
            return "📙"
        else:
            return "📕"

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="hub_prev", row=2)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # Parse state from message
        embed = interaction.message.embeds[0]
        page, page_key, filter_rarity, search_query = self.parse_footer(embed)
        
        # Go to previous page
        new_page = max(0, page - 1)
        
        new_embed, _ = await self.build_embed_with_state(
            page=new_page, page_key=page_key, filter_rarity=filter_rarity, search_query=search_query
        )
        await interaction.edit_original_response(embed=new_embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="hub_next", row=2)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # Parse state from message
        embed = interaction.message.embeds[0]
        page, page_key, filter_rarity, search_query = self.parse_footer(embed)
        
        # Get max page
        _, max_page = await self.build_embed_with_state(
            page=page, page_key=page_key, filter_rarity=filter_rarity, search_query=search_query
        )
        
        # Go to next page
        new_page = min(max_page, page + 1)
        
        new_embed, _ = await self.build_embed_with_state(
            page=new_page, page_key=page_key, filter_rarity=filter_rarity, search_query=search_query
        )
        await interaction.edit_original_response(embed=new_embed, view=self)

    @discord.ui.button(label="🔍 Tìm kiếm", style=discord.ButtonStyle.primary, custom_id="hub_search", row=2)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SearchAchievementModal(self.cog, self))

class SearchAchievementModal(discord.ui.Modal, title="Tìm kiếm Thành Tựu"):
    def __init__(self, cog, view):
        super().__init__()
        self.cog = cog
        self.view = view

    search_input = discord.ui.TextInput(
        label="Từ khóa",
        placeholder="Nhập tên hoặc mô tả thành tựu...",
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Parse current state from message
        embed = interaction.message.embeds[0]
        page, page_key, filter_rarity, _ = self.view.parse_footer(embed)
        
        # Search with new keyword
        new_embed, _ = await self.view.build_embed_with_state(
            page=0, page_key=page_key, filter_rarity=filter_rarity, search_query=self.search_input.value
        )
        await interaction.response.edit_message(embed=new_embed, view=self.view)

class CheckTTView(discord.ui.View):
    def __init__(self, cog, achievement_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.achievement_id = achievement_id

    def get_page_from_footer(self, embed):
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
        self.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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
        # Register permanent views (timeout=None)
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
        """Hiển thị danh sách thành tựu với filter và search (shared & permanent)"""
        view = AchievementHubView(self)
        embed, _ = await view.build_embed_with_state(
            page=0, page_key="all", filter_rarity=None, search_query=None
        )
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
