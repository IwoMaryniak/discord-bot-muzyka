import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
from flask import Flask
from threading import Thread

# ==========================================
# 1. SERWER WWW DLA RENDERA (KEEP ALIVE)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Bot działa, śpiewa i nie śpi!"

def run():
    # Render automatycznie przypisuje odpowiedni port w zmiennej PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 2. KONFIGURACJA BOTA DISCORD
# ==========================================
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="/", intents=intents)

# Słownik przechowujący kolejki utworów: {guild_id: [(url_audio, tytul)]}
queues = {}

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0', # Zapobiega błędom sieciowym IPv6
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

@bot.event
async def on_ready():
    print(f'Zalogowano pomyślnie jako: {bot.user.name}')
    
    # Automatyczne ustawianie animowanego profilowego z repozytorium GitHub
    if os.path.exists("avatar.gif"):
        try:
            with open("avatar.gif", "rb") as f:
                avatar_bytes = f.read()
            await bot.user.edit(avatar=avatar_bytes)
            print("Pomyślnie zaktualizowano animowany awatar bota!")
        except discord.HTTPException as e:
            print(f"Discord zablokował zmianę awataru (częsty powód: zabezpieczenie anty-spamowe/ratelimit): {e}")
        except Exception as e:
            print(f"Nie udało się zmienić awataru: {e}")
            
    # Synchronizacja nowoczesnych komend Slash (/)
    try:
        synced = await bot.tree.sync()
        print(f"Zsynchronizowano {len(synced)} komend typu Slash.")
    except Exception as e:
        print(f"Błąd synchronizacji komend: {e}")

# Funkcja obsługująca automatyczne przechodzenie do kolejnego utworu w kolejce
async def play_next(interaction, guild_id):
    voice_client = interaction.guild.voice_client
    if voice_client and guild_id in queues and len(queues[guild_id]) > 0:
        next_url, next_title = queues[guild_id].pop(0)
        
        source = discord.FFmpegPCMAudio(next_url, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error:
                print(f"Błąd podczas odtwarzania: {error}")
            bot.loop.create_task(play_next(interaction, guild_id))
            
        voice_client.play(source, after=after_playing)
        await interaction.channel.send(f"🎶 Teraz gram z kolejki: **{next_title}**")

@bot.tree.command(name="play", description="Puszcza muzykę z linku lub wyszukuje piosenkę na YouTube")
@app_commands.describe(utwor="Wklej link URL lub wpisz tytuł (np. Kalinka by Major spz)")
async def play(interaction: discord.Interaction, utwor: str):
    # Dajemy botowi czas na przetworzenie piosenki (zapobiega błędowi "Interaction timed out")
    await interaction.response.defer()

    # Sprawdzanie czy użytkownik jest na kanale głosowym
    if not interaction.user.voice:
        await interaction.followup.send("❌ Musisz najpierw wejść na kanał głosowy!")
        return

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    # Bot dołącza na kanał lub przenosi się na Twój kanał
    if not voice_client:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    guild_id = interaction.guild_id
    if guild_id not in queues:
        queues[guild_id] = []

    # Automatyczne wykrywanie: czy podano link URL, czy zwykły tekst do wyszukania
    query = utwor
    if not query.startswith("http://") and not query.startswith("https://"):
        query = f"ytsearch:{query}"

    # Bezpieczne, asynchroniczne wyciąganie linku audio bez blokowania bota
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    except Exception as e:
        print(f"Błąd wyszukiwania: {e}")
        await interaction.followup.send("❌ Wystąpił błąd podczas wyszukiwania utworu.")
        return

    # Jeśli użytkownik wpisał tekst, pobieramy pierwszy pasujący wynik wyszukiwania
    if 'entries' in data:
        if not data['entries']:
            await interaction.followup.send("❌ Nie znaleziono żadnego pasującego tytułu.")
            return
        data = data['entries'][0]

    url = data['url']
    title = data['title']

    # Jeśli bot aktualnie nic nie gra, puszcza utwór od razu
    if not voice_client.is_playing() and not voice_client.is_paused():
        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error:
                print(f"Błąd podczas odtwarzania: {error}")
            bot.loop.create_task(play_next(interaction, guild_id))
            
        voice_client.play(source, after=after_playing)
        await interaction.followup.send(f"▶️ Teraz gram: **{title}**")
    else:
        # Jeśli bot już coś gra, dodaje utwór do playlisty (kolejki)
        queues[guild_id].append((url, title))
        await interaction.followup.send(f"📁 Dodano do kolejki: **{title}**")

if __name__ == "__main__":
    # Uruchomienie mini-serwera HTTP w osobnym wątku
    keep_alive()
    
    # Bezpieczne pobranie tokenu ze zmiennych środowiskowych serwera Render
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ BŁĄD SYSTEMU: Brak zmiennej środowiskowej DISCORD_TOKEN w panelu Render.com!")
