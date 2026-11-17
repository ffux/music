# Guarded ALAC to AAC fallback

New song downloads prefer highest-bandwidth ALAC, then highest-bandwidth standard
AAC from the source master playlist. Existing files remain untouched. The actual
file metadata supplies the displayed codec, sample rate and lossless bit depth.

The pinned gamdl 3.8.5 adapter requires a successful HTTP response and a valid,
complete master playlist before interpreting absence of an ALAC variant as codec
unavailability. Missing URLs, invalid/incomplete manifests, HTTP/authentication
errors and timeouts fail closed. A selected ALAC stream's media/decryption or
output failure never causes a second AAC download attempt. If the source cannot
reliably establish absence, the job remains an error rather than downgrading.

The adapter is version-gated; an unreviewed gamdl version stops instead of changing
fallback semantics. No blanket retry of failed jobs as AAC is implemented. Format
and decryption warnings that upstream calls skips are surfaced as job errors;
existing-file skips remain successful preservation of existing files.

Validation:

- 24 existing worker/lifecycle/regression checks pass.
- 5 tests exercise the actual gamdl selection implementation: highest ALAC,
  highest AAC with ALAC absent, missing/malformed manifests, HTTP/auth/timeouts,
  and selected-stream I/O/decryption failures.
- A separate hidden preview used a test-only filter to omit ALAC variants from
  a successfully fetched real manifest. It downloaded AAC at 44.1 kHz, reported
  0 errors and fully decoded without errors. This simulates absence; it is not
  evidence that that catalog track naturally lacks lossless.
- Metadata and UI helper checks distinguish `44.1 kHz AAC` from
  `24-bit/44.1 kHz ALAC`. No confirmation prompt is introduced.

Run the selector tests inside the pinned app image, where gamdl is installed:
`python3 -m unittest test_quality_selection` from the app source directory.
