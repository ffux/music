#!/usr/bin/env python3
"""Explicit lifecycle for the wrapper companion; never called by app deployments."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
PROJECT = 'music-wrapper'


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True, capture_output=capture)


def compose(release, *args):
    return run('docker', 'compose', '--project-name', PROJECT,
               '--env-file', str(release / 'compose.env'),
               '-f', str(release / 'compose.yaml'), *args)


def readiness():
    # /health has no account/session tokens. Never print /me responses.
    with urlopen('http://127.0.0.1:18080/health', timeout=3) as response:
        data = json.loads(response.read(65536))
    return isinstance(data, dict) and data.get('status') == 'ok'


def wait_healthy():
    for attempt in range(10):
        try:
            if readiness():
                return
        except (OSError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError('Wrapper liveness failed; inspect its private logs')


def pointer(state, name):
    link = state / name
    if not link.is_symlink():
        return None
    target = link.resolve()
    if target.parent != (state / 'releases').resolve() or not target.is_dir():
        raise RuntimeError('Invalid release pointer')
    return target


def set_pointer(state, name, release):
    temporary = state / (name + '.new')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(release)
    temporary.replace(state / name)


def apply_release(state, release):
    current = pointer(state, 'current')
    try:
        compose(release, 'up', '-d', '--no-build', '--pull', 'never', 'music-wrapper')
        wait_healthy()
    except (subprocess.CalledProcessError, RuntimeError):
        if current:
            compose(current, 'up', '-d', '--no-build', '--pull', 'never', 'music-wrapper')
            wait_healthy()
        else:
            compose(release, 'stop', 'music-wrapper')
        raise
    if current and current != release:
        set_pointer(state, 'previous', current)
    set_pointer(state, 'current', release)


def prepare_release(state):
    source = os.environ.get('WRAPPER_SOURCE_DIR')
    if not source:
        raise RuntimeError('Set WRAPPER_SOURCE_DIR to the prepared upstream checkout')
    source = str(Path(source).resolve())
    if any(character in source for character in "\n\r'$\\"):
        raise RuntimeError('Unsupported wrapper source path')
    run('git', '-C', str(HERE.parent), 'diff', '--quiet', 'HEAD', '--', 'wrapper')
    revision = run('git', '-C', str(HERE.parent), 'rev-parse', 'HEAD', capture=True).stdout.strip()
    image = run('docker', 'image', 'inspect', 'music-wrapper:100e0a8',
                '--format', '{{.Id}}', capture=True).stdout.strip()
    if not image.startswith('sha256:') or len(image) != 71:
        raise RuntimeError('Build the reviewed wrapper image before applying')
    release = state / 'releases' / (revision + '-' + image[7:19])
    if not release.exists():
        release.mkdir(parents=True, mode=0o700)
        shutil.copyfile(HERE / 'compose.yaml', release / 'compose.yaml')
        (release / 'compose.env').write_text(
            f"WRAPPER_SOURCE_DIR='{source}'\nMUSIC_WRAPPER_IMAGE={image}\n")
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'apply', 'rollback', 'status', 'stop'])
    parser.add_argument('--state-dir', default='/var/lib/music-wrapper')
    options = parser.parse_args()
    state = Path(options.state_dir).resolve()
    if options.action in ('apply', 'rollback', 'stop'):
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = (state / 'operation.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another wrapper lifecycle operation is running') from None
    if options.action == 'build':
        run('sh', str(HERE / 'build.sh'))
        return
    if options.action in ('status', 'stop', 'rollback'):
        release = pointer(state, 'previous' if options.action == 'rollback' else 'current')
        if not release:
            raise RuntimeError('No recorded companion release')
        if options.action == 'status':
            compose(release, 'ps')
            print('Wrapper HTTP liveness:', 'ok' if readiness() else 'not ready')
        elif options.action == 'stop':
            compose(release, 'stop', 'music-wrapper')
        else:
            apply_release(state, release)
        return
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    apply_release(state, prepare_release(state))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
