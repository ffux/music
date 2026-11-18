# Persistent artist portraits

Library artist cards request `/api/library/artist-artwork?path=<artist-folder>`
without waiting for the full album metadata index. On first use, a lightweight
Mutagen tag reader identifies a consistent Apple artist ID without ffprobe.
Mixed/unknown identities and compilation folders retain a neutral placeholder.
Only Apple's explicit artist portraits are accepted, never album covers.

Genuine artist parent folders store `.artist.jpg` and `.artist.json`. Hidden
files stay out of audio listings, album/artist ZIPs and metadata fingerprints.
The JSON identifies app-managed images by owner and SHA-256, and records the
artist ID and refresh/retry timestamps. Existing user artwork is not overwritten.
Catalogue artists without a downloaded folder use a separate persistent cache
under the application's data volume, keyed by Apple artist ID.

A saved portrait is served immediately from disk, including after a deployment.
When requested after seven days, it is refreshed in the background. This is
weekly freshness-on-access, not an unconditional weekly crawler. Failed refreshes
keep the previous image and back off before retrying. A cold cache may wait for
its first Apple lookup; initial rollout can warm downloaded artists proactively.
Image refreshes are bounded, deduplicated and validated. Publication is atomic;
symlinks, traversal and deleted/replaced artist directories are rejected.

Tests cover independent artist rendering, persistent cache reuse, stale refresh,
network/image failures, compilations/identity, unowned files, path safety and
concurrent requests. Run all Python and `test_*.js` suites before deployment.
