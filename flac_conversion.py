"""Verified, non-destructive conversion of local ALAC files to native FLAC.

No downloader credentials or network access are needed. CLI defaults to a dry run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from mutagen.mp4 import MP4
from mutagen.flac import FLAC, Picture

TAG_MAP = {'\xa9nam': 'TITLE', '\xa9ART': 'ARTIST', 'aART': 'ALBUMARTIST',
           '\xa9alb': 'ALBUM', '\xa9day': 'DATE', '\xa9gen': 'GENRE',
           '\xa9wrt': 'COMPOSER', 'cprt': 'COPYRIGHT', '\xa9cmt': 'COMMENT',
           '\xa9lyr': 'LYRICS', 'sonm': 'TITLESORT', 'soar': 'ARTISTSORT',
           'soaa': 'ALBUMARTISTSORT', 'soal': 'ALBUMSORT', 'soco': 'COMPOSERSORT',
           'cnID': 'APPLE_SONG_ID', 'plID': 'APPLE_ALBUM_ID', 'atID': 'APPLE_ARTIST_ID',
           'tmpo': 'BPM', 'cpil': 'COMPILATION'}


def run(args, timeout=1800):
    return subprocess.run(args, check=True, capture_output=True, timeout=timeout)


def probe(path):
    data = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', 'a',
                          '-show_streams', '-of', 'json', str(path)], 30).stdout)
    streams = data.get('streams', [])
    if len(streams) != 1:
        raise ValueError('Expected exactly one audio stream')
    stream = streams[0]
    return (stream['codec_name'], int(stream['sample_rate']), int(stream['channels']),
            int(stream.get('bits_per_raw_sample') or stream.get('bits_per_sample') or 0))


def pcm_hash(path):
    # Same canonical sample representation for either lossless codec, with no resampling.
    return run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-map', '0:a:0',
                '-c:a', 'pcm_s32le', '-f', 'hash', '-hash', 'sha256', '-']).stdout.strip()


def fingerprint(path):
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return dict(name=path.name, size=stat.st_size, mtime_ns=stat.st_mtime_ns,
                mtimeMs=stat.st_mtime_ns / 1_000_000, sha256=digest.hexdigest())


def copy_tags(source, output):
    tags = MP4(source).tags or {}
    flac = FLAC(output)
    flac.clear()
    for source_key, target_key in TAG_MAP.items():
        if source_key in tags:
            values = tags[source_key]
            if not isinstance(values, (list, tuple)):
                values = [values]
            flac[target_key] = [str(int(v)) if isinstance(v, bool) else str(v)
                                for v in values]
    for source_key, number, total in [('trkn', 'TRACKNUMBER', 'TRACKTOTAL'),
                                      ('disk', 'DISCNUMBER', 'DISCTOTAL')]:
        if tags.get(source_key):
            index, count = tags[source_key][0]
            flac[number] = [str(index)]
            if count:
                flac[total] = [str(count)]
    # Preserve free-form metadata (e.g. replay gain) under its descriptive key.
    for key, values in tags.items():
        if key.startswith('----:com.apple.iTunes:'):
            name = key.rsplit(':', 1)[1]
            try:
                flac[name] = [bytes(value).decode('utf-8') for value in values]
            except (UnicodeError, ValueError):
                pass
    flac.clear_pictures()
    for cover in tags.get('covr', []):
        picture = Picture()
        picture.type = 3
        picture.mime = 'image/png' if cover.imageformat == cover.FORMAT_PNG else 'image/jpeg'
        picture.data = bytes(cover)
        flac.add_picture(picture)
    flac.save()
    reread = FLAC(output)
    if dict(reread.tags or {}) != dict(flac.tags or {}) or [p.data for p in reread.pictures] != [p.data for p in flac.pictures]:
        raise RuntimeError('FLAC metadata readback mismatch')


def checked_source(source, root):
    root = Path(root).resolve(strict=True)
    source = Path(source).absolute()
    if source.is_symlink() or not source.is_file():
        raise ValueError('Source must be a regular file, not a symlink')
    resolved = source.resolve(strict=True)
    if not resolved.is_relative_to(root) or source != resolved:
        raise ValueError('Source must stay in the music directory without symlink components')
    if source.suffix.lower() != '.m4a':
        raise ValueError('Only M4A sources are candidates')
    return source


def convert(source, root, min_free_bytes=1024**3):
    """Return a result; never remove or overwrite source or an existing output."""
    started = time.monotonic()
    source = checked_source(source, root)
    info = probe(source)
    if info[0] != 'alac':
        return {'status': 'skipped', 'reason': 'not ALAC', 'source': str(source)}
    if info[3] not in (16, 24):
        raise ValueError('Only verified 16-bit and 24-bit ALAC conversion is supported')
    output = source.with_suffix('.flac')
    marker = source.with_name('.' + source.name + '.flac.json')
    if output.is_file() and marker.is_file() and not output.is_symlink() and not marker.is_symlink():
        try:
            record = json.loads(marker.read_text())
            if (record.get('version') == 1 and record.get('source') == fingerprint(source)
                    and record.get('output') == fingerprint(output)):
                return {'status': 'unchanged', 'source': str(source), 'output': str(output)}
        except (OSError, ValueError):
            pass
    if output.exists() or output.is_symlink() or marker.exists() or marker.is_symlink():
        raise FileExistsError('FLAC or conversion marker already exists; refusing to overwrite')
    # Reserve uncompressed PCM size, metadata and overhead even for highly
    # compressible sources, plus the disk floor.
    duration = MP4(source).info.length
    required = int(duration * info[1] * info[2] * (info[3] // 8) * 1.1) + source.stat().st_size + 1024**2
    if shutil.disk_usage(source.parent).free < min_free_bytes + required:
        raise RuntimeError('Insufficient free space for a retained-original conversion')
    before = fingerprint(source)
    fd, temporary = tempfile.mkstemp(prefix='.flac-conversion-', suffix='.flac', dir=source.parent)
    os.close(fd)
    temp = Path(temporary)
    try:
        run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-y', '-i', str(source),
             '-map', '0:a:0', '-map_metadata', '-1', '-c:a', 'flac',
             '-compression_level', '5', str(temp)])
        copy_tags(source, temp)
        if probe(temp) != ('flac', *info[1:]):
            raise RuntimeError('Sample rate, channels or bit depth changed')
        if pcm_hash(source) != pcm_hash(temp):
            raise RuntimeError('Decoded audio does not match source')
        if fingerprint(source) != before:
            raise RuntimeError('Source changed during conversion')
        if shutil.disk_usage(source.parent).free < min_free_bytes:
            raise RuntimeError('Free-space floor reached; output not published')
        with temp.open('rb') as handle:
            os.fsync(handle.fileno())
        # Hard link publishes atomically and fails rather than overwriting another writer.
        os.link(temp, output)
        record = {'version': 1, 'source': before, 'output': fingerprint(output)}
        with marker.open('x') as handle:
            json.dump(record, handle)
            handle.flush()
            os.fsync(handle.fileno())
        return {'status': 'converted', 'source': str(source), 'output': str(output),
                'elapsedSeconds': round(time.monotonic() - started, 3),
                'sourceBytes': before['size'], 'outputBytes': record['output']['size']}
    except Exception:
        # A published, verified FLAC is deliberately retained if marker creation fails.
        # It remains visible alongside its original; subsequent runs won't overwrite it.
        raise
    finally:
        temp.unlink(missing_ok=True)


def candidates(root):
    root = Path(root).resolve(strict=True)
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in sorted(dirs) if not name.startswith('.')
                   and not Path(directory, name).is_symlink()]
        for name in sorted(files):
            source = Path(directory, name)
            if not name.startswith('.') and source.suffix.lower() == '.m4a' and not source.is_symlink():
                yield source


def snapshot(root):
    if not Path(root).exists():
        return {}
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in candidates(root)}


def convert_new_files(root, before, log, min_free_bytes=1024**3):
    for source, identity in snapshot(root).items():
        if before.get(source) == identity:
            continue
        result = convert(source, root, min_free_bytes)
        log('FLAC: ' + json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--apply', action='store_true', help='Convert candidates; defaults to dry run')
    parser.add_argument('--min-free-bytes', type=int, default=1024**3)
    args = parser.parse_args()
    failures = 0
    for source in candidates(args.root):
        try:
            if not args.apply:
                result = {'status': 'candidate' if probe(source)[0] == 'alac' else 'skipped', 'source': str(source)}
            else:
                result = convert(source, args.root, args.min_free_bytes)
            print(json.dumps(result), flush=True)
        except Exception as error:
            failures += 1
            print(json.dumps({'status': 'error', 'source': str(source), 'error': str(error)}), flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
