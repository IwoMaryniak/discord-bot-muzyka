const { Client, GatewayIntentBits, REST, Routes, SlashCommandBuilder } = require('discord.js');
const { joinVoiceChannel, createAudioPlayer, createAudioResource, AudioPlayerStatus } = require('@discordjs/voice');
const play = require('play-dl');
const fs = require('fs');
const path = require('path');

const TOKEN = process.env.TOKEN_BOTA;
const CLIENT_ID = process.env.ID_BOTA;

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.GuildMessages
    ]
});

const queues = new Map();

const commands = [
    new SlashCommandBuilder()
        .setName('play')
        .setDescription('Puszcza muzykę z YT/Spotify lub dodaje do kolejki')
        .addStringOption(option => 
            option.setName('piosenka')
                .setDescription('Nazwa piosenki, link YT lub link Spotify')
                .setRequired(true))
].map(command => command.toJSON());

const rest = new REST({ version: '10' }).setToken(TOKEN);

(async () => {
    try {
        console.log('Rejestrowanie komend...');
        await rest.put(Routes.applicationCommands(CLIENT_ID), { body: commands });
        console.log('Komendy zarejestrowane!');
    } catch (error) {
        console.error(error);
    }
})();

async function playSong(guildId, queue) {
    if (!queue || queue.songs.length === 0) {
        setTimeout(() => {
            if (queue && queue.songs.length === 0) {
                queue.connection.destroy();
                queues.delete(guildId);
            }
        }, 180000); // 3 minuty bezczynności i wychodzi
        return;
    }

    const song = queue.songs[0];
    try {
        let stream = await play.stream(song.url);
        const resource = createAudioResource(stream.stream, { inputType: stream.type });
        queue.player.play(resource);
        queue.textChannel.send(`🎶 Teraz gram: **${song.title}**`);
    } catch (error) {
        console.error(error);
        queue.textChannel.send(`❌ Błąd odtwarzania: ${song.title}. Gram następny utwór.`);
        queue.songs.shift();
        playSong(guildId, queue);
    }
}

client.once('ready', async () => {
    console.log(`Zalogowano jako ${client.user.tag}!`);
    const avatarPath = path.join(__dirname, 'Avatar.gif');
    if (fs.existsSync(avatarPath)) {
        try {
            const avatar = fs.readFileSync(avatarPath);
            await client.user.setAvatar(avatar);
            console.log('Ustawiono animowany awatar!');
        } catch (e) {
            console.log('Profilowe ustawia się raz na jakiś czas (limit Discorda).');
        }
    }
});

client.on('interactionCreate', async interaction => {
    if (!interaction.isChatInputCommand()) return;

    if (interaction.commandName === 'play') {
        await interaction.deferReply();
        const query = interaction.options.getString('piosenka');
        const voiceChannel = interaction.member.voice.channel;

        if (!voiceChannel) return interaction.editReply('Musisz być na kanale głosowym!');

        let songTitle = "";
        let songUrl = "";

        try {
            // Obsługa Spotify (wyszukuje po tytule na YT)
            if (query.includes('spotify.com')) {
                if (play.is_valid_vals(query) === 'track') {
                    let spotData = await play.spotify(query);
                    const searchResult = await play.search(`${spotData.name} ${spotData.artists[0].name}`, { limit: 1 });
                    if (searchResult.length === 0) return interaction.editReply('Nie znaleziono utworu ze Spotify na YT.');
                    songTitle = searchResult[0].title;
                    songUrl = searchResult[0].url;
                } else {
                    return interaction.editReply('Bot obsługuje na razie pojedyncze utwory ze Spotify.');
                }
            } else {
                // Obsługa YouTube i zwykłego tekstu
                const ytInfo = await play.search(query, { limit: 1 });
                if (ytInfo.length === 0) return interaction.editReply('Nie znaleziono piosenki.');
                songTitle = ytInfo[0].title;
                songUrl = ytInfo[0].url;
            }

            const song = { title: songTitle, url: songUrl };
            let serverQueue = queues.get(interaction.guildId);

            if (!serverQueue) {
                const connection = joinVoiceChannel({
                    channelId: voiceChannel.id,
                    guildId: interaction.guildId,
                    adapterCreator: interaction.guild.voiceAdapterCreator,
                    selfDeaf: true
                });

                const player = createAudioPlayer();
                serverQueue = { textChannel: interaction.channel, connection, player, songs: [] };
                queues.set(interaction.guildId, serverQueue);
                serverQueue.songs.push(song);
                connection.subscribe(player);

                player.on(AudioPlayerStatus.Idle, () => {
                    serverQueue.songs.shift();
                    playSong(interaction.guildId, serverQueue);
                });

                await interaction.editReply(`🎵 Gram teraz: **${song.title}**`);
                playSong(interaction.guildId, serverQueue);
            } else {
                serverQueue.songs.push(song);
                return interaction.editReply(`➕ Dodano do kolejki: **${song.title}**`);
            }
        } catch (err) {
            console.error(err);
            await interaction.editReply('Wystąpił błąd podczas przetwarzania komendy.');
        }
    }
});

client.login(TOKEN);
