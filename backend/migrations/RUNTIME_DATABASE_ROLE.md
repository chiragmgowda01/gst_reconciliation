# Runtime database role provisioning

The FastAPI service uses `APP_DATABASE_URL`. In production this must connect
as `reconcilepro_app`; startup checks the connected PostgreSQL role and refuses
to run under the migration administrator. `DATABASE_URL` is reserved for a
short-lived, explicitly authorized Alembic process and is not used by ordinary
application requests. Do not place the administrator URL in the Render web
service environment when a controlled migration process can supply it only for
the migration window.

## Provisioning procedure

1. Confirm the intended Supabase project, database, and a recovery plan before
   creating a role. Do not use this procedure against a shared or staging
   database as a substitute for production change approval.
2. Connect through a trusted administrative PostgreSQL session that does not
   record SQL input in shell history. Create `reconcilepro_app` as a `NOLOGIN`
   role with `NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION
   NOBYPASSRLS`. Set a generated unique password using the client's protected
   interactive password prompt (for `psql`, `\password reconcilepro_app`),
   then enable `LOGIN`. Never put the password in Git, a command argument,
   application logs, or a migration.
3. Store the password in an approved secret manager and configure Render's
   `APP_DATABASE_URL` as a PostgreSQL psycopg connection URL for
   `reconcilepro_app`. URL-encode reserved characters in the password. Add the
   value through Render's secret/environment interface; do not paste it into
   source files or diagnostic output.
4. Keep the elevated `DATABASE_URL` out of the long-running Render web service
   where feasible. Supply it only to the separate migration process for a
   reviewed, explicitly authorized migration window. The migration must run
   as `postgres` for revision 0005 because it changes that role's default ACLs.
5. Apply the reviewed migration chain through `0005_runtime_role_security`
   using the controlled migration procedure. Revision 0005 refuses to create
   the runtime role and fails if it has not been provisioned.
6. Set the web service to `APP_DATABASE_URL` only, restart it, and verify the
   health endpoint reports PostgreSQL. Confirm startup completed against the
   expected Alembic head. Never expose either URL in logs or HTTP responses.

The application role is intentionally not a schema owner and receives no DDL,
table hard-delete, or truncate permission. To change its access later, review a
new migration and add narrowly scoped grants; do not broaden default ACLs as a
quick fix. Row-level security remains a separate design decision and is not
enabled by revision 0005 because compatible tenant-context policies are not
currently configured.
