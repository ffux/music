import io
import json
import os
import tempfile
import sqlite3
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import URLError

import worker


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_default_requests_guarded_alac_aac_without_overwrite(self):
        command = worker.build_command('https://music.apple.com/us/album/test/123')
        self.assertIn('--no-config-file', command)
        self.assertEqual(command[command.index('--song-codec-priority') + 1], 'alac,aac')
        self.assertIn('--use-wrapper', command)
        self.assertNotIn('--overwrite', command)

    def test_strict_alac_and_private_endpoints(self):
        os.environ.update(MUSIC_USE_WRAPPER='true', MUSIC_SONG_CODEC_PRIORITY='alac',
                          MUSIC_WRAPPER_URL='http://music-wrapper', MUSIC_DOWNLOAD_SUBDIR='.alac-preview')
        command = worker.build_command('https://music.apple.com/us/artist/test/123')
        self.assertIn('--use-wrapper', command)
        self.assertEqual(command[command.index('--song-codec-priority') + 1], 'alac')
        self.assertEqual(command[command.index('--wrapper-decrypt-host') + 1], 'music-wrapper')
        self.assertTrue(command[command.index('--output-path') + 1].endswith('/.alac-preview'))
        self.assertNotIn('--overwrite', command)

    def test_alac_requires_wrapper(self):
        os.environ.update(MUSIC_SONG_CODEC_PRIORITY='alac', MUSIC_USE_WRAPPER='false')
        with self.assertRaisesRegex(ValueError, 'requires'):
            worker.downloader_settings()

    def test_invalid_configuration_fails(self):
        for key, value in [('MUSIC_USE_WRAPPER', 'yes'), ('MUSIC_SONG_CODEC_PRIORITY', 'ask'),
                           ('MUSIC_WRAPPER_URL', 'http://user:password@wrapper'),
                           ('MUSIC_WRAPPER_DECRYPT_PORT', '65536'),
                           ('MUSIC_DOWNLOAD_SUBDIR', '../outside'),
                           ('MUSIC_DOWNLOAD_SUBDIR', '/outside')]:
            with self.subTest(key=key, value=value), patch.dict(os.environ, {key: value}):
                with self.assertRaises(ValueError):
                    worker.downloader_settings()

    def test_symlink_output_cannot_escape_music(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, os.path.join(root, 'link'))
            with patch.object(worker, 'MUSIC_DIR', root), patch.dict(os.environ, {'MUSIC_DOWNLOAD_SUBDIR': 'link'}):
                with self.assertRaises(ValueError):
                    worker.downloader_settings()

    def check_snapshot(self, snapshot):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(snapshot).encode()
        with patch.object(worker, 'urlopen', return_value=response):
            worker.check_wrapper_ready(dict(use_wrapper=True, wrapper_url='http://wrapper'))

    def test_authenticated_ready_wrapper(self):
        self.check_snapshot({'runtime': {'playback_ready': True}, 'auth': {'state': 'authenticated'}})

    def test_logged_out_wrapper_fails_without_exposing_tokens(self):
        with self.assertRaisesRegex(RuntimeError, 'sign-in required') as error:
            self.check_snapshot({'runtime': {'playback_ready': True}, 'auth': {'state': 'logged_out', 'music_user_token': 'secret'}})
        self.assertNotIn('secret', str(error.exception))

    def test_unready_and_invalid_wrappers_fail(self):
        for snapshot in [None, {}, {'runtime': {'playback_ready': False}}]:
            with self.subTest(snapshot=snapshot), self.assertRaises(RuntimeError):
                self.check_snapshot(snapshot)

    def test_unreachable_wrapper_fails_cleanly(self):
        with patch.object(worker, 'urlopen', side_effect=URLError('private internal details')):
            with self.assertRaisesRegex(RuntimeError, '^Wrapper unavailable'):
                worker.check_wrapper_ready(dict(use_wrapper=True, wrapper_url='http://wrapper'))

    def test_bad_settings_mark_job_error_without_spawning_downloader(self):
        with tempfile.TemporaryDirectory() as data:
            database = os.path.join(data, 'queue.db')
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, status TEXT, log TEXT DEFAULT '', updated_at TEXT)")
            connection.execute("INSERT INTO jobs (id, status) VALUES (1, 'pending')")
            connection.commit()
            connection.close()
            with patch.object(worker, 'DB_PATH', database), patch.dict(os.environ, {'MUSIC_SONG_CODEC_PRIORITY': 'alac', 'MUSIC_USE_WRAPPER': 'false'}), patch.object(worker.subprocess, 'Popen') as spawn:
                worker.run_job(1, 'https://music.apple.com/us/song/example/123')
            spawn.assert_not_called()
            connection = sqlite3.connect(database)
            status, log = connection.execute('SELECT status, log FROM jobs WHERE id=1').fetchone()
            connection.close()
            self.assertEqual(status, 'error')
            self.assertIn('requires MUSIC_USE_WRAPPER', log)

    def test_aac_needs_no_wrapper(self):
        os.environ.update(MUSIC_USE_WRAPPER='false', MUSIC_SONG_CODEC_PRIORITY='aac-web')
        with patch.object(worker, 'urlopen') as request:
            worker.check_wrapper_ready(worker.downloader_settings())
        request.assert_not_called()

    def test_nonzero_downloader_summary_is_recognized(self):
        self.assertTrue(worker.downloader_reported_errors('Finished with 2 error(s)'))
        self.assertFalse(worker.downloader_reported_errors('Finished with 0 error(s)'))
        self.assertFalse(worker.downloader_reported_errors('Downloading track'))
        self.assertTrue(worker.downloader_reported_errors('Requested format is not available'))
        self.assertTrue(worker.downloader_reported_errors('Decryption is not available'))


if __name__ == '__main__':
    unittest.main()
