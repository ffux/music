# Mobile UI reference update

Reviewed all seven supplied screenshots: 1000021319.jpg, 1000021321.jpg, 1000021323.jpg, 1000021325.jpg, 1000021327.jpg, 1000021329.jpg, 1000021331.jpg. The screenshots remain in the user's Library and are not shipped with the app.

Mobile uses a black background, blue selection accent, floating bottom navigation, artist rows with circular portraits, artwork-led centered album and artist headers, pill controls, and search result rows. Existing destinations are retained rather than adding inactive Home/New/Radio views. Library search remains a dedicated screen with explicit Apple search; favourites/profiles/playlists remain out of scope.

The compact mobile player expands to an accessible Now Playing surface with original artwork, actual file quality, progress, transport, shuffle/repeat, More and Up Next. It observes and controls the same existing audio element and queue. No codecs, transcoding, download quality or storage behavior changed. Up Next includes artwork and remains separate from download history.

Device downloads move into More for local artists, albums, tracks, catalogue matches and current playback. Server-save buttons remain visible for missing or incomplete catalogue items. Partial collection device ZIP labels explicitly say downloaded songs only. Existing device download confirmation behavior is preserved.

Artist search lacked portraits because the iTunes search response does not provide them. A separate lazy endpoint accepts numeric Apple artist IDs only, reads Apple's public musician-page metadata and accepts only HTTPS mzstatic AMCArtistImages portraits. Album and foreign images are rejected. Requests are cached, deduplicated and limited to four concurrently. Missing artwork shows a neutral placeholder. Real Remi Wolf and Samuel Organ portraits verified visually.

Validation: JavaScript syntax/navigation/search/queue tests; primary-save/menu-download routing tests; mocked image identity/error/cache/concurrency tests; 29 existing Python download/wrapper tests; desktop and 390x844 / 360x800 browser checks against the supplied references; AAC playback, pause, expanded presentation, queue continuation and Escape behavior. No real library deletion or test download was performed.

## Delete from server remains blocked

No file-delete route or control is introduced. Express currently has no in-app authenticated principal verification; it relies on the outer Cloudflare gate. The Access team issuer and app audience were not found in repository/deployment configuration. Unauthenticated external probes returned HTTP 403 without usable Access application identifiers. Permanent deletion must not be exposed based only on assumed edge protection or an unverified request header.

Before enabling deletion, establish and verify the Access JWT issuer/audience (or an equivalent authenticated operator boundary). Then implement explicit confirmation on every operation, short-lived scope-bound confirmation tokens, path/descendant/symlink protections, active-download conflict handling, and playback/library cleanup. Test exclusively on disposable fixtures. These controls have not yet been implemented or tested; existing files remain untouched.
