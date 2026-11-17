# Confirmed server deletion

## Existing access boundary, verified 2026-11-17

A fresh browser request to https://music.zzxx.ooo/ redirects to Cloudflare Access's email sign-in. The redirect identifies the existing team issuer `https://throbbing-flower-2b15.cloudflareaccess.com` and application audience `cfbd88aae2c8294da5f09d2786be737096706b14fdc114c124a3463ede2c0549`. Public signing keys are reachable from the app runtime. Existing Cloudflare API credentials cannot read Access/tunnel configuration (HTTP 403), but this no longer blocks verification because the trusted browser redirect supplied the public identifiers.

The music container has no published ports. Caddy binds only VM loopback ports 80/443. Probes from the Mac to VM LAN ports 80/443/3000 fail. Requests from the trusted VM itself to Caddy loopback or the music Docker IP return HTTP 200 without Access. Public edge authentication and internal-origin trust are therefore distinct. No network, Cloudflare policy, SSH access, credentials or login requirements were changed.

Deletion verifies the existing `Cf-Access-Jwt-Assertion` using jose, pinned issuer/audience, RS256, public-key rotation, expiry/subject/issued-at and an authenticated app/email session. It introduces no second sign-in. Merely supplying an email header or reaching the origin is insufficient. Default app identifiers can be overridden by server configuration if the Access application is deliberately recreated.

## Per-operation protections

Both preview and delete require the canonical same Origin, same-origin Fetch Metadata, JSON and a custom action header. This protects against cross-site requests independently of Access cookies. Preview creates a random, two-minute, one-use token bound to the authenticated subject, exact path, kind and metadata fingerprint. The browser always shows native explicit confirmation with item name, path, scope, song/file counts, permanent-deletion warning and device-copy clarification. There is no remember/disable option. Changing the library requires a new review.

Python operates under held directory descriptors with `O_NOFOLLOW`. It rejects root/traversal/hidden path components, backslashes, symlinks, special files, invalid scope/depth, and filesystem-boundary changes. Artist deletion is one top-level artist folder; album deletion is exactly one artist/album folder; song deletion is one supported audio file beneath an album. Album/artist scopes include associated ordinary files such as artwork, disclosed in confirmation. Descendant identities are rechecked before removal. New or replaced entries are refused; replacement symlinks are never followed.

Operations are blocked while download jobs are pending/running. Only one deletion runs at a time; new queue submissions are blocked during it. Confirmation tokens are consumed once even on conflict. Interrupted/partial operations produce an error and require library refresh/review. Successful or partial deletion invalidates metadata, broadcasts the scope and removes affected queue entries. A deleted current track stops without autoplaying another song; unrelated playback remains intact.

## Validation

- JWT tests: valid signature/session, missing/forged/expired/future/wrong-issuer/wrong-audience/wrong-type tokens; signing-key endpoint reachable without account secrets.
- Nine filesystem tests use disposable trees only: single song, album and artist scope; sibling/outside preservation; traversal/root/type/extension refusal; target/ancestor/descendant symlinks; changed collection/file fingerprints; disc subfolders.
- HTTP route tests use a container with **no music mounts**: auth and CSRF refusal, fresh explicit confirmation, identity binding, replay/expiry, injected path ignored, active-download/concurrent-operation locks and changed-file refusal.
- Frontend tests: every attempt confirms, Cancel sends no final delete request, deletion stops only affected playback and prunes queue scope safely.
- Mobile browser fixture: actual album More menu, named permanent-deletion warning, Cancel leaves the fixture visible and unchanged. No browser-confirmed deletion of real files was performed.
- Existing search/navigation/mobile/portrait tests and 29 download/wrapper tests pass.

Live release checks intentionally exercise only invalid/missing-auth rejection and served source. A real authenticated deletion of music is left to the user's own explicit confirmation; it is not used as a production test.
