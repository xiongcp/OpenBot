"""Checksum-locked ordered migrations, without implicit transaction commits."""

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class MigrationReport:
    version: int
    backup_path: Path | None


def load_migrations(directory: Path) -> list[Migration]:
    entries = json.loads((directory / "manifest.json").read_text())["migrations"]
    result = []
    for entry in entries:
        name = entry["file"]
        if Path(name).name != name:
            raise MigrationError("Migration file must be local")
        sql = (directory / name).read_text()
        migration = Migration(entry["version"], entry["name"], sql)
        if migration.checksum != entry["sha256"]:
            raise MigrationError("Migration artifact checksum mismatch")
        result.append(migration)
    return result


def connect(
    path: Path, *, readonly: bool = False, busy_timeout_ms: int = 250
) -> sqlite3.Connection:
    if path.is_symlink() or not 0 <= busy_timeout_ms <= 250:
        raise MigrationError("Invalid database path or lock timeout")
    if readonly:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, isolation_level=None)
    else:
        db = sqlite3.connect(path, isolation_level=None)
    try:
        db.execute(f"PRAGMA busy_timeout={busy_timeout_ms:d}")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA recursive_triggers=ON")
        if not readonly:
            db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        expected = {
            "journal_mode": "wal",
            "synchronous": 2,
            "foreign_keys": 1,
            "recursive_triggers": 1,
        }
        for pragma, value in expected.items():
            if db.execute("PRAGMA " + pragma).fetchone()[0] != value:
                raise MigrationError("SQLite connection durability guard failed")
        if (
            sqlite3.sqlite_version_info < (3, 38, 0)
            or db.execute("SELECT json_valid('{}')").fetchone()[0] != 1
        ):
            raise MigrationError("SQLite JSON/STRICT capabilities unavailable")
        if readonly:
            db.execute("PRAGMA query_only=ON")
        return db
    except BaseException:
        db.close()
        raise


def _history(db: sqlite3.Connection, migrations: list[Migration]) -> int:
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    if "schema_migrations" not in tables:
        if tables:
            raise MigrationError("Unversioned database requires an explicit migration")
        return 0
    rows = list(db.execute("SELECT version,name,checksum FROM schema_migrations ORDER BY version"))
    if len(rows) > len(migrations) or [r[0] for r in rows] != list(range(1, len(rows) + 1)):
        raise MigrationError("Unknown or discontinuous schema history")
    for row, migration in zip(rows, migrations, strict=False):
        if row != (migration.version, migration.name, migration.checksum):
            raise MigrationError("Applied migration checksum/name mismatch")
    return len(rows)


def _statements(sql: str) -> list[str]:
    statements = []
    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            statements.append(pending)
            pending = ""
    if pending.strip():
        raise MigrationError("Incomplete migration statement")
    return statements


def migrate(path: Path, migrations: list[Migration]) -> MigrationReport:
    if [m.version for m in migrations] != list(range(1, len(migrations) + 1)) or not migrations:
        raise MigrationError("Migrations must begin at version 1 without gaps")
    if path.is_symlink():
        raise MigrationError("Symlink database refused")
    backup_path = None
    if path.exists() and path.stat().st_size:
        try:
            source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                applied = _history(source, migrations)
                if applied == len(migrations):
                    if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise MigrationError("Database integrity check failed")
                    if source.execute("PRAGMA foreign_key_check").fetchone() is not None:
                        raise MigrationError("Existing database has invalid foreign keys")
                    # Validate effective connection options, even on no-op startup.
                    checked = connect(path)
                    checked.close()
                    return MigrationReport(applied, None)
                if applied:
                    backup_path = path.with_name(path.name + ".pre-migrate-" + secrets.token_hex(8))
                    fd = os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                    os.close(fd)
                    target = sqlite3.connect(backup_path)
                    try:
                        source.backup(target)
                        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                            raise MigrationError("Migration backup failed integrity check")
                    finally:
                        target.close()
            finally:
                source.close()
        except sqlite3.DatabaseError as exc:
            raise MigrationError("Cannot inspect existing database safely") from exc
    elif not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(fd)
    db = connect(path)
    try:
        db.execute("BEGIN IMMEDIATE")
        applied = _history(db, migrations)
        for migration in migrations[applied:]:
            forbidden = {
                sqlite3.SQLITE_TRANSACTION,
                sqlite3.SQLITE_SAVEPOINT,
                sqlite3.SQLITE_ATTACH,
                sqlite3.SQLITE_DETACH,
                sqlite3.SQLITE_PRAGMA,
            }
            try:
                for statement in _statements(migration.sql):
                    sql = re.sub(r"(?m)^\s*--[^\n]*$", "", statement).strip()
                    add_column = re.match(
                        r"(?i)^ALTER\s+TABLE\s+([a-z_][a-z0-9_]*)\s+ADD\s+COLUMN\s", sql
                    )
                    table = add_column.group(1) if add_column else None

                    def authorize_sql(
                        action: int,
                        arg1: str | None,
                        arg2: str | None,
                        database: str | None,
                        source: str | None,
                        *,
                        allowed_table: str | None = table,
                        blocked: set[int] = forbidden,
                    ) -> int:
                        if (
                            action == sqlite3.SQLITE_PRAGMA
                            and allowed_table is not None
                            and (arg1, arg2, database) == ("quick_check", allowed_table, "main")
                        ):
                            return sqlite3.SQLITE_OK
                        return sqlite3.SQLITE_DENY if action in blocked else sqlite3.SQLITE_OK

                    db.set_authorizer(authorize_sql)
                    db.execute(statement)
            finally:
                db.set_authorizer(None)
            db.execute(
                "INSERT INTO schema_migrations VALUES(?,?,?,?)",
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    time.time_ns() // 1_000_000,
                ),
            )
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise MigrationError("Migration produced invalid foreign keys")
        db.execute("COMMIT")
        return MigrationReport(len(migrations), backup_path)
    except BaseException as exc:
        if db.in_transaction:
            db.execute("ROLLBACK")
        if isinstance(exc, sqlite3.DatabaseError):
            raise MigrationError("Migration failed; transaction rolled back") from exc
        raise
    finally:
        db.close()
