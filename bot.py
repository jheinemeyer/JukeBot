import config

from discord.ext.commands	import Bot, Context
from discord				import Client, Server, Channel, PrivateChannel, Message, User, Game, ChannelType
from discord.voice_client	import VoiceClient, StreamPlayer

import sys
from pprint 				import pprint

import urllib3
import audioread

from pandora.models.pandora	import Playlist, Station, PlaylistItem
from pandora.clientbuilder	import SettingsDictBuilder

bot = Bot(command_prefix="!")

client = SettingsDictBuilder({
    "DECRYPTION_KEY": "R=U!LH$O2B#",
    "ENCRYPTION_KEY": "6#26FRL$ZWD",
    "PARTNER_USER": "android",
    "PARTNER_PASSWORD": "AC7IBG09A3DTSYM4R41UJWL07VLN8JI7",
    "DEVICE": "android-generic",
	"QUALITY": "highQuality",
}).build()

logged_in_user: User = None

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
	if ctx.message.author.id == "282652694580297748":
		#await bot.say("No, _YOU_ shut down!  Jerk.")
		await bot.close()
		return

	await bot.say("You are not my master, {0}! (You're {1})".format(ctx.message.author.name, ctx.message.author.id))
	

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
	if not isinstance(ctx.message.channel, PrivateChannel):
		await bot.delete_message(ctx.message)
		await bot.whisper("Re-issue the command in this DM with the syntax `!login as [user] [password...]`")
		return

	await bot.say("User: {0}, Pass: {1}".format(user_name, passwd))
	try:
		client.login(user_name, passwd)
	except Exception as e:
		await bot.say("Could not log in: {0}".format(e.with_traceback()))
		return

	await bot.say("Pandora seems to have authenticated.")

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
	user: User       = message.author
	server: Server   = message.server

	# Get that fucker's current voice channel.
	voice = [channel for channel in server.channels if (channel.type == ChannelType.voice and (user in channel.voice_members))]
	
	if len(voice) == 0:
		await bot.say("You aren't in any voice channel... you tit!")
		return

	channel = voice[0]
	await bot.say("Attempting to join voice channel `{}`".format(channel.name))

	voice: VoiceClient = bot.voice_client_in(server)
	if bot.is_voice_connected(server) == True:
		await voice.move_to(channel)
	else:
		voice = await bot.join_voice_channel(channel)

	playlist: Playlist = client.get_playlist(client.get_station_list()[0].id)

	pending = "Current queue:\n"
	for song in playlist:
		pending += "`{0.song_name}` by `{0.artist_name}`\n".format(song)

	await bot.say(pending)

	song: PlaylistItem = playlist[0]
	pprint(song)

	await bot.say("Now playing `{}` by `{}`".format(song.song_name, song.artist_name))
	url: str = song.audio_url
	u = urllib2.urlopen(url)




	player: StreamPlayer = voice.create_ffmpeg_player(url)
	#player.volume = 0.15
	player.start()
	


bot.run(config.token)
