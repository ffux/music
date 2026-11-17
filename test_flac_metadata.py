import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from mutagen.flac import FLAC
import metadata

class FlacMetadataTests(unittest.TestCase):
    def test_real_flac_tags_fidelity_and_conversion_visibility(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            flac = root / '01 Song.flac'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=48000:duration=0.1',
                            '-c:a', 'flac', '-sample_fmt', 's32', str(flac)], check=True)
            tags = FLAC(flac)
            for name, value in {'title':'Song', 'artist':'Artist', 'albumartist':'Album Artist',
                                'album':'Album', 'date':'2026-01-02', 'genre':'Electronic',
                                'copyright':'Fixture', 'tracknumber':'1/10', 'discnumber':'2',
                                'APPLE_SONG_ID':'123', 'APPLE_ALBUM_ID':'456',
                                'APPLE_ARTIST_ID':'789'}.items():
                tags[name] = value
            tags.save()
            source = root / '01 Song.m4a'
            source.write_bytes(b'original fixture remains unchanged')
            def identity(file):
                st = file.stat()
                return {'name':file.name, 'size':st.st_size, 'mtime_ns':st.st_mtime_ns,
                        'mtimeMs':st.st_mtime_ns / 1000000, 'sha256':'a'*64}
            marker = {'version':1, 'source':identity(source), 'output':identity(flac)}
            (root / '.01 Song.m4a.flac.json').write_text(json.dumps(marker))
            (root / '.partial.flac').write_bytes(b'partial')
            self.assertTrue(metadata.is_converted_source(temp, source.name))
            result = json.loads(subprocess.check_output([sys.executable, 'metadata.py', temp]))
            self.assertEqual(list(result['tracks']), ['01 Song.flac'])
            track = result['tracks']['01 Song.flac']
            self.assertEqual((track['title'],track['songId'],track['albumId'],track['artistId']),
                             ('Song',123,456,789))
            self.assertEqual((track['disc'],track['track']), (2,1))
            self.assertEqual((track['codec'],track['sampleRate'],track['bitDepth']), ('FLAC',48000,24))
            self.assertEqual(result['album']['artist'], 'Album Artist')
            self.assertEqual(result['releaseDate'], '2026-01-02')
            self.assertGreater(track['duration'], 0)
            flac.unlink()
            self.assertFalse(metadata.is_converted_source(temp, source.name))
            flac.symlink_to(source)
            self.assertFalse(metadata.is_converted_source(temp, source.name))
            self.assertEqual(source.read_bytes(), b'original fixture remains unchanged')

    def test_number_parsing_preserves_mp4_tuple_and_vorbis_totals(self):
        self.assertEqual(metadata.first_number([(3, 12)]), 3)
        self.assertEqual(metadata.first_number(['3/12']), 3)
        self.assertIsNone(metadata.first_number(['bad']))

if __name__ == '__main__':
    unittest.main()
