import json
import os
import sys

from mutagen.mp4 import MP4


def first_number(value, default=None):
    try:
        item = value[0]
        if isinstance(item, tuple):
            item = item[0]
        return int(item)
    except (IndexError, TypeError, ValueError):
        return default


def main():
    root = os.path.realpath(sys.argv[1])
    dates = []
    tracks = {}

    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not name.startswith('.'))
        for filename in sorted(filenames):
            if not filename.lower().endswith('.m4a'):
                continue
            full_path = os.path.join(directory, filename)
            try:
                tags = MP4(full_path).tags or {}
            except Exception:
                tags = {}
            date = str((tags.get('\xa9day') or [''])[0]).strip()
            if date:
                dates.append(date)
            relative = os.path.relpath(full_path, root).replace(os.sep, '/')
            tracks[relative] = {
                'disc': first_number(tags.get('disk')),
                'track': first_number(tags.get('trkn')),
                'date': date or None,
            }

    # Pre-release singles can retain earlier dates inside an album. The latest
    # track date is the safest representation of the complete album release.
    release_date = max(dates) if dates else None
    print(json.dumps({'releaseDate': release_date, 'tracks': tracks}))


if __name__ == '__main__':
    main()
