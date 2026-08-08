import os
import tempfile
import unittest
from unittest.mock import patch

import worker


class BuildCommandTests(unittest.TestCase):
    def command_for(self, url):
        with tempfile.TemporaryDirectory() as data_dir:
            cookies_path = os.path.join(data_dir, 'cookies.txt')
            with patch.object(worker, 'COOKIES_PATH', cookies_path):
                return worker.build_command(url)

    def test_single_song_is_non_interactive(self):
        command = self.command_for('https://music.apple.com/us/song/example/123')
        self.assertEqual(command[-1], 'https://music.apple.com/us/song/example/123')
        self.assertNotIn('dl', command)
        self.assertNotIn('--artist-auto-select', command)

    def test_album_is_non_interactive(self):
        command = self.command_for('https://music.apple.com/us/album/example/123')
        self.assertEqual(command[-1], 'https://music.apple.com/us/album/example/123')
        self.assertNotIn('dl', command)
        self.assertNotIn('--artist-auto-select', command)

    def test_artist_selects_full_discography(self):
        command = self.command_for('https://music.apple.com/us/artist/example/123?uo=4')
        self.assertEqual(command[-1], 'https://music.apple.com/us/artist/example/123?uo=4')
        self.assertNotIn('dl', command)
        index = command.index('--artist-auto-select')
        self.assertEqual(command[index + 1], 'all-albums')

    def test_artist_word_in_query_does_not_change_url_type(self):
        command = self.command_for(
            'https://music.apple.com/us/album/example/123?ref=artist'
        )
        self.assertNotIn('--artist-auto-select', command)

    def test_cookies_are_added_when_present(self):
        with tempfile.TemporaryDirectory() as data_dir:
            cookies_path = os.path.join(data_dir, 'cookies.txt')
            open(cookies_path, 'w').close()
            with patch.object(worker, 'COOKIES_PATH', cookies_path):
                command = worker.build_command(
                    'https://music.apple.com/us/song/example/123'
                )
        index = command.index('--cookies-path')
        self.assertEqual(command[index + 1], cookies_path)


if __name__ == '__main__':
    unittest.main()
