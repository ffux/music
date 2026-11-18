# Conversion recovery and deployment drain

After a successful downloader exit, the worker persists a job-scoped source list
in `queue.db` (`conversion_plans`) before creating any FLAC output. Each original
has a settled content fingerprint. Restart resumes only running jobs with this
checkpoint; it does not repeat the download. Existing verified FLAC/marker pairs
are reused. Changed or missing originals, unsafe paths, or unmarked final outputs
stop recovery and leave the job in error for manual review. Originals, unmarked
outputs, and abandoned hidden temporary files are never deleted by recovery.

An interruption before the successful-download checkpoint remains an error, not
an inferred success. Failed recovery is not retried in an infinite loop.

## Deployment controller contract

```
python3 /app/deployment_control.py [--db PATH] begin TOKEN
python3 /app/deployment_control.py [--db PATH] status TOKEN
python3 /app/deployment_control.py [--db PATH] end TOKEN
```

Default DB: `$DATA_DIR/queue.db`, or `/data/queue.db`. Output is JSON with
`active`, `drained`, `running`, and `pending`; exit 0 means success, exit 1 means
conflict/error. Tokens must be nonempty and at most 200 characters. `begin` is
idempotent for its owner; another owner cannot inspect, replace, or release it.
`end` requires an existing matching owner.

Worker claim and drain acquisition share a SQLite `BEGIN IMMEDIATE` transaction.
The controller waits for `active && drained`: no running job remains, while
pending jobs may remain queued. Keep the same token through promotion/rollback,
then release it on the container sharing the production DB. The drain persists
across process/container loss and has no automatic expiry. After controller loss,
inspect and release explicitly using the original token. A missing token or CLI
must never be interpreted as safe to promote.

The first upgrade from a worker lacking drain support uses the durable bootstrap
helper described below, installed atomically while no jobs are running. Install
the compatible application before enabling the normal deployment drain hook. Staging must use isolated data/music volumes and must not run a
second worker against the production queue. This implementation assumes one
production worker, as the existing deployment does.

## First-upgrade bootstrap for legacy workers

`bootstrap_control.py` is a standalone standard-library helper with the same
`[--db PATH] begin|status|end TOKEN` interface. It returns the drain JSON plus
`legacyGuard`. `begin` uses one immediate transaction to verify zero running jobs,
claim the owner, and install two persistent triggers on `jobs`. These reject any
insert or status update entering `running`, before the legacy worker starts its
downloader. New pending queue requests remain accepted. Updated workers also see
the normal persistent drain row. Guard installation does not stop any process.

The guard survives helper exit, app crash, machine reboot and legacy rollback.
There is no expiry. The controller must retain its owner token. After verifying
the new app's drain support and successful promotion, call bootstrap `end` with
that token. This atomically removes only the exact owned trigger pair and its
matching bootstrap/drain rows. For an explicitly abandoned upgrade, the same
release restores legacy operation. Generic drain `end` refuses an active or
partial bootstrap guard, preventing accidental partial release.

Different owners, an active job, unowned trigger names, or partial/modified guard
state cause a refusal without modifying that state. Do not manually drop triggers
or release a foreign drain to work around an error. Review partial state and
recover deliberately. The deployment controller still needs to verify process
health and the intended app version before choosing to release the guard.
