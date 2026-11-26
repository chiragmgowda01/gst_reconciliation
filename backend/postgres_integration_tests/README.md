# PostgreSQL-only integration suite

Run this suite only through
`scripts/Invoke-ReconcileProPostgresValidation.ps1` from ordinary Windows
PowerShell. From the repository root, use:

```powershell
& .\scripts\Invoke-ReconcileProPostgresValidation.ps1
```

It expects Docker Desktop and the backend virtual environment. By default,
the runner uses `postgres:16-alpine` (pulled if needed), preserving the
existing PostgreSQL 16 workflow. The runner creates a new
container with a per-run database name, runtime-only credentials, a random
host port bound to `127.0.0.1`, and a tmpfs data directory. It does not mount
named Docker volumes. The container is removed by its exact ID only after the
run label is verified. If the image unexpectedly creates an anonymous volume,
cleanup only considers a volume absent from the pre-run volume list and
confirmed as unattached after this container is removed.

The runner provisions a one-run `reconcilepro_app` login with a generated
temporary secret, then applies `alembic upgrade head` as the disposable
`postgres` migration administrator. It passes the two URLs only to child
processes and redacts them from output. The API is imported under the
least-privilege URL; the admin URL is used only by migration and test setup.
It then runs this directory with `--confcutdir=postgres_integration_tests`.
That deliberate separation prevents `backend/tests/conftest.py` from replacing
the PostgreSQL URL with in-memory SQLite. The integration module independently
checks the URL is psycopg/PostgreSQL, loopback-only, and matches the unique
database/run identifier before it imports the application.

The suite covers a fresh revision-0005 schema; independent legacy ORM schema
adoption; defaults, constraints, collations, sequence ownership/configuration
and sequence-state checks; migration 0003 refusal when active invoice keys
are duplicated (including preservation of both rows and the unapplied revision);
migration authorization; concurrent invoice
imports; rollback for invoice and GSTR-3B imports; tenant boundaries; and
GSTR-3B revision restoration, stale-snapshot rejection, and concurrent
deletion ordering.

The fresh-database check also compares the complete migrated schema at
`0005_runtime_role_security` against registered SQLAlchemy model metadata,
including types, nullability, defaults, keys, constraints, indexes, the active
invoice partial-index predicate, and integer sequence ownership/configuration/state.
The role-security check verifies effective CRUD/DDL permissions, import-table
and sequence denial for the Supabase Data API roles, role memberships, and
default ACL behavior on a transactionally rolled-back probe table. No
production or shared database may be used.

To validate on PostgreSQL 17.12, select the exact supported version and image:

```powershell
& .\scripts\Invoke-ReconcileProPostgresValidation.ps1 -PostgresVersion 17.12
```

The runner accepts only `16` and `17.12`; all other versions are rejected.
For 17.12 it requires the actual server-reported version to be exactly
`17.12` before applying migrations or running tests. PostgreSQL 16 retains its
existing major-version check and remains the default.

This does not replace the existing SQLite suite. Run that separately from
`backend` with `python -m pytest tests -q`; it continues using
`backend/tests/conftest.py` and an in-memory database. Do not point either
suite at a shared or hosted database.

For production role provisioning and the separation between the Render runtime
URL and short-lived migration URL, see
[`migrations/RUNTIME_DATABASE_ROLE.md`](../migrations/RUNTIME_DATABASE_ROLE.md).
