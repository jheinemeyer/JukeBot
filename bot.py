from   discord.ext	import commands
import discord
from discord.player import FFmpegPCMAudio

import datetime, re
import asyncio
import math
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

from pandora.clientbuilder	import SettingsDictBuilder
from station import Station, Song

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
		self.add_command(self.pause)
		self.add_command(self.resume)
		self.add_command(self.skip)

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

	@commands.group(name="login", invoke_without_command=True)
	async def login_pandora(self, ctx):
		if ctx.invoked_subcommand == None:
			await ctx.send("Login commands should be done in private messages.")
			return

		''' if not isinstance(ctx.message.channel, discord.PrivateChannel):
			await ctx.send("Re-issue the command in this DM with the syntax `!login as [user] [password...]`")
			return '''

	def login_as_user(self, user_name: str = "", passwd: str = ""):
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
		except:
			raise

		self.client = client

	@login_pandora.command(name="as")
	@predicates.is_private()
	async def pandora_login_as_user(self, ctx, user_name: str = "", *, passwd: str = ""):
		try:
			self.login_as_user(user_name, passwd)
		except Exception as e:
			return await ctx.send("Could not log in: {0}".format(e))

		await ctx.send("Pandora seems to have authenticated.")
		await self.change_presence(game = discord.Game(type = 0, name = "{0.message.author.name}'s music".format(ctx)))
		await self.default_channel.send("{0.message.author.name} has logged me into Pandora!".format(ctx))

	@login_pandora.command()
	@commands.is_owner()
	async def default(self, ctx):
		self.login_as_user(config.default_user, config.default_pass)

		await self.change_presence(game = discord.Game(type = 0, name = "{0.message.author.name}'s music".format(ctx)))
		await self.default_channel.send("{0.message.author.name} has logged me into Pandora!".format(ctx))

	@commands.group()
	async def list(self, ctx):
		if ctx.invoked_subcommand == None:
			await ctx.send("List what?")

	@list.command()
	async def stations(self, ctx: commands.Context):
		try:
			stations = self.client.get_station_list()
		except:
			await ctx.send("I could not fetch any availible stations")
			return

		# I'm assuming the order of the stations returned is durable.
		#   It's a prototype, alright?  It _totally_ won't see production.
		embed = discord.Embed(title = "Available Stations")

		i: int = 0
		station_list: [str] = []
		for station in stations:
			i    += 1
			name  = station.name[:-6] if station.name.endswith(" Radio") else station.name
			station_list.append('#{:>3}:{:>30}'.format(str(i), name))

		embed.description = "```" + "\n".join(station_list) + "```"
		await ctx.send(embed=embed)

	@commands.command()
	@predicates.not_private()
	async def play(self, ctx: commands.Context, index: int = 1):
		if self.client is None:
			await ctx.send("I haven't been logged into Pandora, yet!")
			return

		# Get that fucker's current voice channel.
		voice_state = ctx.author.voice
		if voice_state is None or voice_state.channel is None:
			await ctx.send("You aren't in any voice channel... you tit!")
			return

		stations = self.client.get_station_list()

		index -= 1
		if index < 0 or index > (len(stations) - 1):
			await ctx.send("There are no stations with that index.")
			return

		# Create the station handler
		station: Station = Station(dir = self.directory, loop = self.loop, station = stations[index])
		await station._fill_buffer()
		
		if ctx.voice_client is None:
			voice = await voice_state.channel.connect()
		else:
			voice = ctx.voice_client
			await voice.move_to(voice_state.channel)

		# Kick off the playlist
		await self.play_station(ctx, station=station, voice=voice)

	@commands.command()
	async def pause(self, ctx):
		if ctx.voice_client:
			ctx.voice_client.pause()
			return

		ctx.send("You don't seem to be in a voice channel, {0.author.name}...".format(ctx))

	@commands.command()
	async def resume(self, ctx):
		if ctx.voice_client:
			ctx.voice_client.resume()
			return

		ctx.send("You don't seem to be in a voice channel, {0.author.name}...".format(ctx))

	@commands.command()
	async def skip(self, ctx):
		if ctx.voice_client:
			ctx.voice_client.stop()
			return

		ctx.send("You don't seem to be in a voice channel, {0.author.name}...".format(ctx))

	async def play_station(self, ctx, station, voice):
		song: Song = await station.dequeue()

		def play_next(error):
			if self._closed.is_set():
				return

			print("Reached callback")
			coro = self.play_station(ctx=ctx, station=station, voice=voice)
			fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
			try:
				fut.result()
			except:
				pass

		voice.play(song, after = play_next)

		minutes = int(song.length / 60)
		seconds = song.length % 60
		await ctx.send("Now playing: `{0.name}` (by {0.artist}, {1}:{2:0>2})".format(song, minutes, seconds))


if __name__ == "__main__":
	bot = JukeBot(command_prefix="!")
	bot.run()