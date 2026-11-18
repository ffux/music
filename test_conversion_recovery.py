import json
import subprocess
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import conversion_recovery as recovery
import worker


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.settled = patch.object(recovery, 'settled_fingerprint', side_effect=recovery.fingerprint)
        self.settled.start(); self.addCleanup(self.settled.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.db = self.root / 'queue.db'
        self.conn = sqlite3.connect(self.db)
        self.conn.execute('CREATE TABLE jobs(id INTEGER PRIMARY KEY,status TEXT,log TEXT,updated_at TEXT)')
        self.conn.execute("INSERT INTO jobs VALUES(1,'running','','')")
        self.conn.commit()
        self.a = self.root / 'a.m4a'; self.a.write_bytes(b'original-a')
        self.b = self.root / 'b.m4a'; self.b.write_bytes(b'original-b')
        self.before = {}
        recovery.prepare_conversion_plan(self.conn, 1, self.root, self.before)

    def tearDown(self):
        self.conn.close(); self.temp.cleanup()

    def run_recovery(self):
        with patch.object(worker, 'DB_PATH', str(self.db)):
            worker.recover_interrupted_jobs()
        return self.conn.execute('SELECT status,log FROM jobs WHERE id=1').fetchone()

    def test_persisted_before_first_conversion_and_reopens(self):
        other = sqlite3.connect(self.db)
        self.assertTrue(recovery.has_conversion_plan(other, 1)); other.close()
        with patch.object(recovery, 'convert', return_value={'status':'converted'}) as convert:
            status, log = self.run_recovery()
        self.assertEqual(status, 'done'); self.assertEqual(convert.call_count, 2)
        self.assertIn('no redownload', log)

    def test_restart_between_files_revalidates_idempotently(self):
        calls = []
        def convert(source, root, floor):
            calls.append(source.name)
            if source == self.b: raise KeyboardInterrupt()
            return {'status':'converted'}
        with patch.object(recovery, 'convert', side_effect=convert):
            with self.assertRaises(KeyboardInterrupt):
                recovery.run_conversion_plan(self.conn, 1, lambda _:None, 0)
        self.assertEqual(self.conn.execute('SELECT status FROM jobs').fetchone()[0], 'running')
        with patch.object(recovery, 'convert', return_value={'status':'unchanged'}) as converter:
            status, _ = self.run_recovery()
        self.assertEqual(status,'done');self.assertEqual(converter.call_count,2)
        self.assertEqual(self.a.read_bytes(),b'original-a')

    def test_changed_source_fails_before_any_conversion(self):
        self.b.write_bytes(b'changed')
        with patch.object(recovery,'convert') as convert:
            status,log=self.run_recovery()
        self.assertEqual(status,'error');convert.assert_not_called();self.assertIn('source changed',log)

    def test_missing_source_fails_before_conversion(self):
        self.b.unlink()
        with patch.object(recovery,'convert') as convert:
            status,_=self.run_recovery()
        self.assertEqual(status,'error');convert.assert_not_called()

    def test_symlink_source_fails_closed(self):
        self.b.unlink();self.b.symlink_to(self.a)
        with patch.object(recovery,'convert') as convert:
            status,_=self.run_recovery()
        self.assertEqual(status,'error');convert.assert_not_called()

    def test_partial_published_output_is_preserved_and_error_retained(self):
        output=self.a.with_suffix('.flac');output.write_bytes(b'unmarked-output')
        with patch.object(recovery,'convert',side_effect=FileExistsError('existing output')):
            status,_=self.run_recovery()
        self.assertEqual(status,'error');self.assertEqual(output.read_bytes(),b'unmarked-output')
        self.assertEqual(self.a.read_bytes(),b'original-a')
        self.assertTrue(recovery.has_conversion_plan(self.conn,1))
        with patch.object(recovery,'convert') as convert:self.run_recovery()
        convert.assert_not_called() # no infinite automatic retry of an error

    def test_download_without_plan_never_auto_retries(self):
        self.conn.execute('DELETE FROM conversion_plans');self.conn.commit()
        with patch.object(recovery,'convert') as convert, patch.object(worker,'run_job') as download:
            status,log=self.run_recovery()
        self.assertEqual(status,'error');convert.assert_not_called();download.assert_not_called()
        self.assertIn('manual retry required',log)

    def test_existing_unchanged_files_not_added_to_plan(self):
        self.conn.execute('DELETE FROM conversion_plans');self.conn.commit()
        recovery.prepare_conversion_plan(self.conn,1,self.root,recovery.snapshot(self.root))
        with patch.object(recovery,'convert') as convert:
            status,_=self.run_recovery()
        self.assertEqual(status,'done');convert.assert_not_called()

    def test_real_conversion_restart_preserves_identity_and_reuses_verified_output(self):
        self.settled.stop()
        root=self.root/'real';root.mkdir();source=root/'tone.m4a'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.05','-c:a','alac',str(source)],check=True)
        identity=recovery.fingerprint(source)
        recovery.prepare_conversion_plan(self.conn,2,root,{})
        recovery.run_conversion_plan(self.conn,2,lambda _:None,0)
        self.assertEqual(recovery.fingerprint(source),identity)
        self.assertTrue(source.with_suffix('.flac').exists())
        logs=[];recovery.run_conversion_plan(self.conn,2,logs.append,0)
        self.assertIn('unchanged',logs[0]);self.assertEqual(recovery.fingerprint(source),identity)

    def test_duplicate_plan_refuses_overwrite(self):
        with self.assertRaises(sqlite3.IntegrityError):
            recovery.prepare_conversion_plan(self.conn,1,self.root,{})

if __name__=='__main__':unittest.main()
