import asyncio
from asyncio        import AbstractEventLoop, Task
from pathlib        import Path

from aiohttp        import ClientSession
from discord.opus   import Encoder
from discord.player import FFmpegPCMAudio
from pandora.models import pandora
from yarl           import URL

import logging
log: logging.Logger = logging.getLogger(__name__)


# How many calls to `read` equals one second of audio.
READS_PER_SECOND = int(1000 / Encoder.FRAME_LENGTH)

class Song(FFmpegPCMAudio):
    def __init__(self, *, track: pandora.PlaylistItem, file: Path, **kwargs):
        self._track:     pandora.PlaylistItem = track
        self._file:      Path                 = file
        self._remaining: int                  = self.track.track_length * READS_PER_SECOND

        # Initialize the underlaying FFmpeg source with the filehandle.
        super().__init__(file.open('rb'), **kwargs, pipe=True)

    @property
    def name(self):
        return self._track.song_name

    @property
    def artist(self):
        return self._track.artist_name

    @property
    def length(self):
        return self._track.track_length

    @property
    def remaining(self) -> float:
        return float(self._remaining / READS_PER_SECOND)

    @property
    def track(self):
        return self._track

    # We can't rewind so we monotonically reduce the remaining time.
    def read(self):
        self._remaining -= 1
        return super().read()

    # The superclass cleanup() closes the process, so we need to try and unlink the file.
    def cleanup(self):
        super().cleanup()

        # If we're shutting down, the temp. directory might already be gone.
        try:
            self._file.unlink()
        except:
            pass


DESIRED_SONGS_IN_BUFFER = 2    # How many songs to keep buffered
CHUNK_SIZE              = 2048 # bytes / chunk for buffering songs

class Station:
    """
    A wrapper for a Pandora station that automates buffering and playlist retrieval
    """

    def __init__(self, dir: Path, loop: AbstractEventLoop, station: pandora.Station):
        self.directory:         Path              = dir
        self.loop:              AbstractEventLoop = loop
        self.station:           pandora.Station   = station

        self.buffer:            [Song]                  = []
        self._playlist:         [pandora.PlaylistItem]  = []
        self.rebuild_scheduled: Task                    = None
        self.session:           ClientSession           = ClientSession()

    @property
    def is_valid(self) -> bool:
        return self.station is not None

    @property
    def name(self) -> str:
        return self.station.name if self.station else None

    @property
    def queue(self) -> [pandora.PlaylistItem]:
        return [map(Song.track, self.buffer), self._playlist]

    @property
    def playlist(self) -> pandora.Playlist:
        # We're dead, Jim
        if self.station is None:
            return []

        if self._playlist is None:
            self._playlist = [self.station.get_playlist()]

        # Grab more if we get low.
        if sum(1 for _ in self._playlist) < 2:
            more: pandora.Playlist = self.station.get_playlist()
            self._playlist.extend(more)

        return self._playlist

    def peek(self) -> pandora.PlaylistItem:
        return self.playlist[0]

    async def dequeue(self) -> Song:
        if not self.buffer:
            if self.rebuild_scheduled and not self.rebuild_scheduled.done():
                await self.rebuild_scheduled
            else:
                await self._fill_buffer()

        # Schedule the buffer being rebuilt, if it isn't already
        if self.rebuild_scheduled is None or self.rebuild_scheduled.done():
            self.rebuild_scheduled = asyncio.ensure_future(
                self._fill_buffer(),
                loop=self.loop
            )

        return self.buffer.pop()

    async def on_pandora_disconnect(self):
        self.station = None


    async def _fill_buffer(self):
        """
        Builds the song buffer asynchronously
        """
        while len(self.buffer) < DESIRED_SONGS_IN_BUFFER:
            track: pandora.PlaylistItem = self.playlist.pop()
            if not track:
                return

            # Create a temporary file.
            url = URL(track.audio_url)
            file: Path = Path(self.directory.name, url.name)

            # Buffer the song into the temp file
            async with self.session.get(url) as resp:
                with file.open('wb') as fd:
                    while True:
                        chunk = await resp.content.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        fd.write(chunk)

            # Add the song to the song buffer
            self.buffer.append(Song(track=track, file=file))
        