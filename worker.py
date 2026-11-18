import sqlite3
import subprocess
import os
import queue
import shutil
import signal
import threading
import time
import sys
import json
import re
from deployment_control import claim_next_job
from flac_conversion import snapshot
from conversion_recovery import init_plans, prepare_conversion_plan, has_conversion_plan, run_conversion_plan
from urllib.request import urlopen
from urllib.error import URLError
from urllib.parse import urlparse

DATA_DIR = os.environ.get('DATA_DIR', '/data')
MUSIC_DIR = os.environ.get('MUSIC_DIR', '/music')
DB_PATH = os.path.join(DATA_DIR, 'queue.db')
COOKIES_PATH = os.path.join(DATA_DIR, 'cookies.txt')
JOB_TIMEOUT_SECONDS = int(os.environ.get('JOB_TIMEOUT_SECONDS', 6 * 60 * 60))
JOB_IDLE_TIMEOUT_SECONDS = int(os.environ.get('JOB_IDLE_TIMEOUT_SECONDS', 15 * 60))
MIN_FREE_BYTES = int(os.environ.get('MIN_FREE_BYTES', 1024 * 1024 * 1024))

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def append_log(conn, job_id, line):
    conn.execute(
        "UPDATE jobs SET log = log || ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (line + '\n', job_id)
    )
    conn.commit()


def is_artist_url(url):
    parts = [part for part in urlparse(url).path.split('/') if part]
    return 'artist' in parts


def downloader_settings():
    enabled = os.environ.get('MUSIC_USE_WRAPPER', 'true').lower()
    if enabled not in ('true', 'false', '1', '0'):
        raise ValueError('MUSIC_USE_WRAPPER must be true or false')
    use_wrapper = enabled in ('true', '1')
    codec = os.environ.get('MUSIC_SONG_CODEC_PRIORITY', 'alac,aac')
    if codec not in ('aac-web', 'alac', 'alac,aac'):
        raise ValueError('MUSIC_SONG_CODEC_PRIORITY must be aac-web, alac, or alac,aac')
    if 'alac' in codec and not use_wrapper:
        raise ValueError('ALAC requires MUSIC_USE_WRAPPER=true')
    wrapper_url = os.environ.get('MUSIC_WRAPPER_URL', 'http://music-wrapper')
    parsed = urlparse(wrapper_url)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ('', '/')):
        raise ValueError('MUSIC_WRAPPER_URL must be an HTTP(S) base URL without credentials')
    host = os.environ.get('MUSIC_WRAPPER_DECRYPT_HOST', parsed.hostname)
    port = int(os.environ.get('MUSIC_WRAPPER_DECRYPT_PORT', '10020'))
    if not host or not 1 <= port <= 65535:
        raise ValueError('Invalid wrapper decrypt host or port')
    subdir = os.environ.get('MUSIC_DOWNLOAD_SUBDIR', '')
    output = os.path.realpath(os.path.join(MUSIC_DIR, subdir))
    root = os.path.realpath(MUSIC_DIR)
    if os.path.isabs(subdir) or os.path.commonpath([root, output]) != root:
        raise ValueError('MUSIC_DOWNLOAD_SUBDIR must stay inside MUSIC_DIR')
    return dict(use_wrapper=use_wrapper, codec=codec, wrapper_url=wrapper_url.rstrip('/'),
                decrypt_host=host, decrypt_port=port, output=output)


def check_wrapper_ready(settings):
    if not settings['use_wrapper']:
        return
    try:
        with urlopen(settings['wrapper_url'] + '/me', timeout=10) as response:
            # /me contains account tokens. Never log its body.
            snapshot = json.loads(response.read(1024 * 1024))
    except (URLError, OSError, ValueError):
        raise RuntimeError('Wrapper unavailable; check the private wrapper service') from None
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('runtime'), dict):
        raise RuntimeError('Wrapper returned an invalid readiness response')
    if snapshot['runtime'].get('playback_ready') is not True:
        raise RuntimeError('Wrapper playback is not ready; check its native libraries')
    auth = snapshot.get('auth')
    if not isinstance(auth, dict) or auth.get('state') != 'authenticated':
        raise RuntimeError('Wrapper sign-in required; complete Apple Music login and 2FA privately')


def downloader_reported_errors(line):
    summary = re.search(r'Finished with (\d+) error\(s\)', line)
    unavailable = any(term in line.lower() for term in ('format is not available', 'decryption is not available', 'not streamable'))
    return bool(summary and int(summary.group(1)) > 0) or unavailable


def build_command(url, settings=None):
    settings = settings or downloader_settings()
    executable = ['python3', os.path.join(os.path.dirname(__file__), 'gamdl_runner.py')] if settings['codec'] == 'alac,aac' else ['gamdl']
    cmd = executable + ['--no-config-file', '--output-path', settings['output'],
           '--song-codec-priority', settings['codec']]
    if settings['use_wrapper']:
        cmd += ['--use-wrapper', '--wrapper-url', settings['wrapper_url'],
                '--wrapper-decrypt-host', settings['decrypt_host'],
                '--wrapper-decrypt-port', str(settings['decrypt_port'])]
    if os.path.exists(COOKIES_PATH):
        cmd += ['--cookies-path', COOKIES_PATH]
    if is_artist_url(url):
        cmd += ['--artist-auto-select', 'all-albums']
    cmd.append(url)
    return cmd


def terminate_process(proc):
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def stream_process(proc, on_line):
    lines = queue.Queue()

    def read_output():
        try:
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    started_at = last_output_at = time.monotonic()
    last_disk_check = 0

    while True:
        now = time.monotonic()
        if now - started_at > JOB_TIMEOUT_SECONDS:
            terminate_process(proc)
            raise TimeoutError(f'Job exceeded {JOB_TIMEOUT_SECONDS} seconds')
        if now - last_output_at > JOB_IDLE_TIMEOUT_SECONDS:
            terminate_process(proc)
            raise TimeoutError(f'No downloader output for {JOB_IDLE_TIMEOUT_SECONDS} seconds')
        if now - last_disk_check >= 10:
            last_disk_check = now
            free_bytes = shutil.disk_usage(MUSIC_DIR).free
            if free_bytes < MIN_FREE_BYTES:
                terminate_process(proc)
                raise RuntimeError(
                    f'Download stopped to preserve disk space '
                    f'({free_bytes // (1024 * 1024)} MiB free)'
                )

        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            continue
        if line is None:
            break
        last_output_at = time.monotonic()
        on_line(line.rstrip())


def run_job(job_id, url):
    conn = get_db()
    conn.execute(
        "UPDATE jobs SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (job_id,)
    )
    conn.commit()

    print(f'[worker] Starting job {job_id}: {url}', flush=True)

    status = 'done'
    try:
        settings = downloader_settings()
        if settings['codec'] == 'alac,aac':
            append_log(conn, job_id, 'Quality policy: highest available ALAC, then highest AAC only when a valid source playlist has no ALAC. Authentication, network and storage failures remain errors. Existing files are kept.')
        elif settings['codec'] == 'alac':
            append_log(conn, job_id, 'Quality policy: highest available ALAC; no AAC fallback. Source resolution varies. Existing files are kept.')
        else:
            append_log(conn, job_id, f"Quality policy: {settings['codec']}")
        convert_flac = os.environ.get('MUSIC_CONVERT_ALAC_TO_FLAC', 'true').lower()
        if convert_flac not in ('true', 'false', '1', '0'):
            raise ValueError('MUSIC_CONVERT_ALAC_TO_FLAC must be true or false')
        convert_flac = convert_flac in ('true', '1')
        before = snapshot(settings['output']) if convert_flac else {}
        check_wrapper_ready(settings)
        cmd = build_command(url, settings)
        append_log(conn, job_id, f'$ {" ".join(cmd)}')
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

        def handle_line(line):
            nonlocal status
            if downloader_reported_errors(line):
                status = 'error'
            print(f'[gamdl] {line}', flush=True)
            append_log(conn, job_id, line)

        stream_process(proc, handle_line)
        proc.wait()
        if proc.returncode != 0:
            status = 'error'
            append_log(conn, job_id, f'[exited with code {proc.returncode}]')
        if status == 'done' and convert_flac:
            prepare_conversion_plan(conn, job_id, settings['output'], before)
            append_log(conn, job_id, 'Converting newly downloaded ALAC to verified FLAC; originals are retained. AAC is unchanged.')
            run_conversion_plan(conn, job_id, lambda line: append_log(conn, job_id, line), MIN_FREE_BYTES)
        if status == 'error':
            append_log(conn, job_id, 'Download incomplete. Check the errors above; availability or download failure remains unresolved; see the actual file quality for completed tracks.')
    except FileNotFoundError:
        msg = 'Error: a required executable or file is missing. Check gamdl, ffmpeg and ffprobe installation and the music mount.'
        print(msg, flush=True)
        append_log(conn, job_id, msg)
        status = 'error'
    except Exception as e:
        msg = f'Error: {e}'
        print(msg, flush=True)
        append_log(conn, job_id, msg)
        status = 'error'

    conn.execute(
        "UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, job_id)
    )
    conn.commit()
    conn.close()
    print(f'[worker] Job {job_id} finished: {status}', flush=True)


def recover_interrupted_jobs():
    conn = get_db()
    init_plans(conn)
    jobs = conn.execute("SELECT id FROM jobs WHERE status='running' ORDER BY id").fetchall()
    for job in jobs:
        job_id = job['id']
        status = 'error'
        if has_conversion_plan(conn, job_id):
            try:
                append_log(conn, job_id, 'Resuming persisted FLAC conversion after restart; no redownload.')
                run_conversion_plan(conn, job_id, lambda line: append_log(conn, job_id, line), MIN_FREE_BYTES)
                status = 'done'
                append_log(conn, job_id, 'FLAC recovery completed; originals retained.')
            except Exception as error:
                append_log(conn, job_id, f'FLAC recovery stopped safely: {error}')
        else:
            append_log(conn, job_id, '[worker restarted before download completion was checkpointed; manual retry required]')
        conn.execute('UPDATE jobs SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', (status, job_id))
        conn.commit()
    conn.close()


def main():
    # Wait for DB and data dir to be ready
    print('[worker] Waiting for database...', flush=True)
    while not os.path.exists(DATA_DIR):
        time.sleep(2)

    for attempt in range(30):
        try:
            conn = get_db()
            conn.execute('SELECT 1 FROM jobs LIMIT 1')
            conn.close()
            break
        except Exception:
            time.sleep(2)
    else:
        print('[worker] Could not connect to database after 60s, exiting', flush=True)
        sys.exit(1)

    print('[worker] Ready, polling for jobs...', flush=True)

    recover_interrupted_jobs()

    while True:
        try:
            conn = get_db()
            job = claim_next_job(conn)
            conn.close()

            if job:
                run_job(job['id'], job['url'])
            else:
                time.sleep(2)
        except Exception as e:
            print(f'[worker] Error: {e}', flush=True)
            time.sleep(5)


if __name__ == '__main__':
    main()
