"""One-time upgrade guard for legacy workers that do not understand a drain.

python3 bootstrap_control.py [--db PATH] begin|status|end TOKEN
Persistent SQLite triggers reject entering 'running'; pending inserts remain
allowed. No expiry. Only the matching owner can remove the exact trigger pair.
Call end only after independently verifying the replacement app supports drain,
or when explicitly abandoning the upgrade and restoring legacy operation.
"""
import argparse
import json
import os
import sqlite3

TRIGGERS = {
    'music_bootstrap_running_update': "CREATE TRIGGER music_bootstrap_running_update BEFORE UPDATE OF status ON jobs WHEN NEW.status = 'running' BEGIN SELECT RAISE(ABORT, 'Music deployment bootstrap guard active'); END",
    'music_bootstrap_running_insert': "CREATE TRIGGER music_bootstrap_running_insert BEFORE INSERT ON jobs WHEN NEW.status = 'running' BEGIN SELECT RAISE(ABORT, 'Music deployment bootstrap guard active'); END",
}


def control(db_path, action, token):
    if not isinstance(token, str) or not token or len(token) > 200:
        raise ValueError('A bounded nonempty owner token is required')
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('CREATE TABLE IF NOT EXISTS deployment_drain (id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL)')
        conn.execute('CREATE TABLE IF NOT EXISTS deployment_bootstrap_guard (id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL)')
        drain = conn.execute('SELECT token FROM deployment_drain WHERE id=1').fetchone()
        owner = conn.execute('SELECT token FROM deployment_bootstrap_guard WHERE id=1').fetchone()
        present = dict(conn.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN (?,?)", tuple(TRIGGERS)))
        if drain and drain[0] != token:
            raise RuntimeError('Drain is owned by another controller')
        if owner and owner[0] != token:
            raise RuntimeError('Bootstrap guard is owned by another controller')
        active = bool(owner)
        if active:
            if not drain or present != TRIGGERS:
                raise RuntimeError('Partial or modified bootstrap guard; manual review required')
        elif present:
            raise RuntimeError('Unowned bootstrap triggers; refusing to modify them')
        running = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]
        if action == 'begin':
            if running:
                raise RuntimeError('Active jobs must finish before installing bootstrap guard')
            if not active:
                for sql in TRIGGERS.values():
                    conn.execute(sql)
                conn.execute('INSERT INTO deployment_bootstrap_guard(id,token) VALUES(1,?)', (token,))
                conn.execute('INSERT OR IGNORE INTO deployment_drain(id,token) VALUES(1,?)', (token,))
            active = True
        elif action == 'end':
            if not active:
                raise RuntimeError('No matching active bootstrap guard')
            if running:
                raise RuntimeError('Unexpected running job; manual review required')
            for name in TRIGGERS:
                conn.execute('DROP TRIGGER ' + name)
            conn.execute('DELETE FROM deployment_bootstrap_guard WHERE id=1 AND token=?', (token,))
            conn.execute('DELETE FROM deployment_drain WHERE id=1 AND token=?', (token,))
            active = False
        elif action != 'status':
            raise ValueError('Unknown bootstrap action')
        pending = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
        conn.commit()
        return {'active': active, 'drained': active and running == 0, 'running': running, 'pending': pending, 'legacyGuard': active}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=os.path.join(os.environ.get('DATA_DIR', '/data'), 'queue.db'))
    parser.add_argument('action', choices=['begin', 'status', 'end'])
    parser.add_argument('token')
    args = parser.parse_args()
    try:
        print(json.dumps(control(args.db, args.action, args.token)))
    except Exception as error:
        print(json.dumps({'error': str(error)}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
