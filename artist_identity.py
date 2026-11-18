"""Read an unambiguous library artist ID from tags, without audio probing."""
import json
import os
import sys
from pathlib import Path
from mutagen.flac import FLAC
from mutagen.mp4 import MP4


def artist_identity(folder):
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir() or folder.name.casefold() in ('compilations', 'various artists'):
        return None
    ids = set()
    count = 0
    for directory, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not Path(directory, d).is_symlink()]
        for name in files:
            p = Path(directory, name)
            if name.startswith('.') or p.is_symlink() or p.suffix.lower() not in ('.m4a', '.flac'):
                continue
            count += 1
            if count > 10000:
                return None
            try:
                tags = FLAC(p) if p.suffix.lower() == '.flac' else MP4(p)
                values = tags.get('apple_artist_id' if p.suffix.lower() == '.flac' else 'atID', [])
                if not values:
                    return None  # incomplete identity is not a license to guess
                value = str(values[0])
                if not value.isascii() or not value.isdigit() or not 1 <= len(value) <= 20:
                    return None
                ids.add(value)
                if len(ids) > 1:
                    return None
            except Exception:
                return None
    return next(iter(ids)) if len(ids) == 1 else None


if __name__ == '__main__':
    print(json.dumps({'artistId': artist_identity(sys.argv[1])}))
