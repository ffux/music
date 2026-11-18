import sqlite3,tempfile,unittest
from pathlib import Path
from deployment_control import control,claim_next_job

class DrainTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=str(Path(self.temp.name)/'queue.db');self.c=sqlite3.connect(self.db);self.c.row_factory=sqlite3.Row
  self.c.execute('CREATE TABLE jobs(id INTEGER PRIMARY KEY,status TEXT,created_at TEXT,updated_at TEXT)');self.c.execute("INSERT INTO jobs VALUES(1,'pending','2026-01-01','')");self.c.commit()
 def tearDown(self):self.c.close();self.temp.cleanup()
 def test_drain_before_claim_blocks_pending_across_connections(self):
  self.assertTrue(control(self.db,'begin','owner')['drained']);self.assertIsNone(claim_next_job(self.c));self.assertEqual(control(self.db,'status','owner')['pending'],1)
  other=sqlite3.connect(self.db);other.row_factory=sqlite3.Row;self.assertIsNone(claim_next_job(other));other.close()
  control(self.db,'end','owner');self.assertEqual(claim_next_job(self.c)['id'],1)
 def test_claim_before_drain_waits_running(self):
  self.assertEqual(claim_next_job(self.c)['id'],1);self.assertFalse(control(self.db,'begin','owner')['drained'])
  self.c.execute("UPDATE jobs SET status='done'");self.c.commit();self.assertTrue(control(self.db,'status','owner')['drained'])
 def test_owner_idempotence_and_conflict(self):
  control(self.db,'begin','a');self.assertTrue(control(self.db,'begin','a')['active'])
  for action in ['begin','status','end']:
   with self.assertRaises(RuntimeError):control(self.db,action,'b')
  self.assertTrue(control(self.db,'status','a')['active']);self.assertFalse(control(self.db,'end','a')['active'])
 def test_missing_drain_is_not_drained(self):
  self.assertFalse(control(self.db,'status','owner')['drained'])
  with self.assertRaises(RuntimeError):control(self.db,'end','owner')
if __name__=='__main__':unittest.main()
