const express = require('express');
const { WebSocketServer } = require('ws');
const Database = require('better-sqlite3');
const multer = require('multer');
const http = require('http');
const fs = require('fs');
const path = require('path');

const DATA_DIR = process.env.DATA_DIR || '/data';
const MUSIC_DIR = process.env.MUSIC_DIR || '/music';
const DB_PATH = path.join(DATA_DIR, 'queue.db');

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

// Init DB - retry until /data is available
let db;
function initDb() {
  try {
    db = new Database(DB_PATH);
    db.exec(`
      CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        title TEXT,
        log TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);
    console.log('Database ready at', DB_PATH);
  } catch (e) {
    console.error('DB init failed, retrying in 2s:', e.message);
    setTimeout(initDb, 2000);
  }
}
initDb();

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Stream music files for playback
app.use('/files', (req, res, next) => {
  res.setHeader('Accept-Ranges', 'bytes');
  next();
}, express.static(MUSIC_DIR));

// Upload cookies.txt
const upload = multer({ dest: '/tmp/' });
app.post('/api/cookies', upload.single('cookies'), (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
  const dest = path.join(DATA_DIR, 'cookies.txt');
  fs.copyFileSync(req.file.path, dest);
  fs.unlinkSync(req.file.path);
  res.json({ ok: true, message: 'cookies.txt updated' });
});

app.get('/api/cookies/status', (req, res) => {
  const cookiePath = path.join(DATA_DIR, 'cookies.txt');
  const exists = fs.existsSync(cookiePath);
  let mtime = null;
  if (exists) mtime = fs.statSync(cookiePath).mtime;
  res.json({ exists, mtime });
});

// Queue a download
app.post('/api/queue', (req, res) => {
  if (!db) return res.status(503).json({ error: 'Database not ready' });
  const { url } = req.body;
  if (!url || !url.includes('music.apple.com')) {
    return res.status(400).json({ error: 'Valid Apple Music URL required' });
  }
  const result = db.prepare('INSERT INTO jobs (url) VALUES (?)').run(url);
  broadcast({ type: 'job_added', id: result.lastInsertRowid, url });
  res.json({ id: result.lastInsertRowid });
});

// List all jobs
app.get('/api/jobs', (req, res) => {
  if (!db) return res.status(503).json({ error: 'Database not ready' });
  const jobs = db.prepare('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 200').all();
  res.json(jobs);
});

// Delete a job
app.delete('/api/jobs/:id', (req, res) => {
  if (!db) return res.status(503).json({ error: 'Database not ready' });
  db.prepare('DELETE FROM jobs WHERE id = ?').run(req.params.id);
  res.json({ ok: true });
});

// Library - recursive scan of music dir
app.get('/api/library', (req, res) => {
  function scanDir(dir, base = '') {
    const result = [];
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.name.startsWith('.')) continue;
        const relPath = base ? `${base}/${entry.name}` : entry.name;
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          const children = scanDir(fullPath, relPath);
          if (children.length > 0) {
            result.push({ type: 'dir', name: entry.name, path: relPath, children });
          }
        } else if (/\.(m4a|mp3|flac|aac|opus)$/i.test(entry.name)) {
          const stat = fs.statSync(fullPath);
          result.push({ type: 'file', name: entry.name, path: relPath, size: stat.size });
        }
      }
    } catch (e) {}
    return result.sort((a, b) => a.name.localeCompare(b.name));
  }
  res.json(scanDir(MUSIC_DIR));
});

// WebSocket broadcast
const clients = new Set();
wss.on('connection', ws => {
  clients.add(ws);
  // Send current jobs on connect
  if (db) {
    const jobs = db.prepare('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 200').all();
    ws.send(JSON.stringify({ type: 'init', jobs }));
  }
  ws.on('close', () => clients.delete(ws));
});

function broadcast(data) {
  const msg = JSON.stringify(data);
  for (const ws of clients) {
    if (ws.readyState === 1) ws.send(msg);
  }
}

// Poll DB for job updates and push to clients
let lastPoll = Math.floor(Date.now() / 1000) - 1;
setInterval(() => {
  if (!db) return;
  const updated = db.prepare(
    "SELECT * FROM jobs WHERE strftime('%s', updated_at) >= ?"
  ).all(String(lastPoll));
  if (updated.length) {
    broadcast({ type: 'jobs_update', jobs: updated });
  }
  lastPoll = Math.floor(Date.now() / 1000);
}, 1000);

server.listen(3000, () => console.log('Music app running on port 3000'));
