"""Restrict API roles and provision least-privilege runtime defaults.

Revision ID: 0005_runtime_role_security
Revises: 0004_import_batch_rev_counts
"""

from alembic import context, op
import sqlalchemy as sa


revision = "0005_runtime_role_security"
down_revision = "0004_import_batch_rev_counts"
branch_labels = None
depends_on = None

APP_ROLE = "reconcilepro_app"
API_ROLES = ("anon", "authenticated", "service_role")
APP_TABLE_PRIVILEGES = {
    "users": ("SELECT", "INSERT", "UPDATE"),
    "businesses": ("SELECT", "INSERT", "UPDATE"),
    "invoices": ("SELECT", "INSERT", "UPDATE"),
    "gstr3b_returns": ("SELECT", "INSERT", "UPDATE"),
    "import_batches": ("SELECT", "INSERT", "UPDATE"),
    "import_batch_items": ("SELECT", "INSERT"),
    "alembic_version": ("SELECT",),
}
APP_SEQUENCE_TABLES = ("users", "businesses", "invoices", "gstr3b_returns", "import_batch_items")
IMPORT_TABLES = ("import_batches", "import_batch_items")
COMMON_TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
SEQUENCE_PRIVILEGES = ("USAGE", "SELECT", "UPDATE")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite is used for local regression tests; PostgreSQL ACLs are not
        # emulated or weakened there.
        return
    if context.is_offline_mode():
        _offline_upgrade()
        return

    _require_provisioned_roles(bind)
    _revoke_data_api_access(bind)
    _harden_postgres_defaults()
    _grant_runtime_access(bind)
    _verify_effective_privileges(bind)


def _require_provisioned_roles(bind) -> None:
    current_user = bind.execute(sa.text("SELECT current_user")).scalar_one()
    if current_user != "postgres":
        raise RuntimeError(
            "Revision 0005 requires the postgres migration administrator because its default ACL changes are scoped to postgres."
        )

    required_roles = (APP_ROLE, *API_ROLES)
    found = {
        row["rolname"]: row
        for row in bind.execute(
            sa.text(
                "SELECT oid, rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, "
                "rolreplication, rolbypassrls, rolcanlogin "
                "FROM pg_roles WHERE rolname IN :role_names"
            ).bindparams(sa.bindparam("role_names", expanding=True)),
            {"role_names": required_roles},
        ).mappings()
    }
    missing = [role for role in required_roles if role not in found]
    if missing:
        raise RuntimeError(
            "Revision 0005 requires pre-provisioned PostgreSQL roles: " + ", ".join(missing)
        )

    app = found[APP_ROLE]
    if (
        not app["rolcanlogin"]
        or app["rolsuper"]
        or app["rolinherit"]
        or app["rolcreaterole"]
        or app["rolcreatedb"]
        or app["rolreplication"]
        or app["rolbypassrls"]
    ):
        raise RuntimeError(
            "reconcilepro_app must be a LOGIN, NOINHERIT role without superuser, role/database creation, replication, or BYPASSRLS privileges."
        )
    if bind.execute(
        sa.text("SELECT 1 FROM pg_auth_members WHERE member = :role_oid LIMIT 1"),
        {"role_oid": app["oid"]},
    ).first():
        raise RuntimeError("reconcilepro_app must not inherit or be able to SET ROLE to another PostgreSQL role.")

    app_owns_database = bind.execute(sa.text(
        "SELECT datdba = :role_oid FROM pg_database WHERE datname = current_database()"
    ), {"role_oid": app["oid"]}).scalar_one()
    app_owns_public = bind.execute(sa.text(
        "SELECT nspowner = :role_oid FROM pg_namespace WHERE nspname = 'public'"
    ), {"role_oid": app["oid"]}).scalar_one()
    app_owns_application_table = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname IN :table_names
              AND c.relowner = :role_oid
        )
    """).bindparams(sa.bindparam("table_names", expanding=True)), {
        "table_names": tuple(APP_TABLE_PRIVILEGES), "role_oid": app["oid"]
    }).scalar_one()
    app_owns_application_sequence = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_class AS sequence
            JOIN pg_namespace AS n ON n.oid = sequence.relnamespace
            WHERE n.nspname = 'public' AND sequence.relkind = 'S'
              AND sequence.relowner = :role_oid
        )
    """), {"role_oid": app["oid"]}).scalar_one()
    if app_owns_database or app_owns_public or app_owns_application_table or app_owns_application_sequence:
        raise RuntimeError(
            "reconcilepro_app must not own the database, public schema, application tables, or sequences."
        )

    for table_name in APP_TABLE_PRIVILEGES:
        if not bind.execute(sa.text(
            "SELECT to_regclass(:qualified_name)"
        ), {"qualified_name": f"public.{table_name}"}).scalar_one():
            raise RuntimeError(f"Revision 0005 requires existing table public.{table_name}.")


def _revoke_data_api_access(bind) -> None:
    bind.execute(sa.text(
        "REVOKE ALL PRIVILEGES ON TABLE public.import_batches, public.import_batch_items "
        "FROM PUBLIC, anon, authenticated, service_role"
    ))
    sequence_name = bind.execute(sa.text(
        "SELECT pg_get_serial_sequence('public.import_batch_items', 'id')"
    )).scalar_one_or_none()
    if not sequence_name:
        raise RuntimeError("Revision 0005 could not find the owned import_batch_items ID sequence.")
    sequence = bind.execute(sa.text("""
        SELECT ns.nspname, c.relname
        FROM pg_class AS c
        JOIN pg_namespace AS ns ON ns.oid = c.relnamespace
        WHERE c.oid = to_regclass(:sequence_name) AND c.relkind = 'S'
    """), {"sequence_name": sequence_name}).one_or_none()
    if sequence is None:
        raise RuntimeError("Revision 0005 could not inspect the import-item ID sequence.")
    preparer = bind.dialect.identifier_preparer
    qualified_sequence = f"{preparer.quote_schema(sequence.nspname)}.{preparer.quote(sequence.relname)}"
    bind.exec_driver_sql(
        f"REVOKE ALL PRIVILEGES ON SEQUENCE {qualified_sequence} FROM PUBLIC, anon, authenticated, service_role"
    )


def _harden_postgres_defaults() -> None:
    # PostgreSQL grants CREATE on public to PUBLIC on some upgraded databases.
    # A role-specific revoke cannot negate inherited PUBLIC rights, so remove
    # schema creation from the public/API principals and explicitly retain only
    # schema USAGE for the runtime role below.
    op.execute(
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC, anon, authenticated, service_role, reconcilepro_app"
    )
    for object_type in ("TABLES", "SEQUENCES"):
        # Revoke both global and public-schema defaults. PostgreSQL combines
        # these ACL sources, so a schema-only revoke cannot neutralize a global
        # grant made by an earlier administrator configuration.
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE ALL ON {object_type} "
            "FROM PUBLIC, anon, authenticated, service_role"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"REVOKE ALL ON {object_type} FROM PUBLIC, anon, authenticated, service_role"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE ALL ON {object_type} FROM reconcilepro_app"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
            f"REVOKE ALL ON {object_type} FROM reconcilepro_app"
        )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
        # New tables get only read/insert by default. Any future update-capable
        # table must receive an explicit reviewed grant in its own migration.
        "GRANT SELECT, INSERT ON TABLES TO reconcilepro_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO reconcilepro_app"
    )


def _grant_runtime_access(bind) -> None:
    preparer = bind.dialect.identifier_preparer
    app_role = preparer.quote(APP_ROLE)
    database_name = preparer.quote(bind.execute(sa.text("SELECT current_database()")).scalar_one())
    bind.exec_driver_sql(f"GRANT CONNECT ON DATABASE {database_name} TO {app_role}")
    bind.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {app_role}")

    table_list = ", ".join(
        f"public.{preparer.quote(table_name)}" for table_name in APP_TABLE_PRIVILEGES
    )
    bind.exec_driver_sql(f"REVOKE ALL PRIVILEGES ON TABLE {table_list} FROM {app_role}")

    for table_name, privileges in APP_TABLE_PRIVILEGES.items():
        quoted_table = f"public.{preparer.quote(table_name)}"
        bind.exec_driver_sql(
            f"GRANT {', '.join(privileges)} ON TABLE {quoted_table} TO {app_role}"
        )

    for table_name in APP_SEQUENCE_TABLES:
        sequence_name = bind.execute(sa.text(
            "SELECT pg_get_serial_sequence(:qualified_table, 'id')"
        ), {"qualified_table": f"public.{table_name}"}).scalar_one_or_none()
        if not sequence_name:
            raise RuntimeError(f"Revision 0005 could not find the ID sequence for public.{table_name}.")
        sequence = bind.execute(sa.text("""
            SELECT ns.nspname, c.relname
            FROM pg_class AS c
            JOIN pg_namespace AS ns ON ns.oid = c.relnamespace
            WHERE c.oid = to_regclass(:sequence_name) AND c.relkind = 'S'
        """), {"sequence_name": sequence_name}).one_or_none()
        if sequence is None:
            raise RuntimeError(f"Revision 0005 could not inspect the ID sequence for public.{table_name}.")
        qualified_sequence = f"{preparer.quote_schema(sequence.nspname)}.{preparer.quote(sequence.relname)}"
        bind.exec_driver_sql(f"REVOKE ALL PRIVILEGES ON SEQUENCE {qualified_sequence} FROM {app_role}")
        bind.exec_driver_sql(
            f"GRANT USAGE, SELECT ON SEQUENCE {qualified_sequence} TO {app_role}"
        )


def _verify_effective_privileges(bind) -> None:
    server_version = int(bind.execute(sa.text("SHOW server_version_num")).scalar_one())
    table_privileges = COMMON_TABLE_PRIVILEGES + (("MAINTAIN",) if server_version >= 170000 else ())

    for table_name in IMPORT_TABLES:
        for role_name in API_ROLES:
            for privilege in table_privileges:
                allowed = bind.execute(sa.text(
                    "SELECT has_table_privilege(:role_name, :table_name, :privilege)"
                ), {"role_name": role_name, "table_name": f"public.{table_name}", "privilege": privilege}).scalar_one()
                if allowed:
                    raise RuntimeError(
                        f"Revision 0005 verification failed: {role_name} retains {privilege} on public.{table_name}."
                    )
        public_grant = bind.execute(sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_class AS c
                CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) AS acl
                WHERE c.oid = to_regclass(:table_name) AND acl.grantee = 0
            )
        """), {"table_name": f"public.{table_name}"}).scalar_one()
        if public_grant:
            raise RuntimeError(f"Revision 0005 verification failed: PUBLIC retains a grant on public.{table_name}.")

    import_sequence = bind.execute(sa.text(
        "SELECT pg_get_serial_sequence('public.import_batch_items', 'id')"
    )).scalar_one()
    for role_name in API_ROLES:
        for privilege in SEQUENCE_PRIVILEGES:
            allowed = bind.execute(sa.text(
                "SELECT has_sequence_privilege(:role_name, :sequence_name, :privilege)"
            ), {"role_name": role_name, "sequence_name": import_sequence, "privilege": privilege}).scalar_one()
            if allowed:
                raise RuntimeError(
                    f"Revision 0005 verification failed: {role_name} retains {privilege} on the import-item sequence."
                )
    public_sequence_grant = bind.execute(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_class AS c
            CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl, acldefault('S', c.relowner))) AS acl
            WHERE c.oid = to_regclass(:sequence_name) AND acl.grantee = 0
        )
    """), {"sequence_name": import_sequence}).scalar_one()
    if public_sequence_grant:
        raise RuntimeError("Revision 0005 verification failed: PUBLIC retains a grant on the import-item sequence.")

    # Check defaults made by postgres at both global and public-schema scopes.
    # ACLs at both scopes combine, so either one granting a Data API role (or
    # PUBLIC) would reopen access to future objects.
    default_acl_leaks = bind.execute(sa.text("""
        SELECT d.defaclobjtype, COALESCE(n.nspname, '<global>') AS schema_name,
               pg_get_userbyid(d.defaclrole) AS owner_name,
               grantee.rolname AS grantee_name,
               acl.privilege_type
        FROM pg_default_acl AS d
        LEFT JOIN pg_namespace AS n ON n.oid = d.defaclnamespace
        CROSS JOIN LATERAL aclexplode(d.defaclacl) AS acl
        LEFT JOIN pg_roles AS grantee ON grantee.oid = acl.grantee
        WHERE d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = 'postgres')
          AND (d.defaclnamespace = 0 OR n.nspname = 'public')
          AND d.defaclobjtype IN ('r', 'S')
          AND (acl.grantee = 0 OR grantee.rolname IN ('anon', 'authenticated', 'service_role'))
    """)).mappings().all()
    if default_acl_leaks:
        item = default_acl_leaks[0]
        raise RuntimeError(
            "Revision 0005 verification failed: postgres default ACL grants "
            f"{item['privilege_type']} on future object type {item['defaclobjtype']} "
            f"({item['schema_name']}) to {item['grantee_name']}."
        )

    app_default_rows = bind.execute(sa.text("""
        SELECT d.defaclobjtype, COALESCE(n.nspname, '<global>') AS schema_name,
               acl.privilege_type
        FROM pg_default_acl AS d
        LEFT JOIN pg_namespace AS n ON n.oid = d.defaclnamespace
        CROSS JOIN LATERAL aclexplode(d.defaclacl) AS acl
        WHERE d.defaclrole = (SELECT oid FROM pg_roles WHERE rolname = 'postgres')
          AND (d.defaclnamespace = 0 OR n.nspname = 'public')
          AND d.defaclobjtype IN ('r', 'S')
          AND acl.grantee = (SELECT oid FROM pg_roles WHERE rolname = 'reconcilepro_app')
    """)).mappings().all()
    # The public-schema future-table default is deliberately narrower than
    # existing write-capable tables; future schemas need their own reviewed
    # grants. Sequence values may be consumed/read, never set by the app role.
    actual_app_defaults = {
        (row["defaclobjtype"], row["schema_name"], row["privilege_type"])
        for row in app_default_rows
    }
    expected_app_defaults = {
        ("r", "public", "SELECT"),
        ("r", "public", "INSERT"),
        ("S", "public", "USAGE"),
        ("S", "public", "SELECT"),
    }
    if actual_app_defaults != expected_app_defaults:
        raise RuntimeError(
            "Revision 0005 verification failed: reconcilepro_app future-object defaults "
            f"did not match reviewed privileges (actual={sorted(actual_app_defaults)!r})."
        )

    for table_name, expected_privileges in APP_TABLE_PRIVILEGES.items():
        for privilege in table_privileges:
            allowed = bind.execute(sa.text(
                "SELECT has_table_privilege(:role_name, :table_name, :privilege)"
            ), {"role_name": APP_ROLE, "table_name": f"public.{table_name}", "privilege": privilege}).scalar_one()
            expected = privilege in expected_privileges
            if bool(allowed) != expected:
                result = "missing" if expected else "unnecessary"
                raise RuntimeError(
                    f"Revision 0005 verification failed: {result} {privilege} privilege for {APP_ROLE} on public.{table_name}."
                )

    if not bind.execute(sa.text("SELECT has_schema_privilege(:role_name, 'public', 'USAGE')"), {"role_name": APP_ROLE}).scalar_one():
        raise RuntimeError("Revision 0005 verification failed: reconcilepro_app lacks USAGE on schema public.")
    if not bind.execute(sa.text("SELECT has_database_privilege(:role_name, current_database(), 'CONNECT')"), {"role_name": APP_ROLE}).scalar_one():
        raise RuntimeError("Revision 0005 verification failed: reconcilepro_app lacks CONNECT on the current database.")
    if bind.execute(sa.text("SELECT has_schema_privilege(:role_name, 'public', 'CREATE')"), {"role_name": APP_ROLE}).scalar_one():
        raise RuntimeError("Revision 0005 verification failed: reconcilepro_app has CREATE on schema public.")
    for role_name in API_ROLES:
        if bind.execute(sa.text(
            "SELECT has_schema_privilege(:role_name, 'public', 'CREATE')"
        ), {"role_name": role_name}).scalar_one():
            raise RuntimeError(
                f"Revision 0005 verification failed: {role_name} has CREATE on schema public."
            )
    if bind.execute(sa.text("SELECT has_database_privilege(:role_name, current_database(), 'CREATE')"), {"role_name": APP_ROLE}).scalar_one():
        raise RuntimeError("Revision 0005 verification failed: reconcilepro_app has CREATE on the database.")
    if not bind.execute(sa.text("SELECT has_table_privilege(:role_name, 'public.alembic_version', 'SELECT')"), {"role_name": APP_ROLE}).scalar_one():
        raise RuntimeError("Revision 0005 verification failed: reconcilepro_app cannot read alembic_version.")

    for table_name in APP_SEQUENCE_TABLES:
        sequence_name = bind.execute(sa.text(
            "SELECT pg_get_serial_sequence(:qualified_table, 'id')"
        ), {"qualified_table": f"public.{table_name}"}).scalar_one_or_none()
        if not sequence_name:
            raise RuntimeError(f"Revision 0005 verification failed: sequence for public.{table_name} is missing.")
        for privilege in ("USAGE", "SELECT", "UPDATE"):
            actual = bind.execute(sa.text(
                "SELECT has_sequence_privilege(:role_name, :sequence_name, :privilege)"
            ), {"role_name": APP_ROLE, "sequence_name": sequence_name, "privilege": privilege}).scalar_one()
            expected = privilege in {"USAGE", "SELECT"}
            if bool(actual) != expected:
                result = "missing" if expected else "unnecessary"
                raise RuntimeError(
                    f"Revision 0005 verification failed: {result} {privilege} privilege for "
                    f"{APP_ROLE} on sequence for public.{table_name}."
                )

    for table_name, expected_privileges in APP_TABLE_PRIVILEGES.items():
        if bind.execute(sa.text("SELECT pg_has_role(:role_name, table_owner, 'USAGE') FROM (SELECT pg_get_userbyid(relowner) AS table_owner FROM pg_class WHERE oid = to_regclass(:table_name)) AS owner_info"), {
            "role_name": APP_ROLE, "table_name": f"public.{table_name}"
        }).scalar_one():
            raise RuntimeError(f"Revision 0005 verification failed: reconcilepro_app inherits ownership of public.{table_name}.")


def _offline_upgrade() -> None:
    # Emit deterministic SQL without opening a connection. Preconditions and
    # effective-grant checks execute when the generated script is applied.
    op.execute(sa.text("""
        DO $$ DECLARE app_role_oid oid; BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reconcilepro_app') THEN
            RAISE EXCEPTION 'Revision 0005 requires pre-provisioned role reconcilepro_app';
          END IF;
          SELECT oid INTO app_role_oid FROM pg_roles
            WHERE rolname = 'reconcilepro_app' AND rolcanlogin AND NOT rolsuper
              AND NOT rolinherit AND NOT rolcreatedb AND NOT rolcreaterole
              AND NOT rolreplication AND NOT rolbypassrls;
          IF app_role_oid IS NULL THEN
            RAISE EXCEPTION 'reconcilepro_app must be LOGIN, NOINHERIT and have no elevated role attributes';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member = app_role_oid) THEN
            RAISE EXCEPTION 'reconcilepro_app must not belong to any other role';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
             OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
             OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
            RAISE EXCEPTION 'Revision 0005 requires Supabase Data API roles anon, authenticated, and service_role';
          END IF;
          IF current_user <> 'postgres' THEN
            RAISE EXCEPTION 'Revision 0005 must be applied by postgres';
          END IF;
        END $$;
    """))
    op.execute("REVOKE ALL PRIVILEGES ON TABLE public.import_batches, public.import_batch_items FROM PUBLIC, anon, authenticated, service_role")
    op.execute(sa.text("""
        DO $$ DECLARE sequence_name text; BEGIN
          sequence_name := pg_get_serial_sequence('public.import_batch_items', 'id');
          IF sequence_name IS NULL THEN
            RAISE EXCEPTION 'Revision 0005 could not find the owned import_batch_items ID sequence';
          END IF;
          EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC, anon, authenticated, service_role', sequence_name);
        END $$;
    """))
    _harden_postgres_defaults()
    op.execute(sa.text("""
        DO $$ BEGIN
          EXECUTE format('GRANT CONNECT ON DATABASE %I TO reconcilepro_app', current_database());
        END $$;
    """))
    op.execute("GRANT USAGE ON SCHEMA public TO reconcilepro_app")
    op.execute(
        "REVOKE ALL PRIVILEGES ON TABLE public.users, public.businesses, public.invoices, "
        "public.gstr3b_returns, public.import_batches, public.import_batch_items, "
        "public.alembic_version FROM reconcilepro_app"
    )
    for table_name, privileges in APP_TABLE_PRIVILEGES.items():
        op.execute(f"GRANT {', '.join(privileges)} ON TABLE public.{table_name} TO reconcilepro_app")
    for table_name in APP_SEQUENCE_TABLES:
        op.execute(sa.text(f"""
            DO $$ DECLARE sequence_name text; BEGIN
              sequence_name := pg_get_serial_sequence('public.{table_name}', 'id');
              IF sequence_name IS NULL THEN
                RAISE EXCEPTION 'Revision 0005 could not find ID sequence for public.{table_name}';
              END IF;
              EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM reconcilepro_app', sequence_name);
              EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO reconcilepro_app', sequence_name);
            END $$;
        """))
    op.execute(sa.text("""
        DO $$ DECLARE p text; t text; r text; seq text; actual boolean; expected boolean;
          expected_privs text[]; app_default_count integer; BEGIN
          FOREACH t IN ARRAY ARRAY['import_batches', 'import_batch_items'] LOOP
            FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
              FOREACH p IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] LOOP
                IF has_table_privilege(r, 'public.' || t, p) THEN
                  RAISE EXCEPTION 'Revision 0005 verification failed: Data API role retains table access';
                END IF;
              END LOOP;
            END LOOP;
          END LOOP;
          seq := pg_get_serial_sequence('public.import_batch_items', 'id');
          FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
            FOREACH p IN ARRAY ARRAY['USAGE', 'SELECT', 'UPDATE'] LOOP
              IF has_sequence_privilege(r, seq, p) THEN
                RAISE EXCEPTION 'Revision 0005 verification failed: Data API role retains import sequence access';
              END IF;
            END LOOP;
          END LOOP;
          FOREACH t IN ARRAY ARRAY['users', 'businesses', 'invoices', 'gstr3b_returns', 'import_batch_items'] LOOP
            seq := pg_get_serial_sequence('public.' || t, 'id');
            FOREACH p IN ARRAY ARRAY['USAGE', 'SELECT', 'UPDATE'] LOOP
              actual := has_sequence_privilege('reconcilepro_app', seq, p);
              expected := p = ANY(ARRAY['USAGE', 'SELECT']);
              IF actual IS DISTINCT FROM expected THEN
                RAISE EXCEPTION 'Revision 0005 verification failed: runtime sequence privilege mismatch';
              END IF;
            END LOOP;
          END LOOP;
          FOREACH t IN ARRAY ARRAY['users', 'businesses', 'invoices', 'gstr3b_returns',
                                    'import_batches', 'import_batch_items', 'alembic_version'] LOOP
            expected_privs := CASE t
              WHEN 'import_batch_items' THEN ARRAY['SELECT', 'INSERT']
              WHEN 'alembic_version' THEN ARRAY['SELECT']
              ELSE ARRAY['SELECT', 'INSERT', 'UPDATE']
            END;
            FOREACH p IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] LOOP
              actual := has_table_privilege('reconcilepro_app', 'public.' || t, p);
              expected := p = ANY(expected_privs);
              IF actual IS DISTINCT FROM expected THEN
                RAISE EXCEPTION 'Revision 0005 verification failed: runtime table privilege mismatch';
              END IF;
            END LOOP;
          END LOOP;
          IF current_setting('server_version_num')::integer >= 170000 THEN
            FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
              FOREACH t IN ARRAY ARRAY['import_batches', 'import_batch_items'] LOOP
                IF has_table_privilege(r, 'public.' || t, 'MAINTAIN') THEN
                  RAISE EXCEPTION 'Revision 0005 verification failed: Data API role retains MAINTAIN';
                END IF;
              END LOOP;
            END LOOP;
            FOREACH t IN ARRAY ARRAY['users', 'businesses', 'invoices', 'gstr3b_returns',
                                      'import_batches', 'import_batch_items', 'alembic_version'] LOOP
              IF has_table_privilege('reconcilepro_app', 'public.' || t, 'MAINTAIN') THEN
                RAISE EXCEPTION 'Revision 0005 verification failed: runtime role has unnecessary MAINTAIN';
              END IF;
            END LOOP;
          END IF;
          IF has_schema_privilege('reconcilepro_app', 'public', 'CREATE')
             OR has_database_privilege('reconcilepro_app', current_database(), 'CREATE')
             OR NOT has_table_privilege('reconcilepro_app', 'public.alembic_version', 'SELECT') THEN
            RAISE EXCEPTION 'Revision 0005 verification failed: runtime role has unsafe or missing access';
          END IF;
          IF has_schema_privilege('anon', 'public', 'CREATE')
             OR has_schema_privilege('authenticated', 'public', 'CREATE')
             OR has_schema_privilege('service_role', 'public', 'CREATE') THEN
            RAISE EXCEPTION 'Revision 0005 verification failed: a Data API role can create in public';
          END IF;
          IF EXISTS (
            SELECT 1 FROM pg_default_acl d
            CROSS JOIN LATERAL aclexplode(d.defaclacl) acl
            LEFT JOIN pg_roles r ON r.oid = acl.grantee
            WHERE d.defaclrole = 'postgres'::regrole
              AND (d.defaclnamespace = 0 OR d.defaclnamespace = 'public'::regnamespace)
              AND d.defaclobjtype IN ('r', 'S')
              AND (acl.grantee = 0 OR r.rolname IN ('anon', 'authenticated', 'service_role'))
          ) THEN
            RAISE EXCEPTION 'Revision 0005 verification failed: API role or PUBLIC retains future-object defaults';
          END IF;
          SELECT count(*) INTO app_default_count
            FROM pg_default_acl d
            CROSS JOIN LATERAL aclexplode(d.defaclacl) acl
            WHERE d.defaclrole = 'postgres'::regrole
              AND (d.defaclnamespace = 0 OR d.defaclnamespace = 'public'::regnamespace)
              AND d.defaclobjtype IN ('r', 'S')
              AND acl.grantee = 'reconcilepro_app'::regrole
              AND ((d.defaclobjtype = 'r' AND d.defaclnamespace = 'public'::regnamespace
                    AND acl.privilege_type IN ('SELECT', 'INSERT'))
                OR (d.defaclobjtype = 'S' AND d.defaclnamespace = 'public'::regnamespace
                    AND acl.privilege_type IN ('USAGE', 'SELECT')));
          IF app_default_count <> 4 OR EXISTS (
            SELECT 1 FROM pg_default_acl d
            CROSS JOIN LATERAL aclexplode(d.defaclacl) acl
            WHERE d.defaclrole = 'postgres'::regrole
              AND (d.defaclnamespace = 0 OR d.defaclnamespace = 'public'::regnamespace)
              AND d.defaclobjtype IN ('r', 'S')
              AND acl.grantee = 'reconcilepro_app'::regrole
              AND NOT ((d.defaclobjtype = 'r' AND d.defaclnamespace = 'public'::regnamespace
                        AND acl.privilege_type IN ('SELECT', 'INSERT'))
                    OR (d.defaclobjtype = 'S' AND d.defaclnamespace = 'public'::regnamespace
                        AND acl.privilege_type IN ('USAGE', 'SELECT')))
          ) THEN
            RAISE EXCEPTION 'Revision 0005 verification failed: runtime default privileges differ from policy';
          END IF;
        END $$;
    """))


def downgrade() -> None:
    # Privilege hardening is intentionally forward-only. Never restore Data API
    # grants or weaken the default ACL during an ordinary downgrade.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        raise RuntimeError(
            "Revision 0005 is security hardening and cannot be automatically downgraded; "
            "its restrictive grants/defaults must remain in place."
        )
    # SQLite has no corresponding ACL changes. Before allowing Alembic to
    # continue into earlier destructive revisions, preserve the same data
    # guards those revisions enforce. This keeps failed SQLite downgrades at
    # the current revision instead of partially walking back the chain.
    revised_rows = bind.execute(sa.text(
        "SELECT COUNT(*) FROM import_batches WHERE revised_rows > 0"
    )).scalar_one()
    if revised_rows:
        raise RuntimeError(
            "Revision-count migration downgrade blocked because revised import history exists. "
            "Preserve the batch audit counts before considering a downgrade."
        )
    protected = (
        "SELECT COUNT(*) FROM import_batches",
        "SELECT COUNT(*) FROM import_batch_items",
        "SELECT COUNT(*) FROM invoices WHERE import_batch_id IS NOT NULL OR deleted_at IS NOT NULL",
        "SELECT COUNT(*) FROM gstr3b_returns WHERE import_batch_id IS NOT NULL OR deleted_at IS NOT NULL",
    )
    if any(bind.execute(sa.text(query)).scalar_one() for query in protected):
        raise RuntimeError(
            "Import-batch migration downgrade blocked because tracked or audit data exists. "
            "Export and preserve the audit history before considering a downgrade."
        )
