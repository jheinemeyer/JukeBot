from pandora.models import pandora

from discord.opus   import Encoder
from discord.player import FFmpegPCMAudio
from yarl           import URL
from pathlib        import Path
from asyncio        import AbstractEventLoop

import logging
log: logging.Logger = logging.getLogger(__name__)


class Track:
    def __init__(self, item: pandora.PlaylistItem):
        self.artist_name:   str = item.artist_name
        self.album_name:    str = item.album_name
        self.song_name:     str = item.song_name
        self.track_length:  int = item.track_length

        self.station_id:    str = item.station_id
        self.track_token:   str = item.track_token
        self.album_art_url: URL = URL(item.album_art_url)


# How many calls to `read` equals one second of audio.
READS_PER_SECOND = int(1000 / Encoder.FRAME_LENGTH)

class Song(FFmpegPCMAudio):
    def __init__(self, track: Track, file: Path, **kwargs):
        self.track:     Track = track
        self.file:      Path  = file
        self.remaining: int   = self.track.track_length * READS_PER_SECOND

        # Initialize the underlaying FFmpeg source with the filehandle.
        super().__init__(file.open('rb'), **kwargs, pipe=True)

    @property
    def remaining(self):
        return self.remaining / READS_PER_SECOND

    @property
    def length(self):
        return self.track.track_length

    @property
    def track(self):
        return self.track

    # We can't rewind so we monotonically reduce the remaining time.
    def read(self):
        self.remaining -= 1
        return super().read()

    # The superclass cleanup() closes the process, so we need to try and unlink the file.
    def cleanup(self):
        super().cleanup()

        # If we're shutting down, the containing directory might already be gone.
        try:
            file.unlink()
        except:
            pass


class Station:
    """
    A wrapper for a Pandora station that automates buffering and playlist retrieval
    """

    def __init__(self, directory: Path, loop: AbstractEventLoop, station: pandora.Station):
        
        self.directory: Path              = directory
        self.loop:      AbstractEventLoop = loop
        self.station:   pandora.Station   = station
        self.playlist:  pandora.Playlist  = None
        self.buffer:    [Song]            = []

    @property
    def is_valid(self) -> bool:
        return self.station is not None

    @property
    def name(self) -> str:
        return self.station.name if self.station else None

    @property
    async def queue(self) -> [Track]:
        # We're dead, Jim
        if self.station is None:
            return []

        if self.playlist is None:
            self.playlist = self.station.get_playlist()

        # Grab more if we get low.
        if self.playlist.count() < 2:
            more: Playlist = self.station.get_playlist()
            self.playlist.extend(more)

        return [map(Track, self.playlist)]

    async def peek(self) -> Track:
        return self.queue[0]

    async def dequeue(self) -> Song:
        if len(self.song) == 0:
            await self._buffer()

        song = self.song
        self.song = self.on_deck

        # Schedule the buffer being rebuilt
        self.loop.call_soon(self._buffer, self)

        return song

    async def on_pandora_disconnect(self):
        self.station.


    async def _buffer(self):
        """
        Builds the song buffer asynchronously
        """