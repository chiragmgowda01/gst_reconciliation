# PostgreSQL-only integration suite

Run this suite only through
`scripts/Invoke-ReconcileProPostgresValidation.ps1` from ordinary Windows
PowerShell. From the repository root, use:

```powershell
& .\scripts\Invoke-ReconcileProPostgresValidation.ps1
```

It expects Docker Desktop, the backend virtual environment, and
the `postgres:16-alpine` image (pulled if needed). The runner creates a new
container with a per-run database name, runtime-only credentials, a random
host port bound to `127.0.0.1`, and a tmpfs data directory. It does not mount
named Docker volumes. The container is removed by its exact ID only after the
run label is verified. If the image unexpectedly creates an anonymous volume,
cleanup only considers a volume absent from the pre-run volume list and
confirmed as unattached after this container is removed.

The runner applies `alembic upgrade head` to its fresh PostgreSQL database,
then runs this directory with `--confcutdir=postgres_integration_tests`.
That deliberate separation prevents `backend/tests/conftest.py` from replacing
the PostgreSQL URL with in-memory SQLite. The integration module independently
checks the URL is psycopg/PostgreSQL, loopback-only, and matches the unique
database/run identifier before it imports the application.

The suite covers a fresh revision-0004 schema; independent legacy ORM schema
adoption; defaults, constraints, collations, sequence ownership/configuration
and sequence-state checks; migration 0003 refusal when active invoice keys
are duplicated (including preservation of both rows and the unapplied revision);
migration authorization; concurrent invoice
imports; rollback for invoice and GSTR-3B imports; tenant boundaries; and
GSTR-3B revision restoration, stale-snapshot rejection, and concurrent
deletion ordering.

This does not replace the existing SQLite suite. Run that separately from
`backend` with `python -m pytest tests -q`; it continues using
`backend/tests/conftest.py` and an in-memory database. Do not point either
suite at a shared or hosted database.
