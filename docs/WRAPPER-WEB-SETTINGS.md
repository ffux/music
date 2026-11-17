# Wrapper connection settings

Settings replaces cookie import with a read-only readiness indicator and a secure Terminal handoff. It does not provide a browser password form or proxy `/login`, `/login/2fa`, or `/me`.

The current app relies on Cloudflare Access at its existing ingress; it does not validate an individual operator identity inside Express. Bridging passwords through that app would add a credential-handling surface and require separately reviewed authorization, request-origin/CSRF protection, login rate limits, 2FA ownership and secret-handling controls. This release avoids that new access entirely. Existing SSH authentication remains the authorization boundary for reauthentication. No new ports, session permissions or Cloudflare policy changes are required.

`GET /api/wrapper/status` calls the fixed server-configured wrapper `/me`, with a five-second timeout, redirects refused and a five-second cache/request deduplication. The browser receives only an allowlisted state; account identity, token values, raw responses and exception messages are never returned or logged. Responses are marked `no-store`. Network/runtime errors are distinguished from sign-in required. This is a readiness check, not a guarantee that the next catalogue/download request will succeed or that a subscription remains valid.

The existing interactive `wrapper/login.py` command accepts hidden inputs in Terminal over existing SSH access. It exits without changing an authenticated session. The web UI never runs that command, changes credentials, revokes a session or submits credentials. On a phone, an already configured SSH client or a computer is needed. A future fully in-browser flow remains separate security work.

The old cookie upload/status routes and controls are removed. Existing cookie files are preserved, as are music files, wrapper session storage and download configuration.

Validation: mock all auth/runtime/error states; sentinel secret filtering; disabled/invalid URL handling; request deduplication; existing JS UX/navigation suites; isolated preview with the actual read-only wrapper status. No login/logout or credential submission was performed.
