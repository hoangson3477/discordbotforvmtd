import discord
from discord.ext import commands
from typing import Optional


class SpotifyView(discord.ui.View):
    """Embed view cho Spotify info - có nút để mở Spotify trên web"""
    
    def __init__(self, track_url: Optional[str] = None, artist_url: Optional[str] = None):
        super().__init__()
        self.track_url = track_url
        self.artist_url = artist_url
        
        if self.track_url:
            self.add_item(discord.ui.Button(
                label="🎵 Mở bài hát",
                url=self.track_url,
                style=discord.ButtonStyle.link
            ))


class Spotify(commands.Cog):
    """
    Cog để xem thông tin Spotify của user.
    
    Cách dùng:
    - "hey spotify" (xem của chính mình)
    - "hey spotify @user" (xem của user khác)
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def get_spotify_activity(self, user: discord.Member) -> Optional[discord.Spotify]:
        """
        Lấy hoạt động Spotify từ presence của user.
        
        Args:
            user: Discord member object
            
        Returns:
            discord.Spotify object nếu user đang nghe Spotify, None nếu không
        """
        if not user.activities:
            return None
        
        for activity in user.activities:
            if isinstance(activity, discord.Spotify):
                return activity
        
        return None
    
    def create_spotify_embed(self, activity: discord.Spotify, user: discord.Member) -> discord.Embed:
        """
        Tạo embed hiển thị thông tin Spotify.
        
        Args:
            activity: Spotify activity object
            user: Discord member object
            
        Returns:
            discord.Embed object
        """
        embed = discord.Embed(
            title="🎵 Thông tin Spotify",
            color=0x1DB954,  # Spotify green
            description=f"**{user.mention}** đang nghe:"
        )
        
        # Thêm cover art nếu có
        if activity.album_cover_url:
            embed.set_thumbnail(url=activity.album_cover_url)
        
        # Thông tin bài hát
        embed.add_field(
            name="🎤 Bài hát",
            value=f"[{activity.title}]({activity.track_url})",
            inline=False
        )
        
        # Nghệ sĩ
        artists = ", ".join(activity.artists) if activity.artists else "Unknown"
        embed.add_field(
            name="👨‍🎤 Nghệ sĩ",
            value=artists,
            inline=True
        )
        
        # Album
        embed.add_field(
            name="💿 Album",
            value=activity.album or "Unknown",
            inline=True
        )
        
        # Thời gian
        if activity.duration:
            minutes, seconds = divmod(int(activity.duration.total_seconds()), 60)
            embed.add_field(
                name="⏱️ Thời lượng",
                value=f"{minutes}:{seconds:02d}",
                inline=True
            )
        
        embed.set_footer(
            text=f"Spotify • {user.name}",
            icon_url="https://open.spotifycdn.com/images/favicon32.ico"
        )
        
        return embed
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Lắng nghe tin nhắn chứa "hey spotify".
        """
        # Bỏ qua tin nhắn của bot
        if message.author.bot:
            return
        
        # Kiểm tra xem message có chứa "hey spotify" không (không phân biệt hoa/thường)
        content = message.content.strip().lower()
        
        if "hey spotify" not in content:
            return
        
        # Nếu tin nhắn là trong DM, lấy author
        if isinstance(message.channel, discord.DMChannel):
            target_user = message.author
        else:
            # Nếu trong guild, lấy member object
            target_user = message.author
            
            # Kiểm tra xem có mention ai không
            if message.mentions:
                target_user = message.mentions[0]
        
        # Chuyển thành member object nếu cần
        if not isinstance(target_user, discord.Member):
            if isinstance(message.channel, discord.TextChannel):
                try:
                    target_user = await message.guild.fetch_member(target_user.id)
                except discord.errors.NotFound:
                    await message.reply("❌ Không tìm thấy user này!")
                    return
            else:
                await message.reply("❌ Không thể lấy thông tin user!")
                return
        
        # Lấy hoạt động Spotify
        spotify_activity = self.get_spotify_activity(target_user)
        
        if not spotify_activity:
            embed = discord.Embed(
                title="🎵 Spotify",
                description=f"**{target_user.mention}** không đang nghe Spotify 😔",
                color=0x1DB954
            )
            await message.reply(embed=embed)
            return
        
        # Tạo embed và gửi
        embed = self.create_spotify_embed(spotify_activity, target_user)
        view = SpotifyView(spotify_activity.track_url)
        
        await message.reply(embed=embed, view=view)
    
    @commands.hybrid_command(name="spotify", aliases=["sp"])
    async def spotify_command(
        self,
        ctx: commands.Context,
        user: Optional[discord.Member] = None
    ):
        """
        Xem thông tin Spotify của một user.
        
        Cách dùng:
        /spotify [user]
        !spotify [@user]
        """
        target_user = user or ctx.author
        
        # Lấy hoạt động Spotify
        spotify_activity = self.get_spotify_activity(target_user)
        
        if not spotify_activity:
            embed = discord.Embed(
                title="🎵 Spotify",
                description=f"**{target_user.mention}** không đang nghe Spotify 😔",
                color=0x1DB954
            )
            await ctx.send(embed=embed)
            return
        
        # Tạo embed và gửi
        embed = self.create_spotify_embed(spotify_activity, target_user)
        view = SpotifyView(spotify_activity.track_url)
        
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    """
    Load cog vào bot.
    Được gọi tự động bởi bot khi load extension.
    """
    await bot.add_cog(Spotify(bot))
