# ReconcilePro database migrations and import tracking

Database schema changes are managed with Alembic. The application does not run
migrations itself: startup checks that the database is at the current revision
and fails with a generic instruction if it is not. Alembic reads an explicitly
provided `DATABASE_URL`; `migrations/env.py` does not load `.env` files or print
connection details. The CSV seed script also requires a migrated schema and
does not create tables itself.

## Schema revisions

- `0001_core_schema` describes the existing users, businesses, invoices, and
  GSTR-3B tables. It is the baseline for fresh databases and for safely adopting
  an existing database after its schema has been checked.
- `0002_import_batch_management` adds import batches and row outcomes, nullable
  batch associations on invoice and GSTR-3B rows, and soft-delete timestamps.

For a new disposable database, explicitly run `alembic upgrade head` with its
SQLite `DATABASE_URL`. For an existing database that predates Alembic, first
run the read-only `schema_parity.verify_legacy_schema(engine)` utility. It
compares tables, columns, SQL types and string lengths, nullability, primary
keys, foreign keys, unique constraints, and indexes against the independent
legacy baseline. The guarded
`schema_parity.stamp_verified_legacy_baseline(connection)` operation refuses
to stamp if any required object differs. Stamping records the baseline; it does
not create or repair tables. Do not stamp a database whose schema has not been
verified. Production migration and stamping operations require PostgreSQL and
an explicit `RECONCILEPRO_ALLOW_PRODUCTION_MIGRATION=true`; no production
migration is run as part of this project change.

## Import and retention semantics

- A successful or partially successful import has a fresh UUID `batch_id`,
  explicit business and importing-user ownership, source metadata, row counts,
  status, and timestamps. Simulator batches use a fixed fixture identifier;
  CSV batches store only a sanitized filename basename.
- Existing invoice rows are left with `import_batch_id = NULL`. The model
  reports these as `legacy_untracked`; the migration does not invent an old
  batch, filename, importing user, or import time. New import routes must create
  a batch and attach only rows inserted by that batch. Duplicate rows must not
  gain ownership of an existing invoice.
- Batch rows and batch-item audit records are retained. Deletion is represented
  by timestamps and actor IDs, not by deleting the batch. Future deletion code
  must soft-delete only records owned by the selected batch and filter deleted
  rows out of every invoice, reconciliation, anomaly, summary, report, and
  export query.
- GSTR-3B keeps its unique `(business_id, tax_period)` constraint. A future
  re-import after deletion must reactivate/update the same period row, not insert
  a second one. Each batch item retains before/after values for revised periods
  so a later audited deletion can restore the prior active values. The current
  revision adds schema only; it does not yet implement import or deletion APIs.
- Import batches and item snapshots have no automatic purge. Any future retention
  policy must be an explicit, separately approved operation that preserves the
  audit trail required by the product.
- Fixture seeding is disabled in production. Local demo seeding requires
  `RECONCILEPRO_ISOLATED_DEMO_SEED=true`, an explicit SQLite URL, a non-default
  database target, and an empty migrated database. It refuses to add demo
  records to an existing customer database.
- Downgrading the batch revision is blocked if batch/item records or tracked or
  soft-deleted rows exist. Downgrading the core schema is blocked while users,
  businesses, invoices, or GSTR-3B records exist. These checks prevent ordinary
  rollback commands from silently dropping data.
