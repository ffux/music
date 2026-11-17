import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
from gamdl.interface.song import AppleMusicSongInterface
from gamdl.interface.enums import SongCodec
from gamdl_runner import guarded_nonweb


def manifest(*variants):
    return '#EXTM3U\n' + ''.join(
        f'#EXT-X-STREAM-INF:BANDWIDTH={rate},AVERAGE-BANDWIDTH={rate},CODECS="{codec}",AUDIO="{group}"\n{group}.m3u8\n'
        for group, codec, rate in variants)


class QualityTests(unittest.IsolatedAsyncioTestCase):
    def song(self, text):
        response = httpx.Response(200, text=text, request=httpx.Request('GET', 'https://example.test/master.m3u8'))
        song = object.__new__(AppleMusicSongInterface)
        song.codec_priority = [SongCodec.ALAC, SongCodec.AAC]
        song.base = SimpleNamespace(get_response=AsyncMock(return_value=response))
        song._get_m3u8_master_url = AsyncMock(return_value='https://example.test/master.m3u8')
        song._get_stream_info_nonweb = guarded_nonweb.__get__(song)
        song._get_stream_info_from_playlist = AsyncMock(side_effect=lambda url, selected, **kwargs: selected)
        return song

    async def test_alac_wins_and_highest_bandwidth_selected(self):
        song = self.song(manifest(('audio-stereo-256','mp4a.40.2',256000),('audio-alac-1','alac',700000),('audio-alac-2','alac',2000000)))
        result = await song.get_stream_info('1',False)
        self.assertEqual(result['stream_info']['average_bandwidth'],2000000)
        self.assertEqual(song.base.get_response.await_count,1)

    async def test_absent_alac_selects_highest_aac(self):
        song = self.song(manifest(('audio-stereo-128','mp4a.40.2',128000),('audio-stereo-256','mp4a.40.2',256000)))
        result = await song.get_stream_info('1',False)
        self.assertEqual(result['stream_info']['average_bandwidth'],256000)

    async def test_http_and_timeout_do_not_try_aac(self):
        for error in [httpx.ReadTimeout('timeout'), httpx.HTTPStatusError('failed',request=httpx.Request('GET','https://example.test'),response=httpx.Response(401))]:
            song = self.song('')
            song.base.get_response.side_effect=error
            with self.assertRaises(type(error)):
                await song.get_stream_info('1',False)
            self.assertEqual(song.base.get_response.await_count,1)
            song._get_stream_info_from_playlist.assert_not_awaited()

    async def test_missing_or_malformed_manifest_does_not_try_aac(self):
        for content in ['', '<html>error</html>', '#EXTM3U\n#EXTINF:2\nsegment.m4a', '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2\na.m3u8']:
            song=self.song(content)
            with self.assertRaises(RuntimeError):
                await song.get_stream_info('1',False)
            self.assertEqual(song.base.get_response.await_count,1)
        song=self.song('')
        song._get_m3u8_master_url.return_value=None
        with self.assertRaises(RuntimeError):
            await song.get_stream_info('1',False)
        song.base.get_response.assert_not_awaited()

    async def test_selected_alac_read_or_io_failure_never_retries_aac(self):
        song=self.song(manifest(('audio-alac-1','alac',700000),('audio-stereo-256','mp4a.40.2',256000)))
        for error in [OSError('disk full'),RuntimeError('decrypt failed'),httpx.ReadTimeout('stream timeout')]:
            song._get_stream_info_from_playlist=AsyncMock(side_effect=error)
            with self.assertRaises(type(error)):
                await song.get_stream_info('1',False)
            self.assertEqual(song._get_stream_info_from_playlist.await_count,1)
