# Verified FLAC storage and browser playback

## Scope

New successful download jobs convert **new or changed local ALAC M4A files** to
native `.flac` files before the job is marked done. The source quality-selection
policy is unchanged. AAC fallback files remain AAC; they are never labeled or
converted as lossless. Set `MUSIC_CONVERT_ALAC_TO_FLAC=false` to disable conversion.

This first implementation converts at the end of a successful **job**, not after
each song in a multi-track job. It does not implement streaming, progressive
playback or prefetching. Failed downloader jobs are not converted automatically.
Previously existing files that the downloader skips require the migration command.

## Safety and storage

- Original M4A files are retained in place, byte-for-byte unchanged.
- Supports 16/24-bit ALAC, preserving sample rate and channel count.
- Temporary output is hidden. FFmpeg must decode it successfully, decoded PCM
  SHA-256 must equal the source, and format properties must match before publish.
- Common tags (including lyrics, sorting, track/disc totals, Apple IDs), compatible
  free-form text tags and all embedded covers are copied and read back. Unmapped
  proprietary MP4 atoms remain available in the retained original.
- The converter reserves approximately uncompressed PCM size plus source size and
  overhead, above the configured `MIN_FREE_BYTES` floor. Conversion subprocesses
  have bounded timeouts. It never overwrites an existing output or source.
- A hidden verification marker records both file hashes, sizes and mtimes. The
  library prefers FLAC only while this marker still matches both file identities;
  it avoids duplicate tracks and excludes retained originals from album ZIPs.
- A repeat migration skips unchanged, hash-verified pairs. A stale marker or
  colliding FLAC requires review rather than overwrite. A crash between publishing
  FLAC and publishing the marker may leave both visible; this is intentionally
  recoverable rather than destructive. No automatic cleanup of originals exists.
- Deleting just a FLAC keeps its original, which reappears in the library. The song
  deletion confirmation warns about this. Confirmed album/artist deletion still
  removes the whole selected folder, including originals and markers, and previews
  its actual file count. No deletion semantics have been expanded silently.
- Keeping both formats roughly doubles audio storage. A retained same-drive copy
  is not an independent backup.

## Existing library migration

Do not run migration while downloads, file edits or deletions are taking place.
Pause the worker and avoid library deletion UI before applying. The dry run only
reads candidates and probes codecs; it does not start any downloads.

```sh
python3 flac_conversion.py /music                  # dry run only
python3 flac_conversion.py /music --apply          # after reviewing and pausing writers
```

Prefer a separate small fixture/sample directory first. The command emits JSON
per file and a nonzero exit status if any conversion needs attention. Use the
same `--min-free-bytes` value as the worker's reserve if overriding the 1 GiB
migration default. Do not delete source files automatically after migration.

## Validation and deployment

Local tests use generated synthetic audio only, not the real music library.
Run the Python suite with requirements installed, and JS tests with Node 20
(the Dockerfile runtime):

```sh
python3 -m unittest discover -v
for test in test_*.js; do node "$test" || exit; done
node --check server.js
git diff --check
```

Tests cover 16/24-bit PCM equality, artwork/tags/IDs, AAC skip, collisions, failed
verification cleanup, disk floor, symlinks, unchanged originals, retry, dry run,
worker failure states, marker-based listing/ZIP filtering and FLAC metadata.

Live Edge/Firefox playback, seeking and download timing on VM 105 must be tested
before rollout. Do not treat cloud-fixture CPU timings as live server timings.
Main branch pushes auto-deploy; use a feature branch until deployment access and
VM build disk space are verified. No real library migration has been run.

Local validation on the implementation checkout: 51 Python tests and all seven
JavaScript test scripts passed under Node 20. A running local server with a
synthetic converted track passed library single-entry visibility, Apple song ID
metadata, JPEG artwork extraction, HTTP 206 byte-range serving and FLAC-only ZIP
download. Syntax and whitespace checks passed. Actual browser decoder testing
and VM timing remain outstanding.

## Server and desktop verification, 18 November 2026

- Server tests passed using an isolated checkout inside the existing Node 20 app
  container, without changing application code or library files.
- A copied real 198.659-second ALAC track (24-bit/96 kHz, stereo) converted and
  completed PCM/tag verification in **8.102 seconds** on the server. ALAC was
  78,581,435 bytes; FLAC was 78,052,458 bytes. This is one high-resolution sample,
  not a download-time benchmark or a guarantee for every track.
- The real file exposed scalar MP4 compilation tags; normalization now supports
  scalar booleans and the regression fixture explicitly checks this field.
- Firefox 158 and Chrome 157 on the Mac both decoded the converted sample and
  continued playback beyond a seek to 60 seconds with no media error. Tests were
  muted and served locally. Chrome seeking requires HTTP byte ranges, which the
  app already supports; a plain non-range test server was replaced before the
  successful seek test.
- Edge is not installed on the connected Mac, so Edge-specific testing remains
  unverified. Local tests do not prove authenticated remote mobile playback.
