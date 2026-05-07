"""
Optimized embed utilities to reduce Discord interaction lag
"""
import discord
from discord.ext import commands
import asyncio
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger("my_bot")

class EmbedBuilder:
    """Optimized embed builder with caching and async operations"""
    
    def __init__(self, title: str = "", color: discord.Color = discord.Color.blue()):
        self.title = title
        self.color = color
        self.fields = []
        self.footer_text = ""
        self.thumbnail_url = None
        self.author = None
        self.description = ""
        
    def add_field(self, name: str, value: str, inline: bool = False):
        """Add field to embed (batched)"""
        self.fields.append((name, value, inline))
        return self
    
    def set_footer(self, text: str):
        """Set footer text"""
        self.footer_text = text
        return self
    
    def set_thumbnail(self, url: str):
        """Set thumbnail URL"""
        self.thumbnail_url = url
        return self
    
    def set_author(self, name: str, icon_url: Optional[str] = None):
        """Set author"""
        self.author = {"name": name, "icon_url": icon_url}
        return self
    
    def set_description(self, description: str):
        """Set description"""
        self.description = description
        return self
    
    def build(self) -> discord.Embed:
        """Build the final embed"""
        embed = discord.Embed(title=self.title, description=self.description, color=self.color)
        
        # Add all fields at once (faster than individual add_field calls)
        for name, value, inline in self.fields:
            embed.add_field(name=name, value=value, inline=inline)
        
        if self.footer_text:
            embed.set_footer(text=self.footer_text)
        
        if self.thumbnail_url:
            embed.set_thumbnail(url=self.thumbnail_url)
        
        if self.author:
            embed.set_author(**self.author)
        
        return embed

class FastInteraction:
    """Optimized interaction handlers to reduce API calls"""
    
    @staticmethod
    async def defer_if_needed(interaction: discord.Interaction, ephemeral: bool = False):
        """Smart defer - only if response will take time"""
        try:
            # Try to defer quickly
            await interaction.response.defer(ephemeral=ephemeral)
        except discord.errors.InteractionResponded:
            # Already responded, skip
            pass
        except Exception as e:
            logger.warning(f"[FastInteraction] Defer failed: {e}")
    
    @staticmethod
    async def safe_edit(interaction: discord.Interaction, embed: discord.Embed, view: Optional[discord.ui.View] = None):
        """Safe embed edit with error handling"""
        try:
            await interaction.edit_original_response(embed=embed, view=view)
        except discord.errors.NotFound:
            logger.warning("[FastInteraction] Message not found for edit")
        except discord.errors.Forbidden:
            logger.warning("[FastInteraction] No permission to edit message")
        except Exception as e:
            logger.error(f"[FastInteraction] Edit failed: {e}")
    
    @staticmethod
    async def safe_followup(interaction: discord.Interaction, embed: discord.Embed, ephemeral: bool = False):
        """Safe followup with error handling"""
        try:
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        except discord.errors.Forbidden:
            logger.warning("[FastInteraction] No permission for followup")
        except Exception as e:
            logger.error(f"[FastInteraction] Followup failed: {e}")

class EmbedCache:
    """Simple cache for embed data to avoid rebuilds"""
    
    def __init__(self, ttl: int = 300):  # 5 minutes TTL
        self.cache = {}
        self.ttl = ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached data"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if asyncio.get_event_loop().time() - timestamp < self.ttl:
                return data
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Set cached data"""
        self.cache[key] = (value, asyncio.get_event_loop().time())
    
    def clear(self):
        """Clear cache"""
        self.cache.clear()

# Global embed cache for frequently accessed data
embed_cache = EmbedCache()

def create_user_embed(user: discord.User, title: str = "Thông tin người dùng") -> discord.Embed:
    """Fast user info embed creation"""
    return (EmbedBuilder(title=title, color=discord.Color.green())
            .add_field("Tên", user.display_name, False)
            .add_field("ID", str(user.id), True)
            .add_field("Bot?", "✅" if user.bot else "❌", True)
            .set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
            .build())

def create_achievement_embed(achievements: List[Dict], title: str = "Thành tựu") -> discord.Embed:
    """Fast achievement list embed creation"""
    if not achievements:
        return EmbedBuilder(title=title, color=discord.Color.gold()).set_description("Không có thành tựu.").build()
    
    builder = EmbedBuilder(title=title, color=discord.Color.gold())
    
    # Batch add fields (faster than individual calls)
    for i, ach in enumerate(achievements[:10], 1):  # Limit to 10 for performance
        builder.add_field(f"{i}. {ach.get('display_name', 'Unknown')}", ach.get('description', 'Không có mô tả'), False)
    
    if len(achievements) > 10:
        builder.set_footer(text=f"Hiển thị 10/{len(achievements)} thành tựu")
    
    return builder.build()

def paginate_embeds(items: List[str], title: str, items_per_page: int = 10, color: discord.Color = discord.Color.blue()) -> List[discord.Embed]:
    """Fast pagination embed creation"""
    if not items:
        return [EmbedBuilder(title=title, color=color).set_description("Không có dữ liệu.").build()]
    
    embeds = []
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    
    for page in range(total_pages):
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(items))
        page_items = items[start_idx:end_idx]
        
        builder = EmbedBuilder(title=title, color=color)
        builder.set_description("\n".join(page_items))
        builder.set_footer(text=f"Trang {page + 1}/{total_pages}")
        
        embeds.append(builder.build())
    
    return embeds

async def send_paginated_response(ctx: commands.Context, embeds: List[discord.Embed], view: discord.ui.View):
    """Send paginated response with optimized view switching"""
    if not embeds:
        return await ctx.send("Không có dữ liệu.")
    
    # Send first embed
    message = await ctx.send(embed=embeds[0], view=view)
    
    # Store embeds in view for fast switching
    if hasattr(view, 'embeds'):
        view.embeds = embeds
        view.current_page = 0
        view.message = message
    
    return message

class OptimizedView(discord.ui.View):
    """Base class for optimized views with embed caching"""
    
    def __init__(self, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.embeds = []
        self.current_page = 0
        self.message = None
    
    async def switch_page(self, interaction: discord.Interaction, page: int):
        """Fast page switching with cached embeds"""
        if 0 <= page < len(self.embeds):
            self.current_page = page
            await FastInteraction.safe_edit(interaction, self.embeds[page], self)
        else:
            await FastInteraction.safe_followup(interaction, discord.Embed(
                title="Lỗi",
                description="Trang không tồn tại.",
                color=discord.Color.red()
            ), ephemeral=True)
