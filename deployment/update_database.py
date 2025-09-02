#!/usr/bin/env python3
"""
Database updater for MLflow Auth plugin
- Creates tables if missing (via SQLAlchemy Base.metadata.create_all)
- Adds missing columns:
    * logout_time (on login_history)
    * password_change_required (on users table)
- Safe for repeated runs (idempotent)
- Auto-detects actual table names (user/users/mlflow_users and login_history)
"""

import shutil
import sqlite3
import sys
from pathlib import Path

# Make plugin importable
sys.path.insert(0, str(Path(__file__).parent.parent / "mlflow-auth-plugin"))

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import inspect as sa_inspect
from mlflow_auth.auth.models import Base, User, LoginHistory  # noqa: F401


def backup_sqlite_file(db_file: Path) -> Path:
    """Create a .bak backup next to the DB (overwritten at each run)."""
    backup = db_file.with_suffix(db_file.suffix + ".bak")
    try:
        if db_file.exists():
            shutil.copy2(db_file, backup)
            print(f"🧯 Backup created: {backup.name}")
        else:
            print("ℹ️ DB file does not exist yet, no backup needed.")
    except Exception as e:
        print(f"⚠️ Backup failed: {e}")
    return backup


def get_table_names(engine: Engine) -> set:
    """Return lowercased set of existing table names."""
    insp = sa_inspect(engine)
    return {t.lower() for t in insp.get_table_names()}


def get_columns_sqlite(conn: sqlite3.Connection, table_name: str) -> dict:
    """Return {column_name_lower: row} from PRAGMA table_info()."""
    cur = conn.execute(f'PRAGMA table_info("{table_name}")')
    cols = {}
    for row in cur.fetchall():
        cols[row[1].lower()] = row
    return cols


def add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, col_type_sql: str,
                          default_sql: str | None = None, set_default_after: bool = False):
    """
    Add a column to a SQLite table if it's missing.

    SQLite notes:
    - ALTER TABLE ADD COLUMN is limited; keep columns NULLable.
    - DEFAULT in DDL applies to NEW rows; use set_default_after to backfill.
    """
    cols = get_columns_sqlite(conn, table)
    if col.lower() in cols:
        print(f"✓ Column already present: {table}.{col}")
        return

    ddl = f'ALTER TABLE "{table}" ADD COLUMN "{col}" {col_type_sql}'
    if default_sql is not None:
        ddl += f" DEFAULT {default_sql}"

    print(f"➕ Adding column: {table}.{col} ({col_type_sql})")
    conn.execute(ddl)

    if set_default_after and default_sql is not None:
        print(f"↺ Backfilling {table}.{col} with default {default_sql} for existing rows")
        conn.execute(f'UPDATE "{table}" SET "{col}" = {default_sql} WHERE "{col}" IS NULL')


def detect_user_table(existing_tables: set) -> str | None:
    """Find the users table. Candidates: 'user', 'users', 'mlflow_users'."""
    candidates = ["user", "users", "mlflow_users"]
    for c in candidates:
        if c in existing_tables:
            return c
    userish = [t for t in existing_tables if "user" in t]
    return userish[0] if len(userish) == 1 else None


def detect_history_table(existing_tables: set) -> str | None:
    """Find the login history table. Candidate: 'login_history'."""
    candidates = ["login_history", "logins_history", "auth_login_history"]
    for c in candidates:
        if c in existing_tables:
            return c
    hist = [t for t in existing_tables if "history" in t and "login" in t]
    return hist[0] if len(hist) == 1 else None


def update_database():
    """Create/upgrade database schema safely and idempotently."""
    base_dir = Path(__file__).parent
    db_path = base_dir / "data" / "mlflow_auth.db"

    print("🔧 MLflow Auth DB update")
    print("=" * 50)
    print(f"📍 DB path: {db_path}")

    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup current DB file
    backup_sqlite_file(db_path)

    # Create engine and ensure base tables exist
    engine = create_engine(f"sqlite:///{db_path}")
    print("🔄 Ensuring tables exist (SQLAlchemy metadata.create_all)...")
    Base.metadata.create_all(engine)
    print("✓ create_all done")

    # Introspect tables
    tables = get_table_names(engine)
    print(f"🧭 Existing tables: {', '.join(sorted(tables)) or '(none)'}")

    # Detect actual table names
    user_table = detect_user_table(tables)
    hist_table = detect_history_table(tables)

    if not user_table:
        print("⚠️ Could not detect users table automatically. Skipping user columns.")
    else:
        print(f"👤 Users table detected: {user_table}")

    if not hist_table:
        print("⚠️ Could not detect login history table automatically. Skipping history columns.")
    else:
        print(f"📝 Login history table detected: {hist_table}")

    # Open raw sqlite3 connection for ALTER/PRAGMA
    need_commit = False
    with sqlite3.connect(db_path) as conn:
        try:
            # Add password_change_required (BOOLEAN) on users table (default 0)
            if user_table:
                add_column_if_missing(
                    conn,
                    table=user_table,
                    col="password_change_required",
                    col_type_sql="BOOLEAN",
                    default_sql="0",
                    set_default_after=True,
                )
                need_commit = True

            # Add logout_time (DATETIME) on login history
            if hist_table:
                add_column_if_missing(
                    conn,
                    table=hist_table,
                    col="logout_time",
                    col_type_sql="DATETIME",
                    default_sql=None,
                    set_default_after=False
                )
                need_commit = True

            if need_commit:
                conn.commit()
                print("✅ Schema update committed")
            else:
                print("ℹ️ Nothing to change (schema already up-to-date)")

        except Exception as e:
            conn.rollback()
            print(f"❌ Error while updating schema: {e}")
            print("⏪ Changes rolled back. Restore the .bak file if needed.")
            raise

    # Final summary
    with sqlite3.connect(db_path) as conn:
        if user_table:
            cols_u = get_columns_sqlite(conn, user_table)
            print(f"📋 Columns in {user_table}: {', '.join(cols_u.keys())}")
        if hist_table:
            cols_h = get_columns_sqlite(conn, hist_table)
            print(f"📋 Columns in {hist_table}: {', '.join(cols_h.keys())}")

    print("🎉 Database update finished.")


def main():
    print("🔧 Updating MLflow Auth database")
    print("=" * 50)
    try:
        update_database()
    except Exception as e:
        print(f"❌ Update failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
