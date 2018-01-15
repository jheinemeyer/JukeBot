from   discord.ext	import commands
import discord
from discord.player import FFmpegPCMAudio

import datetime, re
import asyncio
import logging
import aiohttp
from yarl import URL
import sys
import traceback

import config

from pprint   import pprint
from tempfile import TemporaryDirectory
from pathlib  import Path
from datetime import timedelta
import functools

from pandora.models.pandora	import PlaylistItem
from pandora.clientbuilder	import SettingsDictBuilder

from utils import predicates

log: logging.Logger = logging.getLogger(__name__)

class JukeBot(commands.Bot):
	def __init__(self, **options):
		super().__init__(**options)

		# for staging the files from Pandora
		self.directory       = TemporaryDirectory()
		self.default_channel = None
		self.client          = None
		self.info            = None
		self.add_command(self.shutdown)
		self.add_command(self.login_pandora)
		self.add_command(self.pandora_login_as_user)
		self.add_command(self.default)
		self.add_command(self.list)
		self.add_command(self.stations)
		self.add_command(self.play)

	def run(self):
		super().run(config.token, reconnect=True)

	async def on_ready(self):
		print(f'Logged in: {self.user.name} (ID: {self.user.id})')
		print('------')

		# Cache this crap.
		self.default_channel = self.get_channel(id = config.default_channel)
		self.info            = await self.application_info()
		await self.default_channel.send("```REACTOR ONLINE.\nSENSORS ONLINE.\nWEAPONS ONLINE.\nALL SYSTEMS NOMINAL.```")


	async def on_command_error(self, ctx, error):
		if isinstance(error, commands.NoPrivateMessage):
			await ctx.author.send('This command cannot be used in private messages.')
		elif isinstance(error, commands.DisabledCommand):
			await ctx.author.send('Sorry. This command is disabled and cannot be used.')
		elif isinstance(error, commands.CommandInvokeError):
			print(f'In {ctx.command.qualified_name}:', file=sys.stderr)
			traceback.print_tb(error.original.__traceback__)
			print(f'{error.original.__class__.__name__}: {error.original}', file=sys.stderr)

	@commands.command()
	@commands.is_owner()
	async def shutdown(self, ctx):
		await self.close()

	@commands.group(name="login")
	async def login_pandora(self, ctx):
		if ctx.invoked_subcommand == None:
			await ctx.send("Login commands should be done in private messages.")
			return

		''' if not isinstance(ctx.message.channel, discord.PrivateChannel):
			await ctx.send("Re-issue the command in this DM with the syntax `!login as [user] [password...]`")
			return '''

	@login_pandora.command(name="as")
	@predicates.is_private()
	async def pandora_login_as_user(self, ctx, user_name: str = "", *, passwd: str = ""):
		client = SettingsDictBuilder({
			"DECRYPTION_KEY": "R=U!LH$O2B#",
			"ENCRYPTION_KEY": "6#26FRL$ZWD",
			"PARTNER_USER": "android",
			"PARTNER_PASSWORD": "AC7IBG09A3DTSYM4R41UJWL07VLN8JI7",
			"DEVICE": "android-generic",
			"AUDIO_QUALITY": "highQuality",
		}).build()

		try:
			client.login(user_name, passwd)
		except Exception as e:
			await ctx.send("Could not log in: {0}".format(e))
			return

		self.client = client
		await ctx.send("Pandora seems to have authenticated.")
		await self.change_presence(game = discord.Game(type = 0, name = "{0.message.author.name}'s music".format(ctx)))
		await self.default_channel.send("{0.message.author.name} has logged me into Pandora!".format(ctx))

	@login_pandora.command()
	@commands.is_owner()
	async def default(self, ctx):
		await self.pandora_login_as_user(ctx, config.default_user, config.default_pass)

	@commands.group()
	async def list(self, ctx):
		if ctx.invoked_subcommand == None:
			await ctx.send("List what?")

	@list.command()
	async def stations(self, ctx):
		try:
			stations = self.client.get_station_list()
		except:
			await ctx.send("I could not fetch any availible stations")
			return

		await ctx.send("Available stations:\n```" + "\n".join(map((lambda x: x.name), stations)) + "```")

	@commands.command()
	@predicates.not_private()
	async def play(self, ctx: commands.Context):
		if self.client is None:
			await ctx.send("I haven't been logged into Pandora, yet!")
			return

		# Get that fucker's current voice channel.
		voice_state = ctx.author.voice
		if voice_state is None or voice_state.channel is None:
			await ctx.send("You aren't in any voice channel... you tit!")
			return

		if ctx.voice_client is None:
			voice = await voice_state.channel.connect()
		else:
			voice = ctx.voice_client
			await voice.move_to(voice_state.channel)
		
		# For debugging, first song in first playlist.
		song: PlaylistItem = self.client.get_playlist(self.client.get_station_list()[0].id).pop()
		pprint(song)

		# Create a temporary file.
		url = URL(song.audio_url)
		file: Path = Path(self.directory.name, url.name)
		print(file)

		# Buffer the song into the temp file
		async with aiohttp.ClientSession() as session:
			async with session.get(url) as r:
				with file.open('wb') as fd:
					fd.write(await r.content.read())

		player = FFmpegPCMAudio(file.open('rb'), pipe = True)

		def cleanup(error):
			print("Reached callback")
			coro = self.on_song_done(ctx, file)
			fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
			try:
				fut.result()
			except:
				pass

		voice.play(player, after = cleanup)

		delta = timedelta(seconds = song.track_length)
		await ctx.send("Now playing `{0.song_name}` by `{0.artist_name}` ({1})".format(song, delta))

	async def on_song_done(self, ctx, file):
		file.unlink()
		await ctx.send("Song finsihed")


if __name__ == "__main__":
	bot = JukeBot(command_prefix="!")
	bot.run()