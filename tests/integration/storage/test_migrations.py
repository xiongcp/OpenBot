import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from openbot.storage.migrate import Migration, MigrationError, connect, load_migrations, migrate

ROOT = Path(__file__).resolve().parents[3]


def test_fresh_profile_has_23_tables_and_effective_pragmas(tmp_path):
    path = tmp_path / "state.sqlite"
    report = migrate(path, load_migrations(ROOT / "db/migrations"))
    assert report.version == 2
    with connect(path) as db:
        tables = db.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        assert len(tables) == 23
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert migrate(path, load_migrations(ROOT / "db/migrations")).version == 2


def test_upgrade_preserves_old_version_and_creates_verified_backup(tmp_path):
    path = tmp_path / "state.sqlite"
    baseline = load_migrations(ROOT / "db/migrations")
    migrate(path, baseline[:1])
    report = migrate(path, baseline)
    assert report.version == 2
    assert report.backup_path.is_file()
    with sqlite3.connect(report.backup_path) as db:
        assert db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 1
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_interrupted_migration_rolls_back_ddl_and_checksum(tmp_path):
    path = tmp_path / "state.sqlite"
    migrations = load_migrations(ROOT / "db/migrations")
    migrate(path, migrations)
    broken = Migration(
        3, "fixture_failed", "CREATE TABLE should_rollback(x TEXT);\nSELECT missing;"
    )
    with pytest.raises(MigrationError):
        migrate(path, migrations + [broken])
    with connect(path) as db:
        assert not db.execute("SELECT 1 FROM sqlite_schema WHERE name='should_rollback'").fetchone()
        assert db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 2
    assert migrate(path, migrations).version == 2


@pytest.mark.parametrize("bad", ["checksum", "future", "gap", "legacy"])
def test_unrecognized_or_modified_history_is_rejected(tmp_path, bad):
    path = tmp_path / "state.sqlite"
    migrations = load_migrations(ROOT / "db/migrations")
    if bad == "legacy":
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE legacy_tasks(id TEXT)")
    elif bad == "gap":
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE schema_migrations("
                "version INTEGER,name TEXT,checksum TEXT,applied_at INTEGER)"
            )
            db.execute("INSERT INTO schema_migrations VALUES(3,'unknown',?,0)", ("b" * 64,))
    else:
        migrate(path, migrations)
        if bad == "checksum":
            migrations = [Migration(1, "baseline", migrations[0].sql + "\n-- changed artifact\n")]
        elif bad == "future":
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO schema_migrations VALUES(3,'unknown',?,0)", ("b" * 64,))
    before = path.read_bytes()
    with pytest.raises(MigrationError):
        migrate(path, migrations)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "sql",
    [
        "COMMIT;",
        "PRAGMA foreign_keys=OFF;",
        "PRAGMA quick_check=operations;",
        "ATTACH ':memory:' AS evil;",
    ],
)
def test_migration_cannot_escape_runner_transaction(tmp_path, sql):
    path = tmp_path / "state.sqlite"
    migrations = load_migrations(ROOT / "db/migrations")
    migrate(path, migrations)
    with pytest.raises(MigrationError):
        migrate(path, migrations + [Migration(3, "invalid_control", sql)])
    with connect(path) as db:
        assert db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 2


def test_read_connection_cannot_write_and_corrupt_database_is_not_replaced(tmp_path):
    path = tmp_path / "state.sqlite"
    migrations = load_migrations(ROOT / "db/migrations")
    migrate(path, migrations)
    with connect(path, readonly=True) as db, pytest.raises(sqlite3.OperationalError):
        db.execute("CREATE TABLE forbidden(id TEXT)")
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"not a database")
    with pytest.raises(MigrationError):
        migrate(corrupt, migrations)
    assert corrupt.read_bytes() == b"not a database"


def test_noop_startup_rejects_foreign_key_corruption(tmp_path):
    path = tmp_path / "state.sqlite"
    migrations = load_migrations(ROOT / "db/migrations") + [
        Migration(
            3,
            "foreign_key_fixture",
            "CREATE TABLE parent(id INTEGER PRIMARY KEY);\n"
            "CREATE TABLE child(parent_id INTEGER REFERENCES parent(id));",
        )
    ]
    migrate(path, migrations)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("INSERT INTO child VALUES(42)")
    with pytest.raises(MigrationError):
        migrate(path, migrations)


def test_process_exit_after_ddl_does_not_leave_half_migration(tmp_path):
    path = tmp_path / "state.sqlite"
    migrations = load_migrations(ROOT / "db/migrations")
    migrate(path, migrations)
    code = """
import os,sqlite3,sys
from pathlib import Path
from openbot.storage.migrate import Migration,load_migrations,migrate
original=sqlite3.connect
class Crash(sqlite3.Connection):
    def execute(self, sql, *args):
        result=super().execute(sql,*args)
        if sql.startswith("CREATE TABLE crash_fixture"):
            os._exit(78)
        return result
def connect(*args,**kwargs):
    kwargs["factory"]=Crash
    return original(*args,**kwargs)
sqlite3.connect=connect
migrate(Path(sys.argv[1]), load_migrations(Path(sys.argv[2])) + [
    Migration(3,"crash_fixture","CREATE TABLE crash_fixture(value TEXT);")])
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), str(ROOT / "db/migrations")],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 78, result.stderr
    assert migrate(path, migrations).version == 2
    db = connect(path)
    try:
        assert (
            db.execute("SELECT name FROM sqlite_schema WHERE name='crash_fixture'").fetchone()
            is None
        )
    finally:
        db.close()
