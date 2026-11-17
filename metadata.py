import json
import os
import sys
import subprocess

from mutagen.mp4 import MP4
from mutagen.flac import FLAC


def first_number(value, default=None):
    try:
        item = value[0]
        if isinstance(item, tuple):
            item = item[0]
        return int(str(item).split('/')[0])
    except (IndexError, TypeError, ValueError):
        return default


def audio_fidelity(filename):
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name,sample_rate,bits_per_raw_sample,bits_per_sample,duration:format=duration',
            '-of', 'json', filename,
        ], capture_output=True, text=True, timeout=15, check=True)
        probe = json.loads(result.stdout)
        stream = probe['streams'][0]
        duration = None
        for raw in (stream.get('duration'), probe.get('format', {}).get('duration')):
            try:
                value = float(raw)
                if 0 < value < 10 ** 9:
                    duration = value
                    break
            except (TypeError, ValueError):
                pass
        return {
            'duration': duration,
            'codec': str(stream.get('codec_name') or '').upper() or None,
            'sampleRate': int(stream.get('sample_rate') or 0) or None,
            'bitDepth': int(stream.get('bits_per_raw_sample') or stream.get('bits_per_sample') or 0) or None,
        }
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, IndexError):
        return {'codec': None, 'sampleRate': None, 'bitDepth': None, 'duration': None}



def read_tags(filename):
    """Normalize FLAC comments into the legacy metadata keys used by the UI."""
    try:
        if filename.lower().endswith('.flac'):
            tags = FLAC(filename).tags or {}
            mapping = {
                '\xa9nam': 'title', '\xa9ART': 'artist', 'aART': 'albumartist',
                '\xa9alb': 'album', '\xa9day': 'date', '\xa9gen': 'genre',
                'cprt': 'copyright', 'disk': 'discnumber', 'trkn': 'tracknumber',
                'cnID': 'apple_song_id', 'plID': 'apple_album_id', 'atID': 'apple_artist_id',
            }
            return {key: tags[value] for key, value in mapping.items() if value in tags}
        return MP4(filename).tags or {}
    except Exception:
        return {}


def is_converted_source(directory, name):
    if not name.lower().endswith('.m4a') or os.path.basename(name) != name:
        return False
    try:
        marker_path = os.path.join(directory, '.' + name + '.flac.json')
        if os.path.islink(marker_path) or os.path.getsize(marker_path) > 16384:
            return False
        with open(marker_path) as handle:
            marker = json.load(handle)
        if (marker.get('version') != 1 or marker['source']['name'] != name
                or marker['output']['name'] != name[:-4] + '.flac'):
            return False
        for item in (marker['source'], marker['output']):
            filename = os.path.join(directory, item['name'])
            stat = os.stat(filename, follow_symlinks=False)
            if (not os.path.isfile(filename) or os.path.islink(filename)
                    or stat.st_size != item['size'] or stat.st_mtime_ns != item['mtime_ns']):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False

def main():
    root = os.path.realpath(sys.argv[1])
    dates = []
    tracks = {}
    album_info = {}

    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not name.startswith('.')
                             and not os.path.islink(os.path.join(directory, name)))
        for filename in sorted(filenames):
            if filename.startswith('.') or not filename.lower().endswith(('.m4a', '.mp3', '.flac', '.aac', '.opus')):
                continue
            full_path = os.path.join(directory, filename)
            if os.path.islink(full_path) or is_converted_source(directory, filename):
                continue
            tags = read_tags(full_path)
            date = str((tags.get('\xa9day') or [''])[0]).strip()
            if date:
                dates.append(date)
            def tag_text(key):
                return str((tags.get(key) or [''])[0]).strip() or None
            if not album_info and tags:
                album_info = {'title': tag_text('\xa9alb'), 'artist': tag_text('aART') or tag_text('\xa9ART'),
                              'genre': tag_text('\xa9gen'), 'copyright': tag_text('cprt'),
                              'albumId': first_number(tags.get('plID')), 'artistId': first_number(tags.get('atID'))}
            relative = os.path.relpath(full_path, root).replace(os.sep, '/')
            tracks[relative] = {
                'songId': first_number(tags.get('cnID')),
                'albumId': first_number(tags.get('plID')),
                'artistId': first_number(tags.get('atID')),
                'title': tag_text('\xa9nam'),
                'artist': tag_text('\xa9ART'),
                'album': tag_text('\xa9alb'),
                'disc': first_number(tags.get('disk')),
                'track': first_number(tags.get('trkn')),
                'date': date or None,
                **audio_fidelity(full_path),
            }

    # Pre-release singles can retain earlier dates inside an album. The latest
    # track date is the safest representation of the complete album release.
    release_date = max(dates) if dates else None
    print(json.dumps({'releaseDate': release_date, 'album': album_info, 'tracks': tracks}))


if __name__ == '__main__':
    main()
