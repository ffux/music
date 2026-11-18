import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from mutagen.mp4 import MP4, MP4Cover
from mutagen.flac import FLAC
import flac_conversion as conversion


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def fixture(self, name='song.m4a', bits=16, codec='alac'):
        file = self.root / name
        conversion.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=997:sample_rate=48000:duration=1',
                        '-ac', '2', '-c:a', codec, '-sample_fmt', 's16p' if bits == 16 else 's32p', str(file)])
        tags = MP4(file)
        tags['\xa9nam'] = ['Test song']; tags['\xa9ART'] = ['Test artist']
        tags['\xa9alb'] = ['Test album']; tags['aART'] = ['Various']
        tags['cnID'] = [123]; tags['plID'] = [456]; tags['atID'] = [789]
        tags['trkn'] = [(2, 10)]; tags['disk'] = [(1, 2)]
        tags['cpil'] = True
        tags['\xa9day'] = ['2026-01-01']; tags['\xa9lyr'] = ['Words']
        # Real tiny PNG artwork, independent of external media.
        from PIL import Image
        import io
        image = io.BytesIO(); Image.new('RGB', (4, 4), 'red').save(image, 'PNG')
        tags['covr'] = [MP4Cover(image.getvalue(), imageformat=MP4Cover.FORMAT_PNG)]
        tags.save()
        return file

    def test_16_and_24_bit_lossless_metadata_artwork_original(self):
        for bits in (16, 24):
            source = self.fixture(f'song-{bits}.m4a', bits)
            before = conversion.fingerprint(source)
            result = conversion.convert(source, self.root, 0)
            output = source.with_suffix('.flac')
            self.assertEqual(result['status'], 'converted')
            self.assertEqual(conversion.fingerprint(source), before)
            self.assertEqual(conversion.probe(output), ('flac', 48000, 2, bits))
            self.assertEqual(conversion.pcm_hash(source), conversion.pcm_hash(output))
            tags = FLAC(output)
            self.assertEqual(tags['title'], ['Test song'])
            self.assertEqual(tags['apple_song_id'], ['123'])
            self.assertEqual(tags['tracknumber'], ['2'])
            self.assertEqual(tags['disctotal'], ['2'])
            self.assertEqual(tags['lyrics'], ['Words'])
            self.assertEqual(tags['compilation'], ['1'])
            self.assertEqual(tags.pictures[0].data, bytes(MP4(source)['covr'][0]))
            marker = json.loads(source.with_name('.' + source.name + '.flac.json').read_text())
            self.assertEqual(marker['output']['sha256'], conversion.fingerprint(output)['sha256'])
            self.assertEqual(conversion.convert(source, self.root, 0)['status'], 'unchanged')

    def test_published_timestamp_settles_before_marker(self):
        output = self.root / 'published.flac'
        output.write_bytes(b'fixture')
        calls = []
        def delayed_attribute_update(_):
            calls.append(True)
            if len(calls) == 2:
                stat = output.stat()
                os.utime(output, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
        with patch.object(conversion.time, 'sleep', side_effect=delayed_attribute_update):
            result = conversion.settled_fingerprint(output)
        self.assertGreaterEqual(len(calls), 5)
        self.assertEqual(result, conversion.fingerprint(output))

    def test_aac_is_not_promoted_to_lossless(self):
        source = self.root / 'aac.m4a'
        conversion.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=duration=0.1', '-c:a', 'aac', str(source)])
        self.assertEqual(conversion.convert(source, self.root, 0)['status'], 'skipped')
        self.assertFalse(source.with_suffix('.flac').exists())

    def test_existing_output_never_overwritten(self):
        source = self.fixture(); output = source.with_suffix('.flac'); output.write_bytes(b'keep')
        with self.assertRaises(FileExistsError): conversion.convert(source, self.root, 0)
        self.assertEqual(output.read_bytes(), b'keep')

    def test_failure_cleans_temporary_output_and_preserves_original(self):
        source = self.fixture(); before = conversion.fingerprint(source)
        with patch.object(conversion, 'pcm_hash', side_effect=[b'a', b'b']):
            with self.assertRaisesRegex(RuntimeError, 'does not match'):
                conversion.convert(source, self.root, 0)
        self.assertEqual(list(self.root.iterdir()), [source])
        self.assertEqual(conversion.fingerprint(source), before)

    def test_disk_floor_and_symlink_rejected(self):
        source = self.fixture()
        with self.assertRaisesRegex(RuntimeError, 'Insufficient'):
            conversion.convert(source, self.root, 10**20)
        linked = self.root / 'link.m4a'; linked.symlink_to(source)
        with self.assertRaises(ValueError): conversion.convert(linked, self.root, 0)
        self.assertNotIn(linked, list(conversion.candidates(self.root)))

    def test_only_new_or_changed_candidates(self):
        old = self.fixture('old.m4a'); before = conversion.snapshot(self.root)
        new = self.fixture('new.m4a'); log = []
        conversion.convert_new_files(self.root, before, log.append, 0)
        self.assertTrue(new.with_suffix('.flac').exists())
        self.assertFalse(old.with_suffix('.flac').exists())
        self.assertEqual(len(log), 1)

    def test_cli_dry_run_does_not_write(self):
        source = self.fixture()
        result = subprocess.run([os.sys.executable, 'flac_conversion.py', str(self.root)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['status'], 'candidate')
        self.assertEqual(list(self.root.iterdir()), [source])


if __name__ == '__main__': unittest.main()
