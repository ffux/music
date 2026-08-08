import sqlite3
import subprocess
import os
import queue
import shutil
import signal
import threading
import time
import sys
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


def build_command(url):
    cmd = ['gamdl', '--output-path', MUSIC_DIR]
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

    cmd = build_command(url)

    print(f'[worker] Starting job {job_id}: {url}', flush=True)
    append_log(conn, job_id, f'$ {" ".join(cmd)}')

    status = 'done'
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )

        def handle_line(line):
            print(f'[gamdl] {line}', flush=True)
            append_log(conn, job_id, line)

        stream_process(proc, handle_line)
        proc.wait()
        if proc.returncode != 0:
            status = 'error'
            append_log(conn, job_id, f'[exited with code {proc.returncode}]')
    except FileNotFoundError:
        msg = 'Error: gamdl not found. Check installation.'
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

    # A container restart kills its child downloader. Mark those abandoned jobs
    # clearly instead of leaving them stuck in the running state forever.
    conn = get_db()
    recovered = conn.execute(
        "UPDATE jobs SET status = 'error', "
        "log = log || '[worker restarted before this job finished]\\n', "
        "updated_at = CURRENT_TIMESTAMP WHERE status = 'running'"
    ).rowcount
    conn.commit()
    conn.close()
    if recovered:
        print(f'[worker] Marked {recovered} interrupted job(s) as error', flush=True)

    while True:
        try:
            conn = get_db()
            job = conn.execute(
                "SELECT * FROM jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1"
            ).fetchone()
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
