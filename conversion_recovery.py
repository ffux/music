"""Durable, job-scoped conversion intent. Never infers download success on restart."""
import json
from pathlib import Path
from flac_conversion import snapshot, checked_source, fingerprint, settled_fingerprint, convert


def init_plans(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS conversion_plans (job_id INTEGER PRIMARY KEY, plan TEXT NOT NULL)')
    conn.commit()


def prepare_conversion_plan(conn, job_id, root, before):
    # Only call after the downloader successfully completed. Persist every exact
    # source identity before the first output is written.
    root = Path(root).resolve(strict=True)
    entries = []
    for source, identity in snapshot(root).items():
        if before.get(source) != identity:
            path = checked_source(source, root)
            entries.append({'source': str(path), 'identity': settled_fingerprint(path)})
    plan = {'version': 1, 'root': str(root), 'entries': entries}
    init_plans(conn)
    conn.execute('INSERT INTO conversion_plans(job_id,plan) VALUES(?,?)', (job_id, json.dumps(plan)))
    conn.commit()


def has_conversion_plan(conn, job_id):
    return conn.execute('SELECT 1 FROM conversion_plans WHERE job_id=?', (job_id,)).fetchone() is not None


def run_conversion_plan(conn, job_id, log, min_free_bytes):
    row = conn.execute('SELECT plan FROM conversion_plans WHERE job_id=?', (job_id,)).fetchone()
    if not row:
        raise ValueError('No durable conversion plan')
    plan = json.loads(row[0])
    if plan.get('version') != 1 or not isinstance(plan.get('entries'), list):
        raise ValueError('Invalid conversion plan')
    root = Path(plan['root']).resolve(strict=True)
    # Validate the complete batch first, including previously completed sources.
    # A missing/changed original or unsafe path halts recovery, never a redownload.
    for entry in plan['entries']:
        source = checked_source(entry['source'], root)
        if fingerprint(source) != entry['identity']:
            raise RuntimeError('Conversion source changed; manual review required: ' + str(source))
    for entry in plan['entries']:
        source = checked_source(entry['source'], root)
        if fingerprint(source) != entry['identity']:
            raise RuntimeError('Conversion source changed during recovery')
        # Existing verified marker pairs are idempotent; unmarked/partial final
        # outputs are deliberately retained and rejected by convert(). Hidden
        # abandoned temporary files are not touched.
        result = convert(source, root, min_free_bytes)
        entry['result'] = result
        conn.execute('UPDATE conversion_plans SET plan=? WHERE job_id=?', (json.dumps(plan), job_id))
        conn.commit()
        log('FLAC: ' + json.dumps(result))
