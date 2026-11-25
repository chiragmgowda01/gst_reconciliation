# Database migration safety

Alembic online commands connect to the database and apply schema changes. They
must only be run against a disposable local database during development, or
against production after a separately approved rollout and explicit
`RECONCILEPRO_ALLOW_PRODUCTION_MIGRATION=true` authorization.

Alembic offline commands such as `alembic upgrade head --sql` only render SQL;
they do not connect to a database or apply changes. Production SQL generation
still requires the same authorization flag and a PostgreSQL URL. Generated SQL
is not evidence that a database is compatible, and running that SQL elsewhere
is an execution operation subject to the online migration safeguards and the
approved rollout process.

For an existing pre-Alembic database, `0001_core_schema` may only be stamped
through `schema_parity.stamp_verified_legacy_baseline(connection)`, after the
read-only parity report matches. A mismatch or an inspection the tool cannot
complete blocks stamping. Do not stamp an unverified database or use a direct
Alembic stamp command.
