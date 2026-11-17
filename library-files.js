// A source is hidden only when a verified conversion marker still matches both
// regular files. Stale/partial conversions fall back to displaying the original.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
function isConvertedSource(directory, name) {
  if (!/\.m4a$/i.test(name) || path.basename(name) !== name) return false;
  try {
    const markerPath = path.join(directory, `.${name}.flac.json`);
    const markerStat = fs.lstatSync(markerPath);
    if (!markerStat.isFile() || markerStat.size > 16384) return false;
    const marker = JSON.parse(fs.readFileSync(markerPath, 'utf8'));
    const outputName = name.slice(0, -4) + '.flac';
    if (marker.version !== 1 || marker.source?.name !== name || marker.output?.name !== outputName) return false;
    return [marker.source, marker.output].every(item => {
      const stat = fs.lstatSync(path.join(directory, item.name));
      return stat.isFile() && Number.isFinite(item.size) && item.size === stat.size
        && Number.isFinite(item.mtimeMs) && Math.abs(item.mtimeMs - stat.mtimeMs) < 0.01
        && /^[a-f0-9]{64}$/.test(item.sha256);
    });
  } catch { return false; }
}
function visibleEntries(directory) {
  return fs.readdirSync(directory, {withFileTypes: true}).filter(entry =>
    !entry.name.startsWith('.') && !entry.isSymbolicLink()
      && !isConvertedSource(directory, entry.name));
}
// Only add checked regular files; never include recovery originals or symlinks.
function appendLibraryDirectory(archive, directory, archivePath) {
  for (const entry of visibleEntries(directory)) {
    const fullPath = path.join(directory, entry.name);
    const memberPath = `${archivePath}/${entry.name}`;
    if (entry.isDirectory()) appendLibraryDirectory(archive, fullPath, memberPath);
    else if (entry.isFile()) archive.file(fullPath, {name: memberPath});
  }
}
function libraryFingerprint(directory) {
  const hash = crypto.createHash('sha256');
  let count = 0;
  function visit(dir, prefix = '', depth = 0) {
    if (depth > 32) throw new Error('Library metadata is too deeply nested');
    for (const entry of visibleEntries(dir).sort((a, b) => a.name.localeCompare(b.name))) {
      if (++count > 100000) throw new Error('Library metadata has too many files');
      const full = path.join(dir, entry.name), rel = prefix + entry.name;
      if (entry.isDirectory()) visit(full, rel + '/', depth + 1);
      else if (entry.isFile()) {
        const st = fs.statSync(full);
        hash.update(JSON.stringify([rel, st.size, st.mtimeMs]));
      }
    }
  }
  visit(directory);
  return hash.digest('hex');
}
module.exports = {isConvertedSource, visibleEntries, appendLibraryDirectory, libraryFingerprint};
