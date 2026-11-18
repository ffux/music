import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import worker


class WorkerFlacTests(unittest.TestCase):
    def run_case(self, returncode=0, enabled='true', conversion_error=False):
        with tempfile.TemporaryDirectory() as root:
            db_path = os.path.join(root, 'queue.db')
            conn = sqlite3.connect(db_path)
            conn.execute('CREATE TABLE jobs(id INTEGER PRIMARY KEY, status TEXT, log TEXT, updated_at TEXT)')
            conn.execute("INSERT INTO jobs VALUES(1,'pending','','')"); conn.commit(); conn.close()
            process = SimpleNamespace(returncode=returncode, wait=lambda: None)
            settings = dict(codec='alac', output=root, use_wrapper=False)
            with patch.object(worker, 'DB_PATH', db_path), patch.object(worker, 'downloader_settings', return_value=settings), \
                 patch.object(worker, 'check_wrapper_ready'), patch.object(worker, 'build_command', return_value=['fixture-downloader']), \
                 patch.object(worker.subprocess, 'Popen', return_value=process), patch.object(worker, 'stream_process'), \
                 patch.object(worker, 'run_conversion_plan') as convert, patch.dict(os.environ, {'MUSIC_CONVERT_ALAC_TO_FLAC': enabled}):
                if conversion_error: convert.side_effect = RuntimeError('fixture verification failed')
                worker.run_job(1, 'https://example.test/fixture')
                calls = convert.call_count
            conn = sqlite3.connect(db_path)
            result = conn.execute('SELECT status,log FROM jobs').fetchone(); conn.close()
            return calls, result

    def test_success_converts_before_done(self):
        calls, (status, log) = self.run_case()
        self.assertEqual(calls, 1); self.assertEqual(status, 'done')
        self.assertIn('originals are retained', log)

    def test_download_error_does_not_convert_partial_files(self):
        calls, (status, _) = self.run_case(returncode=1)
        self.assertEqual(calls, 0); self.assertEqual(status, 'error')

    def test_conversion_error_is_not_reported_done(self):
        calls, (status, log) = self.run_case(conversion_error=True)
        self.assertEqual(calls, 1); self.assertEqual(status, 'error')
        self.assertIn('fixture verification failed', log)

    def test_opt_out(self):
        calls, (status, _) = self.run_case(enabled='false')
        self.assertEqual(calls, 0); self.assertEqual(status, 'done')


if __name__ == '__main__': unittest.main()
