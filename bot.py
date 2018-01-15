import config

from discord.ext.commands	import Bot, Context
from discord				import Client, Server, Channel, PrivateChannel, Message, Member, User, Game, ChannelType, AppInfo
from discord.voice_client	import VoiceClient, StreamPlayer

import sys
from pprint 				import pprint

from urllib3                import PoolManager, HTTPResponse

import io
import asyncio
import functools
import logging
from tempfile import TemporaryDirectory
import shutil
from pathlib import Path

from pandora                import APIClient
from pandora.models.pandora	import Playlist, Station, PlaylistItem
from pandora.clientbuilder	import SettingsDictBuilder

from logging import Logger
log:    Logger      = logging.getLogger(__name__)
http:   PoolManager = PoolManager()
client: APIClient   = SettingsDictBuilder({
    "DECRYPTION_KEY": "R=U!LH$O2B#",
    "ENCRYPTION_KEY": "6#26FRL$ZWD",
    "PARTNER_USER": "android",
    "PARTNER_PASSWORD": "AC7IBG09A3DTSYM4R41UJWL07VLN8JI7",
    "DEVICE": "android-generic",
	"QUALITY": "highQuality",
}).build()

directory = TemporaryDirectory()

# Our chatbot.
bot: Bot = Bot(command_prefix="!")

@bot.event
async def on_ready():
	print('Logged in as')
	print(bot.user.name)
	print(bot.user.id)
	print('------')

	bullshit: Channel = bot.get_channel(id = "401908558746222592")
	await bot.send_message(bullshit, "```REACTOR ONLINE.\nSENSORS ONLINE.\nWEAPONS ONLINE.\nALL SYSTEMS NOMINAL.```")
	await bot.change_presence(game=Game(name="background noise", type=2))

@bot.event
async def on_error(event):
	await bot.close()
	raise sys.exc_info()

@bot.command(pass_context=True)
async def shutdown(ctx: Context):
	info = await bot.application_info()
	if ctx.message.author.id == info.owner.id:
		await bot.close()
		return

	await bot.say("You are not my master, {0.name}! (You're \"{0.id}\")".format(ctx.message.author))
	

@bot.group(pass_context=True)
async def login(ctx: Context):
	if ctx.invoked_subcommand != None:
		return

	print(ctx)

	if not isinstance(ctx.message.channel, PrivateChannel):
		await bot.whisper("Re-issue the command in this DM with the syntax `!login as [user] [password...]`")
		return

@login.command(pass_context=True, name="as")
async def as_user(ctx: Context, user_name: str = "", *, passwd: str = ""):
	msg: Message = ctx.message

	if not isinstance(msg.channel, PrivateChannel):
		await bot.delete_message(msg)
		await bot.whisper("Re-issue the command in this DM with the syntax `!login as [user] [password...]`")
		return

	await bot.say("User: {0}, Pass: {1}".format(user_name, passwd))
	try:
		client.login(user_name, passwd)
	except Exception as e:
		await bot.say("Could not log in: {0}".format(e.with_traceback()))
		return

	await bot.say("Pandora seems to have authenticated.")
	await bot.change_presence(game = Game(type = 2, name = "{}'s music".format(msg.author.name)))

@login.command()
async def default():
	client.login(config.default_user, config.default_pass)
	await bot.say("Logged into Pandora with SkyMarshal's credentials (you lazy fuck)")

@bot.group(pass_context=True)
async def list(ctx: Context):
	if ctx.invoked_subcommand == None:
		await bot.say("List what?")

@list.command()
async def stations():
	stations = client.get_station_list()
	await bot.say("Available stations:\n```" + "\n".join(map((lambda x: x.name), stations)) + "```")

@bot.command(pass_context=True)
async def play(ctx: Context):
	message: Message = ctx.message
	user:    Member  = message.author
	server:  Server  = message.server

	if client.transport.sync_time is None:
		await bot.say("I haven't been logged into Pandora, yet!")
		return

	if isinstance(message.channel, PrivateChannel):
		await bot.say("I'm sorry, I'm not smart enough to find a voice channel from a direct message.")
		return

	# Get that fucker's current voice channel.
	voice_channel: Channel = user.voice_channel
	#voice = [channel for channel in server.channels if (channel.type == ChannelType.voice and (user in channel.voice_members))]
	
	if voice_channel is None:
		await bot.say("You aren't in any voice channel... you tit!")
		return

	#channel = voice[0]
	#await bot.say("Attempting to join voice channel `{}`".format(voice_channel.name))

	voice: VoiceClient = bot.voice_client_in(server)
	if bot.is_voice_connected(server) == True:
		await voice.move_to(voice_channel)
	else:
		voice: VoiceClient = await bot.join_voice_channel(voice_channel)

	playlist: Playlist = client.get_playlist(client.get_station_list()[0].id)
	song: PlaylistItem = playlist.pop()

	file: Path = Path(directory.name, song.track_token)
	with http.request("GET", song.audio_url, preload_content = False) as resp, file.open('wb') as fd:
  	  shutil.copyfileobj(resp, fd)

	callback = functools.partial(callback_done, bot = bot, file = file, channel = message.channel)
	player: StreamPlayer = voice.create_ffmpeg_player(
		file.open('rb'),
		pipe = True,
		after = callback
	)

	await bot.say("Now playing `{}` by `{}`".format(song.song_name, song.artist_name))
	#player.volume = 0.15
	player.start()

def callback_done(player, bot, file, channel):
	file.unlink()
	pprint(channel)
	bot.send_message(channel, "Song finished")

bot.run(config.token)
