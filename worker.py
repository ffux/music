import sqlite3
import subprocess
import os
import time
import sys

DATA_DIR = os.environ.get('DATA_DIR', '/data')
MUSIC_DIR = os.environ.get('MUSIC_DIR', '/music')
DB_PATH = os.path.join(DATA_DIR, 'queue.db')
COOKIES_PATH = os.path.join(DATA_DIR, 'cookies.txt')

OUTPUT_TEMPLATE = '{artist_name}/{album_name}/{track_number:02d} {title}'


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


def run_job(job_id, url):
    conn = get_db()
    conn.execute(
        "UPDATE jobs SET status = 'running', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (job_id,)
    )
    conn.commit()

    cmd = [
        'gamdl', 'dl', url,
        '--output-path', os.path.join(MUSIC_DIR, OUTPUT_TEMPLATE),
    ]
    if os.path.exists(COOKIES_PATH):
        cmd += ['--cookies-path', COOKIES_PATH]

    print(f'[worker] Starting job {job_id}: {url}', flush=True)
    append_log(conn, job_id, f'$ {" ".join(cmd)}')

    status = 'done'
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        for line in proc.stdout:
            line = line.rstrip()
            print(f'[gamdl] {line}', flush=True)
            append_log(conn, job_id, line)
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
