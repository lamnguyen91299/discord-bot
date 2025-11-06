# main.py - DJ_TET (ĐÃ FIX LỖI INTERACTION + ỔN ĐỊNH)
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import yt_dlp
import asyncio
import re
import logging
import random
import os
from dotenv import load_dotenv
from pytube import Search

load_dotenv()

# === LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DJ_TET")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents, description="DJ_TET – Bot nhạc Tết 2026")
tree = bot.tree

# === YT-DLP CONFIG ===
ytdl = yt_dlp.YoutubeDL({
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': False,
    'source_address': '0.0.0.0',
    'logger': logger
})

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.5"'
}

ffmpeg_path = r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0-full_build\bin\ffmpeg.exe"

queue = {}
repeat_mode = {}  # 0: off, 1: song, 2: queue

def is_youtube_url(url):
    return re.match(r'(https?://)?(www\.)?(youtube|youtu\.be)', url) is not None

class Player(discord.PCMVolumeTransformer):
    def __init__(self, source, data):
        super().__init__(source)
        self.title = data.get('title', 'Unknown')

    @classmethod
    async def create(cls, url, loop):
        logger.info(f"Đang trích xuất audio từ: {url}")
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            if not data or 'url' not in data:
                raise ValueError("Không lấy được stream URL")
            return cls(discord.FFmpegPCMAudio(data['url'], executable=ffmpeg_path, **ffmpeg_options), data)
        except Exception as e:
            logger.error(f"Lỗi tạo player: {e}")
            raise

async def play_next(guild_id):
    if queue.get(guild_id):
        url, title = queue[guild_id].pop(0)
        logger.info(f"Phát tiếp: {title}")
        vc = bot.get_guild(guild_id).voice_client
        if not vc or not vc.is_connected():
            logger.warning("Voice client không kết nối, bỏ qua bài này")
            return
        try:
            player = await Player.create(url, bot.loop)
            def after_callback(e):
                if e:
                    logger.error(f"Player error: {e}")
                    return
                mode = repeat_mode.get(guild_id, 0)
                if mode == 1:  # repeat song
                    queue[guild_id].insert(0, (url, title))
                elif mode == 2:  # repeat queue
                    queue[guild_id].append((url, title))
                asyncio.run_coroutine_threadsafe(play_next(guild_id), bot.loop)
            vc.play(player, after=after_callback)
        except Exception as e:
            logger.error(f"Lỗi play_next: {e}")

@bot.event
async def on_ready():
    await bot.tree.sync()
    logger.info(f"DJ_TET đã sẵn sàng! ID: {bot.user}")

@tree.command(name="play", description="DJ_TET phát nhạc từ từ khóa hoặc URL")
async def play(interaction: discord.Interaction, query: str):
    # === DEFER INTERACTION (XỬ LÝ TẤT CẢ LỖI INTERACTION) ===
    try:
        await interaction.response.defer(ephemeral=False)
    except (discord.errors.HTTPException, discord.errors.NotFound):
        # Interaction đã được acknowledge hoặc timeout, tiếp tục với followup
        logger.warning("Interaction defer thất bại, sử dụng followup mode")

    logger.info(f"/play: {query}")

    # Kiểm tra voice
    if not interaction.user.voice:
        await interaction.followup.send("Vào voice channel trước nhé!")
        return

    vc = interaction.guild.voice_client
    if not vc:
        try:
            vc = await interaction.user.voice.channel.connect()
            logger.info(f"Đã vào voice: {vc.channel.name}")
        except Exception as e:
            logger.error(f"Lỗi kết nối voice: {e}")
            await interaction.followup.send("Không thể vào voice!")
            return

    guild_id = interaction.guild.id
    queue.setdefault(guild_id, [])

    try:
        if is_youtube_url(query):
            url = query
            info = ytdl.extract_info(url, download=False)
            title = info.get('title', 'Unknown')
        else:
            search = Search(query)
            if not search.results:
                await interaction.followup.send("DJ_TET không tìm thấy bài nào!")
                return
            video = search.results[0]
            url = f"https://www.youtube.com/watch?v={video.video_id}"
            title = video.title
            logger.info(f"Tìm thấy: {title} → {url}")
    except Exception as e:
        logger.error(f"Lỗi xử lý query: {e}")
        await interaction.followup.send(f"Lỗi tìm kiếm: {str(e)[:100]}...")
        return

    queue[guild_id].append((url, title))

    if vc.is_playing():
        await interaction.followup.send(f"**DJ_TET** thêm vào hàng đợi: **{title}**")
    else:
        asyncio.create_task(play_next(guild_id))
        await interaction.followup.send(f"**DJ_TET** đang phát: **{title}**")

@tree.command(name="stop", description="Dừng phát nhạc và rời voice")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
        await vc.disconnect()
        queue[interaction.guild.id] = []
        await interaction.response.send_message("Đã dừng và rời voice!")
    else:
        await interaction.response.send_message("Bot không ở trong voice!")

@tree.command(name="skip", description="Bỏ qua bài hiện tại")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("Đã bỏ qua bài hiện tại!")
    else:
        await interaction.response.send_message("Không có bài nào đang phát!")

@tree.command(name="queue", description="Hiển thị hàng đợi nhạc")
async def show_queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if queue.get(guild_id):
        queue_list = "\n".join(f"{i+1}. {title}" for i, (_, title) in enumerate(queue[guild_id]))
        await interaction.response.send_message(f"**Hàng đợi:**\n{queue_list}")
    else:
        await interaction.response.send_message("Hàng đợi trống!")

@tree.command(name="clear", description="Xóa hàng đợi")
async def clear_queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    queue[guild_id] = []
    await interaction.response.send_message("Đã xóa hàng đợi!")

@tree.command(name="shuffle", description="Xáo trộn hàng đợi")
async def shuffle_queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if queue.get(guild_id) and len(queue[guild_id]) > 1:
        random.shuffle(queue[guild_id])
        await interaction.response.send_message("Đã xáo trộn hàng đợi!")
    else:
        await interaction.response.send_message("Hàng đợi cần ít nhất 2 bài để xáo trộn!")

class RepeatView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=60)
        self.guild_id = guild_id

    @discord.ui.button(label="Tắt", style=discord.ButtonStyle.secondary)
    async def off(self, interaction: discord.Interaction, button: Button):
        repeat_mode[self.guild_id] = 0
        await interaction.response.send_message("Chế độ lặp: tắt")

    @discord.ui.button(label="Bài hiện tại", style=discord.ButtonStyle.primary)
    async def song(self, interaction: discord.Interaction, button: Button):
        repeat_mode[self.guild_id] = 1
        await interaction.response.send_message("Chế độ lặp: bài hiện tại")

    @discord.ui.button(label="Toàn queue", style=discord.ButtonStyle.primary)
    async def queue(self, interaction: discord.Interaction, button: Button):
        repeat_mode[self.guild_id] = 2
        await interaction.response.send_message("Chế độ lặp: toàn queue")

@tree.command(name="repeat", description="Chọn chế độ lặp")
async def set_repeat(interaction: discord.Interaction):
    view = RepeatView(interaction.guild.id)
    await interaction.response.send_message("Chọn chế độ lặp:", view=view)

@tree.command(name="remove", description="Xóa bài tại vị trí")
async def remove_song(interaction: discord.Interaction, position: int):
    guild_id = interaction.guild.id
    if queue.get(guild_id) and 1 <= position <= len(queue[guild_id]):
        removed = queue[guild_id].pop(position - 1)
        await interaction.response.send_message(f"Đã xóa: {removed[1]}")
    else:
        await interaction.response.send_message("Vị trí không hợp lệ!")

@tree.command(name="move", description="Di chuyển bài từ vị trí A đến B")
async def move_song(interaction: discord.Interaction, from_pos: int, to_pos: int):
    guild_id = interaction.guild.id
    q = queue.get(guild_id, [])
    if q and 1 <= from_pos <= len(q) and 1 <= to_pos <= len(q):
        song = q.pop(from_pos - 1)
        q.insert(to_pos - 1, song)
        await interaction.response.send_message(f"Đã di chuyển {song[1]} đến vị trí {to_pos}")
    else:
        await interaction.response.send_message("Vị trí không hợp lệ!")

class SearchView(View):
    def __init__(self, results, guild_id):
        super().__init__(timeout=300)  # 5 minutes
        self.results = results
        self.guild_id = guild_id
        for i in range(len(results)):
            button = Button(label=str(i+1), style=discord.ButtonStyle.primary)
            button.callback = self.create_callback(i)
            self.add_item(button)

    def create_callback(self, index):
        async def callback(interaction: discord.Interaction):
            if not interaction.user.voice:
                await interaction.response.send_message("Vào voice channel trước nhé!")
                return

            vc = bot.get_guild(self.guild_id).voice_client
            if not vc:
                try:
                    vc = await interaction.user.voice.channel.connect()
                except Exception as e:
                    await interaction.response.send_message("Không thể vào voice!")
                    return

            song = self.results[index]
            url = song['url']
            title = song['title']
            queue.setdefault(self.guild_id, [])
            queue[self.guild_id].append((url, title))
            was_playing = vc.is_playing() if vc else False
            if not was_playing:
                asyncio.create_task(play_next(self.guild_id))
            await interaction.response.send_message(f"Đã thêm: {title}")
        return callback

@tree.command(name="search", description="Tìm kiếm nhạc trên YouTube")
async def search_songs(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'extract_flat': True,
            'skip_download': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            results = info.get('entries', [])[:5]
        if not results:
            await interaction.followup.send("Không tìm thấy kết quả!")
            return
        titles = "\n".join(f"{i+1}. {r['title']}" for i, r in enumerate(results))
        view = SearchView(results, interaction.guild.id)
        await interaction.followup.send(f"Kết quả tìm kiếm cho '{query}':\n{titles}", view=view)
    except Exception as e:
        await interaction.followup.send(f"Lỗi tìm kiếm: {str(e)[:100]}")

@tree.command(name="help", description="Hướng dẫn sử dụng bot")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🎵 DJ_TET Bot - Hướng dẫn sử dụng", color=0x00ff00)
    embed.add_field(
        name="🎶 Phát nhạc",
        value="`/play <tên bài/url>` - Phát nhạc từ YouTube\n"
              "`/stop` - Dừng phát và rời voice\n"
              "`/skip` - Bỏ qua bài hiện tại",
        inline=False
    )
    embed.add_field(
        name="📋 Quản lý Queue",
        value="`/queue` - Xem danh sách chờ\n"
              "`/clear` - Xóa toàn bộ queue\n"
              "`/shuffle` - Xáo trộn queue\n"
              "`/remove <vị trí>` - Xóa bài tại vị trí\n"
              "`/move <từ> <đến>` - Di chuyển bài trong queue",
        inline=False
    )
    embed.add_field(
        name="🔄 Lặp lại",
        value="`/repeat` - Chọn chế độ lặp (Tắt/Bài hiện tại/Queue)",
        inline=False
    )
    embed.add_field(
        name="🔍 Tìm kiếm",
        value="`/search <từ khóa>` - Tìm kiếm và chọn từ top 5 kết quả",
        inline=False
    )
    embed.set_footer(text="DJ_TET v1 - Bot nhạc Discord")
    await interaction.response.send_message(embed=embed)

# === CHẠY BOT ===
bot.run(os.getenv('DISCORD_TOKEN'))
