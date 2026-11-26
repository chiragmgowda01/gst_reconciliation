"""Provision disposable integration roles for the PostgreSQL validation runner.

This helper is only for the runner's fresh loopback Docker database. It never
prints URLs or role credentials and refuses any database outside that contract.
"""

from __future__ import annotations

import os
import re
import sys

import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


def main() -> int:
    admin_url = os.getenv("DATABASE_URL", "")
    run_id = os.getenv("RECONCILEPRO_PG_RUN_ID", "")
    app_password = os.getenv("RECONCILEPRO_TEST_RUNTIME_PASSWORD", "")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id) or not re.fullmatch(r"[0-9a-f]{64}", app_password):
        print("Refusing role provisioning: task-specific run ID or temporary password is invalid.", file=sys.stderr)
        return 2

    try:
        parsed = make_url(admin_url)
        expected_db = f"reconcilepro_it_{run_id}"
        if (
            parsed.drivername != "postgresql+psycopg"
            or parsed.host not in {"127.0.0.1", "localhost"}
            or parsed.username != "postgres"
            or parsed.database != expected_db
            or parsed.port in {None, 5432}
        ):
            print("Refusing role provisioning: admin connection is not the runner's disposable loopback database.", file=sys.stderr)
            return 2

        engine = sa.create_engine(parsed, poolclass=NullPool, hide_parameters=True)
        try:
            with engine.begin() as connection:
                identity = connection.execute(sa.text(
                    "SELECT current_user, current_database()"
                )).one()
                if identity[0] != "postgres" or identity[1] != expected_db:
                    print("Refusing role provisioning: connected server identity did not match the disposable runner contract.", file=sys.stderr)
                    return 2
                existing = set(connection.execute(sa.text(
                    "SELECT rolname FROM pg_roles WHERE rolname IN "
                    "('reconcilepro_app', 'anon', 'authenticated', 'service_role')"
                )).scalars())
                if existing:
                    print("Refusing role provisioning: expected fresh test roles already exist.", file=sys.stderr)
                    return 2

                quoted_secret = connection.execute(
                    sa.text("SELECT quote_literal(:password)"), {"password": app_password}
                ).scalar_one()
                connection.exec_driver_sql(
                    "CREATE ROLE reconcilepro_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    f"NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {quoted_secret}"
                )
                for role in ("anon", "authenticated", "service_role"):
                    connection.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN")
                # Model the customary Supabase service_role attribute so tests
                # prove it still cannot reach the protected import tables.
                connection.exec_driver_sql("ALTER ROLE service_role BYPASSRLS")
        finally:
            engine.dispose()
    except Exception as exc:
        # Do not print driver text: exceptions can contain connection details.
        print(f"Disposable role provisioning failed ({type(exc).__name__}).", file=sys.stderr)
        return 1

    print("Disposable test roles provisioned; temporary credential was not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
