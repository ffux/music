# Isolated ALAC preview result — 17 November 2026

The wrapper's actual `/me` response confirmed authentication and playback
readiness after the operator sign-in. Credentials and session tokens were not
printed or committed.

A single existing library track, Remi Wolf — Guy (Apple track ID 1505470608),
was requested with gamdl 3.8.5 using strict `alac`, wrapper HTTP/TCP endpoints,
no config file, separate temporary/database paths, and no overwrite flag.

Result:

- Downloader exit code: 0.
- Output: `/music/.alac-preview/Remi Wolf/You're A Dog! - EP/04 Guy.m4a`.
- Audio: ALAC, 24-bit, 44,100 Hz, stereo.
- File size: 30,830,118 bytes.
- Audio duration: 162.962948 seconds; existing AAC duration: 163.027302 seconds.
- Full-file FFmpeg decode with `-xerror`: exit 0, no decoding errors.
- Companion-only stop/start: authenticated session restored and playback ready.

No audible listening check has been performed. The preview and generated lyrics
remain in the hidden `.alac-preview` directory, excluded from normal library scans.
The original AAC file was not overwritten. Production music configuration and
storage mounts were not modified; the feature branch remains unmerged.

Before production: choose the output strategy for new ALAC files and existing AAC
upgrades, review the branch, then configure and release the app through vibe-deploy.
