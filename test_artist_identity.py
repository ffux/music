import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import artist_identity as identity


class ArtistIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'Artist'
        self.root.mkdir()
        (self.root / 'album').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def track(self, name):
        p = self.root / 'album' / name
        p.touch()
        return p

    def test_consistent_ids_without_probing(self):
        self.track('one.m4a'); self.track('two.flac')
        with patch.object(identity, 'MP4', return_value={'atID': [123]}), patch.object(identity, 'FLAC', return_value={'apple_artist_id': ['123']}):
            self.assertEqual(identity.artist_identity(self.root), '123')

    def test_mixed_and_missing_ids_do_not_guess(self):
        self.track('one.m4a'); self.track('two.m4a')
        for values in ([{'atID': [123]}, {'atID': [456]}], [{'atID': [123]}, {}]):
            with patch.object(identity, 'MP4', side_effect=values):
                self.assertIsNone(identity.artist_identity(self.root))

    def test_compilation_hidden_symlink_empty_and_corrupt(self):
        self.assertIsNone(identity.artist_identity(self.root))
        compilations = self.root.parent / 'Compilations'; compilations.mkdir()
        self.assertIsNone(identity.artist_identity(compilations))
        hidden = self.track('.ignore.m4a')
        self.track('link.m4a').unlink(); (self.root / 'album' / 'link.m4a').symlink_to(hidden)
        with patch.object(identity, 'MP4') as read:
            self.assertIsNone(identity.artist_identity(self.root)); read.assert_not_called()
        self.track('broken.m4a')
        with patch.object(identity, 'MP4', side_effect=ValueError('bad')):
            self.assertIsNone(identity.artist_identity(self.root))


if __name__ == '__main__': unittest.main()
