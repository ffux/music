# ALAC wrapper implementation — feature branch, not activated

The app remains built and deployed by vibe-deploy on a push to `main`. This
branch must not be merged or deployed until the wrapper integration is approved
and tested. The companion Compose file does not run or replace the music app.

## What is implemented

The worker explicitly selects `aac-web` with no wrapper by default. It ignores
container-local gamdl config so behavior cannot drift between builds. Optional
`MUSIC_*` settings in `wrapper/music.env.example` enable strict `alac`, private
HTTP/TCP endpoints, and a hidden preview output directory. `alac,aac-web` is an
explicit opt-in fallback; strict `alac` is the proposed setting.

Before a wrapper job starts, `/me` must report `runtime.playback_ready=true` and
`auth.state=authenticated`. An unavailable, unready, or signed-out wrapper fails
the job with an actionable message. The account response is never logged. The
worker does not prompt for credentials; subprocess stdin is closed. Settings
errors enter the normal job error flow. Existing overwrite behavior stays off.

The separate wrapper service uses a persistent named session volume and joins
`vibe-deploy_web`, where vibe-deploy's music container can resolve
`music-wrapper`. Only operator HTTP port 18080 is published, on host loopback.
There is no public hostname or Caddy route. TCP decrypt is only on the Docker
network. Other apps sharing that network can reach the wrapper: a future move
to a dedicated network requires vibe-deploy support for music's extra network.
The upstream native/chroot runtime requires elevated container capabilities;
review those before activation. No host music path is mounted into the wrapper.

## Remaining prerequisites

1. Supply a legally obtained compatible Apple Music APK/APKM and stage the
   matching native libraries using upstream's hash checks. Do not commit Apple
   binaries, account data, cookies, passwords, or session files.
2. Use reviewed wrapper-v2 source revision
   `100e0a864e883e03a3ac450a780dd9563fff5271`. `wrapper/build.sh` checks HEAD before
   building; it does not start a service. The example target is the existing
   x86_64 VM. Build/runtime compatibility still needs verification.
3. After review, start the companion service from a durable source directory
   outside webhook-managed `deployments/`. Use `wrapper/compose.yaml` with
   `WRAPPER_SOURCE_DIR` pointing at the prepared upstream checkout. Keep the
   Compose project name stable so its session volume is preserved.
4. Complete Apple Music sign-in and 2FA privately through an SSH tunnel to the
   loopback HTTP port, following upstream's login flow. Do not add account
   credentials to environment examples, source, chat logs, or job logs.
5. Configure vibe-deploy's untracked `deployments/music/.env` with the reviewed
   `MUSIC_*` values. vibe-deploy passes that file to staging and production.
   Leave the existing `volumes.txt` and `/data/music` mounts unchanged.
6. Merge/deploy through GitHub only after approval. Test one track into
   `/music/.alac-preview`, verify codec/bit depth/sample rate and full playback,
   then plan how future ALAC files should enter the visible library.

## Validation and rollback

Run `python3 -m unittest test_worker test_wrapper`. Validate Compose without
starting it: `WRAPPER_SOURCE_DIR=/path/to/checkout docker compose -f
wrapper/compose.yaml config --quiet`.

End-to-end sign-in/download tests require the staged libraries and an active
subscription. This branch has not built or started the wrapper, authenticated an
account, downloaded music, changed production settings, or touched library data.
Disabling wrapper mode and restoring `aac-web` returns future jobs to the current
format; existing files and the wrapper session volume can remain untouched.

## Sources

- https://github.com/glomatico/gamdl/blob/3.x/README.md
- https://github.com/glomatico/wrapper-v2/tree/100e0a864e883e03a3ac450a780dd9563fff5271

## Independent release lifecycle

Configuration stays in this repository; the containers have separate lifecycles.
A push to music's `main` builds only the root Dockerfile. Neither that Dockerfile,
the app startup nor the webhook calls `wrapper/manage.py`. A normal UI release
therefore cannot build or restart the companion.

Use a durable checkout outside `deployments/`, with an explicitly reviewed
music commit checked out. Export `WRAPPER_SOURCE_DIR` pointing at the prepared,
pinned upstream source. These commands are operator actions, not webhook hooks:

```sh
python3 wrapper/manage.py build     # build only, no startup
python3 wrapper/manage.py apply     # explicit companion rollout
python3 wrapper/manage.py status    # service status + HTTP liveness
python3 wrapper/manage.py rollback  # restore preceding image/config snapshot
python3 wrapper/manage.py stop      # keep session data and release history
```

The fixed Compose project is `music-wrapper`; its session volume has the explicit
name `music-wrapper-session`. Both survive app rebuilds and source checkout moves.
Do not run `compose down -v` or prune that volume. Before upgrading an authenticated
wrapper, stop it and back up the session volume privately. Image rollback does not
undo a change to the session database format; preserve the pre-upgrade backup.

`apply` requires an already-built local image and committed wrapper configuration.
It snapshots Compose and the exact image ID beneath `/var/lib/music-wrapper/releases`,
then starts only `music-wrapper` with builds and pulls disabled. It waits for HTTP
liveness before recording the current release. An unsuccessful update restores the
previous recorded release; an unsuccessful first start stops the candidate. Retain
old images locally for rollback; the app's image cleanup does not target them.

Liveness deliberately permits a signed-out wrapper so first-time sign-in is
possible. It does not prove ALAC readiness: the worker separately requires
playback readiness and authentication, and the release gate still requires an
actual preview download and playback check. No credentials are written to release
manifests. A host-side lock rejects simultaneous apply, rollback, and stop operations.

Validate lifecycle behavior with `python3 -m unittest test_wrapper_lifecycle`.
This uses mocked Docker calls and temporary release directories; no service starts.
The companion lifecycle and application release are independently reversible.
