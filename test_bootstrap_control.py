import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bootstrap_control as bootstrap
from deployment_control import claim_next_job, control as drain
import worker


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / 'queue.db')
        self.c = sqlite3.connect(self.db)
        self.c.row_factory = sqlite3.Row
        self.c.execute('CREATE TABLE jobs(id INTEGER PRIMARY KEY,status TEXT,log TEXT,created_at TEXT,updated_at TEXT)')
        self.c.execute("INSERT INTO jobs VALUES(1,'pending','','2026-01-01','')")
        self.c.commit()

    def tearDown(self):
        self.c.close(); self.temp.cleanup()

    def test_legacy_run_job_aborts_before_downloader_and_pending_is_kept(self):
        bootstrap.control(self.db, 'begin', 'owner')
        with patch.object(worker, 'DB_PATH', self.db), patch.object(worker.subprocess, 'Popen') as process:
            with self.assertRaises(sqlite3.IntegrityError):
                worker.run_job(1, 'https://example.test/fixture')
        process.assert_not_called()
        self.assertEqual(self.c.execute('SELECT status FROM jobs WHERE id=1').fetchone()[0], 'pending')

    def test_insert_running_rejected_but_pending_accepted(self):
        bootstrap.control(self.db, 'begin', 'owner')
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("INSERT INTO jobs VALUES(2,'running','','','')")
        self.c.rollback()
        self.c.execute("INSERT INTO jobs VALUES(2,'pending','','','')"); self.c.commit()
        self.assertEqual(bootstrap.control(self.db, 'status', 'owner')['pending'], 2)

    def test_new_claim_blocked_then_resumes_after_owned_release(self):
        bootstrap.control(self.db, 'begin', 'owner')
        self.assertIsNone(claim_next_job(self.c))
        bootstrap.control(self.db, 'end', 'owner')
        self.assertEqual(claim_next_job(self.c)['id'], 1)

    def test_active_job_rejects_atomic_install(self):
        self.c.execute("UPDATE jobs SET status='running'"); self.c.commit()
        with self.assertRaises(RuntimeError): bootstrap.control(self.db, 'begin', 'owner')
        self.assertFalse(self.c.execute("SELECT 1 FROM sqlite_master WHERE type='trigger'").fetchone())
        self.assertFalse(drain(self.db, 'status', 'owner')['active'])

    def test_existing_owned_drain_and_idempotence(self):
        drain(self.db, 'begin', 'owner')
        bootstrap.control(self.db, 'begin', 'owner')
        self.assertTrue(bootstrap.control(self.db, 'begin', 'owner')['legacyGuard'])
        for action in ['begin', 'status', 'end']:
            with self.assertRaises(RuntimeError): bootstrap.control(self.db, action, 'foreign')
        with self.assertRaises(RuntimeError): drain(self.db, 'end', 'owner')
        self.assertTrue(bootstrap.control(self.db, 'status', 'owner')['active'])

    def test_foreign_drain_rejected_without_triggers(self):
        drain(self.db, 'begin', 'foreign')
        with self.assertRaises(RuntimeError): bootstrap.control(self.db, 'begin', 'owner')
        self.assertFalse(self.c.execute("SELECT 1 FROM sqlite_master WHERE type='trigger'").fetchone())

    def test_unowned_trigger_even_exact_definition_is_untouched(self):
        sql = next(iter(bootstrap.TRIGGERS.values()))
        self.c.execute(sql); self.c.commit()
        for action in ['begin', 'status', 'end']:
            with self.assertRaises(RuntimeError): bootstrap.control(self.db, action, 'owner')
        self.assertEqual(self.c.execute("SELECT sql FROM sqlite_master WHERE type='trigger'").fetchone()[0], sql)

    def test_partial_or_modified_guard_rejects_release(self):
        bootstrap.control(self.db, 'begin', 'owner')
        self.c.execute('DROP TRIGGER music_bootstrap_running_insert'); self.c.commit()
        for action in ['begin', 'status', 'end']:
            with self.assertRaises(RuntimeError): bootstrap.control(self.db, action, 'owner')
        self.assertIsNotNone(self.c.execute('SELECT token FROM deployment_drain').fetchone())
        self.assertIsNotNone(self.c.execute("SELECT 1 FROM sqlite_master WHERE name='music_bootstrap_running_update'").fetchone())

    def test_restart_and_legacy_rollback_keep_guard_durable(self):
        bootstrap.control(self.db, 'begin', 'owner')
        self.c.close(); self.c = sqlite3.connect(self.db); self.c.row_factory = sqlite3.Row
        self.assertTrue(bootstrap.control(self.db, 'status', 'owner')['drained'])
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute("UPDATE jobs SET status='running' WHERE id=1")
        self.c.rollback()
        bootstrap.control(self.db, 'end', 'owner')
        self.c.execute("UPDATE jobs SET status='running' WHERE id=1"); self.c.commit()

    def test_absent_end_rejected(self):
        self.assertFalse(bootstrap.control(self.db, 'status', 'owner')['active'])
        with self.assertRaises(RuntimeError): bootstrap.control(self.db, 'end', 'owner')

if __name__ == '__main__': unittest.main()
