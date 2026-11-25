"""Read-only verification and guarded adoption of the legacy ORM schema."""

from dataclasses import dataclass
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from legacy_schema import LEGACY_METADATA
from migration_safety import VERIFIED_LEGACY_STAMP_TOKEN, require_migration_authorization


@dataclass(frozen=True)
class SchemaParityReport:
    mismatches: tuple[str, ...]

    @property
    def matches(self) -> bool:
        return not self.mismatches

    def format(self) -> str:
        if self.matches:
            return "Legacy schema matches the 0001_core_schema baseline."
        return "Legacy schema parity failed:\n- " + "\n- ".join(self.mismatches)


def _type_signature(sql_type) -> tuple:
    """Normalize dialect-specific type classes without hiding size/type changes."""
    if isinstance(sql_type, String):
        return ("string", sql_type.length)
    if isinstance(sql_type, SmallInteger):
        return ("small_integer",)
    if isinstance(sql_type, Integer):
        return ("integer",)
    if isinstance(sql_type, Float):
        return ("float",)
    if isinstance(sql_type, Numeric):
        return ("numeric", sql_type.precision, sql_type.scale)
    if isinstance(sql_type, DateTime):
        return ("datetime", bool(sql_type.timezone))
    if isinstance(sql_type, Date):
        return ("date",)
    return (sql_type.__class__.__name__.lower(),)


def _foreign_key_signature(constraint) -> tuple:
    if isinstance(constraint, dict):
        options = constraint.get("options") or {}
        return (
            tuple(constraint.get("constrained_columns") or ()),
            constraint.get("referred_table"),
            tuple(constraint.get("referred_columns") or ()),
            (options.get("ondelete") or "").upper(),
            (options.get("onupdate") or "").upper(),
        )
    return (
        tuple(constraint.column_keys),
        constraint.referred_table,
        tuple(element.column.name for element in constraint.elements),
        (constraint.ondelete or "").upper(),
        (constraint.onupdate or "").upper(),
    )


def _expected_foreign_keys(table) -> set[tuple]:
    signatures = set()
    for constraint in table.foreign_key_constraints:
        signatures.add(
            (
                tuple(constraint.column_keys),
                constraint.elements[0].column.table.name,
                tuple(element.column.name for element in constraint.elements),
                (constraint.ondelete or "").upper(),
                (constraint.onupdate or "").upper(),
            )
        )
    return signatures


def _expected_unique_constraints(table) -> set[tuple]:
    return {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _expected_indexes(table) -> set[tuple]:
    return {
        (index.name, tuple(column.name for column in index.columns), bool(index.unique))
        for index in table.indexes
    }


def _normalize_sql_expression(value) -> str | None:
    """Normalize harmless PostgreSQL rendering differences, not expression meaning."""
    if value is None:
        return None
    source = str(value).strip()
    compact: list[str] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char in {"'", '"'}:
            # Preserve quoted literals/identifiers exactly, including their spaces.
            quote = char
            start = index
            index += 1
            while index < len(source):
                if source[index] == quote:
                    if index + 1 < len(source) and source[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            compact.append(source[start:index])
            continue
        if char.isspace():
            index += 1
            continue
        # pg_get_expr sometimes includes this implicit string cast. Do not drop
        # numeric, date, or other casts because they can affect meaning.
        cast_match = re.match(
            r"::(?:pg_catalog\.)?(?:character varying|varchar)\b",
            source[index:],
            flags=re.IGNORECASE,
        )
        if cast_match:
            index += cast_match.end()
            continue
        compact.append(char.lower())
        index += 1
    expression = "".join(compact)
    while expression.startswith("(") and expression.endswith(")"):
        depth = 0
        wraps_all = True
        for index, char in enumerate(expression):
            depth += char == "("
            depth -= char == ")"
            if depth == 0 and index != len(expression) - 1:
                wraps_all = False
                break
        if not wraps_all:
            break
        expression = expression[1:-1]
    return expression


def _expected_checks(table) -> set[tuple[str | None, str]]:
    from sqlalchemy import CheckConstraint

    return {
        (constraint.name, _normalize_sql_expression(constraint.sqltext))
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _postgres_column_details(connection: Connection, table_names: set[str]):
    """Return catalog-backed defaults, identity, and collation data; errors fail closed."""
    rows = connection.execute(
        text(
            "SELECT ns.nspname AS table_schema, tbl.relname AS table_name, "
            "att.attname AS column_name, pg_get_expr(def.adbin, def.adrelid) AS server_default, "
            "att.attidentity AS identity_kind, coll.collname AS collation_name, "
            "(att.attcollation = typ.typcollation) AS uses_type_default_collation "
            "FROM pg_attribute att "
            "JOIN pg_class tbl ON tbl.oid = att.attrelid "
            "JOIN pg_namespace ns ON ns.oid = tbl.relnamespace "
            "JOIN pg_type typ ON typ.oid = att.atttypid "
            "LEFT JOIN pg_attrdef def ON def.adrelid = tbl.oid AND def.adnum = att.attnum "
            "LEFT JOIN pg_collation coll ON coll.oid = att.attcollation "
            "WHERE tbl.relkind IN ('r', 'p') AND att.attnum > 0 AND NOT att.attisdropped "
            "AND ns.nspname = current_schema()"
        )
    ).mappings().all()
    return {
        (row["table_name"], row["column_name"]): row
        for row in rows
        if row["table_name"] in table_names
    }


def _check_postgresql_sequences(connection: Connection, inspector, mismatches: list[str]) -> dict:
    """Verify owned integer PK sequences and ensure their next value clears existing IDs."""
    preparer = connection.dialect.identifier_preparer
    details: dict[tuple[str, str], dict] = {}
    for table_name, table in LEGACY_METADATA.tables.items():
        for column in table.primary_key.columns:
            if not isinstance(column.type, Integer):
                continue
            try:
                sequence_name = connection.exec_driver_sql(
                    "SELECT pg_get_serial_sequence(%s, %s)",
                    (table_name, column.name),
                ).scalar_one_or_none()
            except SQLAlchemyError as exc:
                mismatches.append(
                    f"sequence {table_name}.{column.name}: ownership inspection failed ({type(exc).__name__})"
                )
                continue
            if not sequence_name:
                mismatches.append(
                    f"sequence {table_name}.{column.name}: expected an owned PostgreSQL identity/serial sequence, none found"
                )
                continue

            parts = sequence_name.split(".")
            if len(parts) == 1:
                qualified = preparer.quote(parts[0])
                sequence_schema, sequence_relname = "public", parts[0]
            elif len(parts) == 2:
                sequence_schema, sequence_relname = parts
                qualified = f"{preparer.quote(sequence_schema)}.{preparer.quote(sequence_relname)}"
            else:
                mismatches.append(f"sequence {table_name}.{column.name}: unsupported sequence name {sequence_name!r}")
                continue

            try:
                sequence = connection.execute(
                    text(
                        "SELECT seq.seqincrement, seq.seqmin, seq.seqmax, seq.seqstart, "
                        "seq.seqcache, seq.seqcycle, ns.nspname AS sequence_schema, "
                        "rel.relname AS sequence_name, owner_ns.nspname AS owner_schema, "
                        "owner.relname AS owner_table, owner_att.attname AS owner_column, "
                        "owner_att.attidentity AS identity_kind "
                        "FROM pg_class rel JOIN pg_namespace ns ON ns.oid = rel.relnamespace "
                        "JOIN pg_sequence seq ON seq.seqrelid = rel.oid "
                        "LEFT JOIN pg_depend dep ON dep.objid = rel.oid AND dep.deptype IN ('a', 'i') "
                        "LEFT JOIN pg_class owner ON owner.oid = dep.refobjid "
                        "LEFT JOIN pg_namespace owner_ns ON owner_ns.oid = owner.relnamespace "
                        "LEFT JOIN pg_attribute owner_att ON owner_att.attrelid = owner.oid AND owner_att.attnum = dep.refobjsubid "
                        "WHERE ns.nspname = :schema AND rel.relname = :name"
                    ),
                    {"schema": sequence_schema, "name": sequence_relname},
                ).mappings().one_or_none()
                if sequence is None:
                    mismatches.append(f"sequence {table_name}.{column.name}: catalog entry {sequence_name!r} is missing")
                    continue
                if (sequence["owner_table"], sequence["owner_column"]) != (table_name, column.name):
                    mismatches.append(
                        f"sequence {table_name}.{column.name}: {sequence_name!r} is not owned by that primary-key column"
                    )
                    continue
                if sequence.get("identity_kind"):
                    mismatches.append(
                        f"sequence {table_name}.{column.name}: identity columns are not part of the legacy SERIAL baseline"
                    )
                expected_config = (1, 1, 2_147_483_647, 1, 1, False)
                actual_config = (
                    sequence["seqincrement"], sequence["seqmin"], sequence["seqmax"],
                    sequence["seqstart"], sequence["seqcache"], sequence["seqcycle"],
                )
                if actual_config != expected_config:
                    mismatches.append(
                        f"sequence {table_name}.{column.name} configuration: expected increment/min/max/start/cache/cycle "
                        f"{expected_config}, got {actual_config}"
                    )
                state = connection.exec_driver_sql(
                    f"SELECT last_value, is_called FROM {qualified}"
                ).one()
                max_id = connection.exec_driver_sql(
                    f"SELECT MAX({preparer.quote(column.name)}) FROM {preparer.quote(table_name)}"
                ).scalar_one_or_none()
                next_value = state[0] + actual_config[0] if state[1] else state[0]
                if max_id is not None and next_value <= max_id:
                    mismatches.append(
                        f"sequence {table_name}.{column.name} state: next value {next_value} could collide "
                        f"with existing maximum ID {max_id}; sequence was not changed"
                    )
                details[(table_name, column.name)] = {
                    "sequence_name": sequence_name,
                    "sequence_relname": sequence_relname,
                }
            except SQLAlchemyError as exc:
                mismatches.append(
                    f"sequence {table_name}.{column.name}: configuration/state inspection failed ({type(exc).__name__})"
                )
    return details


def _compare(connection: Connection, *, allow_alembic_version: bool = False) -> SchemaParityReport:
    mismatches: list[str] = []
    try:
        inspector = inspect(connection)
        actual_tables = set(inspector.get_table_names())
    except Exception as exc:
        return SchemaParityReport((f"schema inspection failed ({type(exc).__name__}); parity cannot be established",))
    expected_tables = set(LEGACY_METADATA.tables)
    if allow_alembic_version:
        actual_tables.discard("alembic_version")

    for name in sorted(expected_tables - actual_tables):
        mismatches.append(f"table {name}: missing")
    for name in sorted(actual_tables - expected_tables):
        mismatches.append(f"table {name}: unexpected")

    pg_columns = {}
    pg_sequences = {}
    if connection.dialect.name == "postgresql":
        try:
            pg_columns = _postgres_column_details(connection, expected_tables & actual_tables)
        except Exception as exc:
            mismatches.append(f"PostgreSQL defaults/identity/collation inspection failed ({type(exc).__name__})")
        try:
            pg_sequences = _check_postgresql_sequences(connection, inspector, mismatches)
        except Exception as exc:
            mismatches.append(f"PostgreSQL sequence inspection failed ({type(exc).__name__})")

    for table_name in sorted(expected_tables & actual_tables):
        expected = LEGACY_METADATA.tables[table_name]
        actual_columns = {
            column["name"]: column for column in inspector.get_columns(table_name)
        }
        expected_columns = {column.name: column for column in expected.columns}

        for name in sorted(expected_columns.keys() - actual_columns.keys()):
            mismatches.append(f"column {table_name}.{name}: missing")
        for name in sorted(actual_columns.keys() - expected_columns.keys()):
            mismatches.append(f"column {table_name}.{name}: unexpected")
        for name in sorted(expected_columns.keys() & actual_columns.keys()):
            expected_column = expected_columns[name]
            actual_column = actual_columns[name]
            expected_type = _type_signature(expected_column.type)
            actual_type = _type_signature(actual_column["type"])
            if expected_type != actual_type:
                mismatches.append(
                    f"column {table_name}.{name} type: expected {expected_type}, got {actual_type}"
                )
            if expected_column.nullable != actual_column["nullable"]:
                mismatches.append(
                    f"column {table_name}.{name} nullability: expected "
                    f"{'nullable' if expected_column.nullable else 'not nullable'}, got "
                    f"{'nullable' if actual_column['nullable'] else 'not nullable'}"
                )
            expected_default = _normalize_sql_expression(
                expected_column.server_default.arg if expected_column.server_default else None
            )
            actual_default = _normalize_sql_expression(actual_column.get("default"))
            if connection.dialect.name == "postgresql":
                catalog = pg_columns.get((table_name, name))
                if catalog is None:
                    mismatches.append(
                        f"column {table_name}.{name}: PostgreSQL default/identity/collation catalog details are unavailable"
                    )
                    catalog = {}
                else:
                    actual_default = _normalize_sql_expression(catalog["server_default"])
                    expected_collation = getattr(expected_column.type, "collation", None)
                    if expected_collation:
                        actual_collation = catalog["collation_name"]
                        if actual_collation != expected_collation:
                            mismatches.append(
                                f"column {table_name}.{name} collation: expected {expected_collation!r}, got {actual_collation!r}"
                            )
                    elif not catalog["uses_type_default_collation"]:
                        mismatches.append(
                            f"column {table_name}.{name} collation: expected the type/database default, got {catalog['collation_name']!r}"
                        )
            serial_pk = (
                connection.dialect.name == "postgresql"
                and (table_name, name) in pg_sequences
            )
            if serial_pk:
                sequence_relname = pg_sequences[(table_name, name)]["sequence_relname"]
                sequence_ref = re.search(r"nextval\('([^']+)'::regclass\)", actual_default or "")
                if not sequence_ref:
                    mismatches.append(
                        f"column {table_name}.{name} server default: expected nextval for owned sequence "
                        f"{sequence_relname!r}, got {actual_default!r}"
                    )
                else:
                    referenced_name = sequence_ref.group(1).split(".")[-1].strip('"')
                    if referenced_name != sequence_relname:
                        mismatches.append(
                            f"column {table_name}.{name} server default references {referenced_name!r}, "
                            f"not its owned sequence {sequence_relname!r}"
                        )
            elif expected_default != actual_default:
                mismatches.append(
                    f"column {table_name}.{name} server default: expected {expected_default!r}, got {actual_default!r}"
                )

        expected_pk = tuple(expected.primary_key.columns.keys())
        actual_pk = tuple(inspector.get_pk_constraint(table_name).get("constrained_columns") or ())
        if expected_pk != actual_pk:
            mismatches.append(f"primary key {table_name}: expected {expected_pk}, got {actual_pk}")

        actual_fks = {
            _foreign_key_signature(constraint)
            for constraint in inspector.get_foreign_keys(table_name)
        }
        expected_fks = _expected_foreign_keys(expected)
        for signature in sorted(expected_fks - actual_fks, key=repr):
            mismatches.append(f"foreign key {table_name}: missing {signature}")
        for signature in sorted(actual_fks - expected_fks, key=repr):
            mismatches.append(f"foreign key {table_name}: unexpected {signature}")

        unique_constraints = inspector.get_unique_constraints(table_name)
        unique_constraint_names = {
            constraint.get("name")
            for constraint in unique_constraints
            if constraint.get("name")
        }
        actual_uniques = {
            tuple(constraint.get("column_names") or ())
            for constraint in unique_constraints
        }
        expected_uniques = _expected_unique_constraints(expected)
        for signature in sorted(expected_uniques - actual_uniques, key=repr):
            mismatches.append(f"unique constraint {table_name}: missing {signature}")
        for signature in sorted(actual_uniques - expected_uniques, key=repr):
            mismatches.append(f"unique constraint {table_name}: unexpected {signature}")

        try:
            actual_checks = {
                (constraint.get("name"), _normalize_sql_expression(constraint.get("sqltext")))
                for constraint in inspector.get_check_constraints(table_name)
            }
            expected_checks = _expected_checks(expected)
            for signature in sorted(expected_checks - actual_checks, key=repr):
                mismatches.append(f"check constraint {table_name}: missing {signature}")
            for signature in sorted(actual_checks - expected_checks, key=repr):
                mismatches.append(f"check constraint {table_name}: unexpected {signature}")
        except Exception as exc:
            mismatches.append(
                f"check constraints {table_name}: inspection failed ({type(exc).__name__}); parity cannot be established"
            )

        actual_indexes = {
            (
                index["name"],
                tuple(index.get("column_names") or ()),
                bool(index.get("unique")),
            )
            for index in inspector.get_indexes(table_name)
            if index.get("duplicates_constraint") not in unique_constraint_names
        }
        expected_indexes = _expected_indexes(expected)
        for signature in sorted(expected_indexes - actual_indexes, key=repr):
            mismatches.append(f"index {table_name}: missing {signature}")
        for signature in sorted(actual_indexes - expected_indexes, key=repr):
            mismatches.append(f"index {table_name}: unexpected {signature}")

    return SchemaParityReport(tuple(mismatches))


def verify_legacy_schema(
    database: Engine | Connection, *, allow_alembic_version: bool = False
) -> SchemaParityReport:
    """Read-only comparison of a pre-Alembic database with the revision 0001 schema."""
    try:
        if isinstance(database, Engine):
            with database.connect() as connection:
                return _compare(connection, allow_alembic_version=allow_alembic_version)
        return _compare(database, allow_alembic_version=allow_alembic_version)
    except Exception as exc:
        return SchemaParityReport(
            (f"schema parity inspection failed ({type(exc).__name__}); baseline adoption is unsafe",)
        )


def stamp_verified_legacy_baseline(connection: Connection) -> SchemaParityReport:
    """Stamp 0001 only after authorization and complete read-only schema parity."""
    require_migration_authorization(connection=connection)
    report = verify_legacy_schema(connection)
    if not report.matches:
        raise RuntimeError("Baseline stamp refused. " + report.format())

    config = Config(str(Path(__file__).resolve().parent / "alembic.ini"))
    config.attributes["connection"] = connection
    config.attributes["reconcilepro_verified_legacy_stamp"] = VERIFIED_LEGACY_STAMP_TOKEN
    command.stamp(config, "0001_core_schema")
    return report
