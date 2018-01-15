import pandora
from pandora.models.pandora	import PlaylistItem, Playlist, Station

from discord.opus   import Encoder
from discord.ext    import commands
from discord.player import FFmpegPCMAudio
from yarl import URL



import logging
log: logging.Logger = logging.getLogger(__name__)


class Track:
    def __init__(self, item: PlaylistItem):
        self.artist_name:   str = item.artist_name
        self.album_name:    str = item.album_name
        self.song_name:     str = item.song_name
        self.track_length:  int = item.track_length

        self.station_id:    str = item.station_id
        self.track_token:   str = item.track_token
        self.album_art_url: URL = URL(item.album_art_url)



# How many calls to `read` equals one second of audio.
READS_PER_SECOND = int(1000 / Encoder.FRAME_LENGTH)

class TimeAwareAudioSource(FFmpegPCMAudio):
    def __init__(self, *args, **kwargs):
        self.track:     Track = kwargs.pop('track')
        self.remaining: int   = self.track.track_length * READS_PER_SECOND

        super().__init__(self, *args, **kwargs)

    # We can't really rewind, so just monotonically reduce the remaining time.
    def read(self):
        self.remaining -= 1
        return super().read()

    @property
    def remaining(self):
        return self.remaining / READS_PER_SECOND

    # delegate to the track, I guess?
    @property
    def __call__(self, method, *args, **kwargs):
        return getattr(self.track, method)(*args, **kwargs)


class PlaylistHandler:
    def __init__(self, bot, station):
        self.bot       commands.Bot         = bot
        self.station:  Station              = station
        self.playlist: Playlist             = None

        self.playing:  TimeAwareAudioSource = None
        self.loaded:   List[PlaylistLitem]  = []

    @property
    def name(self):
        return self.station.name

    def queue(self):
        if self.playlist is None:
            self.playlist = self.station.get_playlist()

        # Grab more if we get low.
        if self.playlist.count() < 2:
            more: Playlist = self.station.get_playlist()
            self.playlist.extend(more)

        return [map(Track, self.playlist)]

    def 
