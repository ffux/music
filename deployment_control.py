"""Local-only deploy drain. A persistent owner token blocks new worker claims.

CLI: python3 /app/deployment_control.py [--db PATH] begin|status|end TOKEN
JSON stdout; exit 0 success, 1 conflict/error. No automatic expiry. After a
controller crash, the same owner can inspect/end the drain explicitly.
"""
import argparse
import json
import os
import sqlite3


def init_drain(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS deployment_drain (id INTEGER PRIMARY KEY CHECK(id=1), token TEXT NOT NULL)')


def control(db_path, action, token):
    if not token or len(token)>200:
        raise ValueError('A bounded nonempty owner token is required')
    conn=sqlite3.connect(db_path,timeout=10)
    try:
        conn.execute('BEGIN IMMEDIATE');init_drain(conn)
        row=conn.execute('SELECT token FROM deployment_drain WHERE id=1').fetchone()
        if row and row[0]!=token:raise RuntimeError('Drain is owned by another controller')
        if action=='begin':
            conn.execute('INSERT OR IGNORE INTO deployment_drain(id,token) VALUES(1,?)',(token,))
        elif action=='end':
            bootstrap_table=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='deployment_bootstrap_guard'").fetchone()
            if (conn.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name IN ('music_bootstrap_running_update','music_bootstrap_running_insert')").fetchone()
                    or (bootstrap_table and conn.execute('SELECT 1 FROM deployment_bootstrap_guard').fetchone())):
                raise RuntimeError('Release the owned bootstrap guard with bootstrap_control.py instead')
            if not row:raise RuntimeError('No matching active drain')
            conn.execute('DELETE FROM deployment_drain WHERE id=1 AND token=?',(token,))
        elif action!='status':raise ValueError('Unknown drain action')
        active=action=='begin' or (bool(row) and action!='end')
        running=conn.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]
        pending=conn.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
        conn.commit()
        return {'active':active,'drained':active and running==0,'running':running,'pending':pending}
    finally:conn.close()


def claim_next_job(conn):
    # Shared transaction with begin(): either this claim precedes the drain and
    # is visible as running, or the drain wins and the job remains pending.
    try:
        conn.execute('BEGIN IMMEDIATE');init_drain(conn)
        if conn.execute('SELECT 1 FROM deployment_drain WHERE id=1').fetchone():
            conn.commit();return None
        row=conn.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY created_at,id LIMIT 1").fetchone()
        if row:conn.execute("UPDATE jobs SET status='running',updated_at=CURRENT_TIMESTAMP WHERE id=?",(row['id'],))
        conn.commit();return row
    except BaseException:
        conn.rollback();raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=os.path.join(os.environ.get('DATA_DIR','/data'),'queue.db'))
    parser.add_argument('action',choices=['begin','status','end']);parser.add_argument('token')
    args=parser.parse_args()
    try:print(json.dumps(control(args.db,args.action,args.token)))
    except Exception as error:
        print(json.dumps({'error':str(error)}));raise SystemExit(1)

if __name__=='__main__':main()
