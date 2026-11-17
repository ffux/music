const express = require('express');
const { WebSocketServer } = require('ws');
const Database = require('better-sqlite3');
const archiver = require('archiver');
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFile } = require('child_process');

const DATA_DIR = process.env.DATA_DIR || '/data';
const MUSIC_DIR = process.env.MUSIC_DIR || '/music';
const DB_PATH = path.join(DATA_DIR, 'queue.db');
const metadataCache = new Map();

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

// Read-only, allowlisted status only. Authentication stays on the private SSH flow.
const { createWrapperStatus } = require('./wrapper-status');
const wrapperStatus = createWrapperStatus({
  baseUrl: process.env.MUSIC_WRAPPER_URL || 'http://music-wrapper',
  enabled: ['true', '1'].includes((process.env.MUSIC_USE_WRAPPER || 'true').toLowerCase()),
});
app.get('/api/wrapper/status', async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.json(await wrapperStatus());
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
          result.push({ type: 'file', name: entry.name, path: relPath, size: stat.size, modifiedAt: stat.mtimeMs });
        }
      }
    } catch (e) {}
    return result.sort((a, b) => a.name.localeCompare(b.name));
  }
  res.json(scanDir(MUSIC_DIR));
});

// Extract and cache the embedded artwork from the first M4A in a library item.
app.get('/api/library/artwork', (req, res) => {
  const relativePath = req.query.path;
  if (typeof relativePath !== 'string' || !relativePath) {
    return res.status(400).json({ error: 'Library path required' });
  }

  const libraryRoot = path.resolve(MUSIC_DIR);
  const targetPath = path.resolve(libraryRoot, relativePath);
  if (!targetPath.startsWith(`${libraryRoot}${path.sep}`)) {
    return res.status(400).json({ error: 'Invalid library path' });
  }

  let realRoot;
  let realTarget;
  try {
    realRoot = fs.realpathSync(libraryRoot);
    realTarget = fs.realpathSync(targetPath);
  } catch {
    return res.status(404).json({ error: 'Library item not found' });
  }
  if (realTarget !== realRoot && !realTarget.startsWith(`${realRoot}${path.sep}`)) {
    return res.status(400).json({ error: 'Invalid library path' });
  }

  function findM4a(itemPath) {
    const stat = fs.lstatSync(itemPath);
    if (stat.isSymbolicLink()) return null;
    if (stat.isFile()) return /\.m4a$/i.test(itemPath) ? itemPath : null;
    if (!stat.isDirectory()) return null;
    const entries = fs.readdirSync(itemPath, { withFileTypes: true })
      .filter(entry => !entry.name.startsWith('.'))
      .sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      const match = findM4a(path.join(itemPath, entry.name));
      if (match) return match;
    }
    return null;
  }

  let mediaPath;
  try {
    mediaPath = findM4a(realTarget);
  } catch {
    return res.status(404).json({ error: 'Artwork not found' });
  }
  if (!mediaPath) return res.status(404).json({ error: 'Artwork not found' });

  const stat = fs.statSync(mediaPath);
  const cacheDir = path.join(DATA_DIR, 'artwork-cache');
  const cacheKey = crypto.createHash('sha256')
    .update(`${mediaPath}:${stat.size}:${stat.mtimeMs}`)
    .digest('hex');
  const cachePath = path.join(cacheDir, `${cacheKey}.jpg`);
  if (fs.existsSync(cachePath)) {
    res.setHeader('Cache-Control', 'public, max-age=86400');
    return res.type('image/jpeg').sendFile(cachePath);
  }

  fs.mkdirSync(cacheDir, { recursive: true });
  execFile('ffmpeg', [
    '-v', 'error', '-i', mediaPath, '-map', '0:v:0', '-frames:v', '1',
    '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'
  ], { encoding: null, maxBuffer: 12 * 1024 * 1024 }, (error, stdout) => {
    if (error || !stdout?.length) {
      return res.status(404).json({ error: 'Artwork not found' });
    }
    try { fs.writeFileSync(cachePath, stdout); } catch {}
    res.setHeader('Cache-Control', 'public, max-age=86400');
    res.type('image/jpeg').send(stdout);
  });
});

app.get('/api/library/metadata', (req, res) => {
  const relativePath = req.query.path;
  if (typeof relativePath !== 'string' || !relativePath) {
    return res.status(400).json({ error: 'Library path required' });
  }
  const libraryRoot = path.resolve(MUSIC_DIR);
  const targetPath = path.resolve(libraryRoot, relativePath);
  if (!targetPath.startsWith(`${libraryRoot}${path.sep}`)) {
    return res.status(400).json({ error: 'Invalid library path' });
  }
  let realRoot;
  let realTarget;
  let stat;
  try {
    realRoot = fs.realpathSync(libraryRoot);
    realTarget = fs.realpathSync(targetPath);
    stat = fs.statSync(realTarget);
  } catch {
    return res.status(404).json({ error: 'Library item not found' });
  }
  if (!stat.isDirectory() || (realTarget !== realRoot && !realTarget.startsWith(`${realRoot}${path.sep}`))) {
    return res.status(400).json({ error: 'Invalid library path' });
  }
  const cacheKey = `${realTarget}:${stat.mtimeMs}`;
  if (metadataCache.has(cacheKey)) return res.json(metadataCache.get(cacheKey));

  execFile('python3', [path.join(__dirname, 'metadata.py'), realTarget],
    { maxBuffer: 8 * 1024 * 1024 }, (error, stdout) => {
      if (error) return res.status(500).json({ error: 'Could not read library metadata' });
      try {
        const metadata = JSON.parse(stdout);
        metadataCache.set(cacheKey, metadata);
        res.json(metadata);
      } catch {
        res.status(500).json({ error: 'Could not read library metadata' });
      }
    });
});

// Download a library track directly or stream any library folder as a ZIP.
app.get('/api/library/download', (req, res) => {
  const relativePath = req.query.path;
  if (typeof relativePath !== 'string' || !relativePath) {
    return res.status(400).json({ error: 'Library path required' });
  }

  const libraryRoot = path.resolve(MUSIC_DIR);
  const targetPath = path.resolve(libraryRoot, relativePath);
  if (!targetPath.startsWith(`${libraryRoot}${path.sep}`)) {
    return res.status(400).json({ error: 'Invalid library path' });
  }

  let realRoot;
  let realTarget;
  let stat;
  try {
    realRoot = fs.realpathSync(libraryRoot);
    realTarget = fs.realpathSync(targetPath);
    stat = fs.statSync(realTarget);
  } catch {
    return res.status(404).json({ error: 'Library item not found' });
  }

  if (realTarget !== realRoot && !realTarget.startsWith(`${realRoot}${path.sep}`)) {
    return res.status(400).json({ error: 'Invalid library path' });
  }

  if (stat.isFile()) {
    if (!/\.(m4a|mp3|flac|aac|opus)$/i.test(realTarget)) {
      return res.status(400).json({ error: 'Unsupported file type' });
    }
    return res.download(realTarget, path.basename(realTarget));
  }

  if (!stat.isDirectory()) {
    return res.status(400).json({ error: 'Unsupported library item' });
  }

  const folderName = path.basename(realTarget);
  res.attachment(`${folderName}.zip`);
  res.type('application/zip');

  const archive = archiver('zip', { zlib: { level: 6 } });
  archive.on('error', error => {
    console.error('ZIP download failed:', error);
    if (!res.headersSent) res.status(500).json({ error: 'Could not create ZIP' });
    else res.destroy(error);
  });
  archive.pipe(res);
  archive.directory(realTarget, folderName);
  archive.finalize();
});

// Public catalogue metadata only; saving still uses the explicit queue endpoint.
const catalogueCache = new Map();
async function appleCatalogue(url) {
  const cached = catalogueCache.get(url);
  if (cached && Date.now() - cached.time < 60000) return cached.data;
  const response = await fetch(url, { signal: AbortSignal.timeout(20000) });
  if (!response.ok) throw new Error(`Apple catalogue returned ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data.results)) throw new Error('Invalid Apple catalogue response');
  if (catalogueCache.size >= 200) catalogueCache.delete(catalogueCache.keys().next().value);
  catalogueCache.set(url, { time: Date.now(), data });
  return data;
}

app.get('/api/search', async (req, res) => {
  const q = typeof req.query.q === 'string' ? req.query.q.trim().slice(0, 200) : '';
  const type = req.query.type || 'all';
  const entities = { song: 'song', album: 'album', artist: 'musicArtist' };
  if (!q || !(type === 'all' || entities[type])) return res.status(400).json({ error: 'Search query and valid type required' });
  try {
    const types = type === 'all' ? ['artist','album','song'] : [type];
    const groups = await Promise.all(types.map(async kind => {
      const data = await appleCatalogue(`https://itunes.apple.com/search?term=${encodeURIComponent(q)}&media=music&entity=${entities[kind]}&limit=25&country=us`);
      return data.results.map(item => ({ ...item, resultType: kind }));
    }));
    res.json({ results: groups.flat() });
  } catch {
    res.status(502).json({ error: 'Apple Music search is unavailable; try again' });
  }
});

app.get('/api/catalogue', async (req, res) => {
  const { id, kind } = req.query;
  if (typeof id !== 'string' || !/^\d{1,20}$/.test(id) || !['artist','album','song'].includes(kind)) {
    return res.status(400).json({ error: 'Valid Apple ID and catalogue type required' });
  }
  try {
    const entity = kind === 'artist' ? 'album' : 'song';
    const data = await appleCatalogue(`https://itunes.apple.com/lookup?id=${id}&entity=${entity}&limit=200&country=us`);
    res.json(data);
  } catch {
    res.status(502).json({ error: 'Apple Music catalogue is unavailable; try again' });
  }
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
