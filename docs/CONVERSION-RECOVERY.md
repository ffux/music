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

The first upgrade from a worker lacking drain support needs an independently
controlled idle window. Install the compatible application before enabling the
deployment hook. Staging must use isolated data/music volumes and must not run a
second worker against the production queue. This implementation assumes one
production worker, as the existing deployment does.
