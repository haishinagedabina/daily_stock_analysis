"""
DB migration: Add five-layer decision columns to screening_candidates.

Run: python scripts/migrate_five_layer_columns.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "stock_analysis.db"

COLUMNS_TO_ADD = [
    ("trade_stage", "VARCHAR(32)"),
    ("setup_type", "VARCHAR(64)"),
    ("entry_maturity", "VARCHAR(16)"),
    ("risk_level", "VARCHAR(16)"),
    ("market_regime", "VARCHAR(32)"),
    ("theme_position", "VARCHAR(32)"),
    ("candidate_pool_level", "VARCHAR(32)"),
    ("trade_plan_json", "TEXT"),
    ("strategy_family", "VARCHAR(32)"),
]


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    existing = {
        row[1] for row in cursor.execute("PRAGMA table_info(screening_candidates)").fetchall()
    }

    added = []
    for col_name, col_type in COLUMNS_TO_ADD:
        if col_name not in existing:
            cursor.execute(
                f"ALTER TABLE screening_candidates ADD COLUMN {col_name} {col_type}"
            )
            added.append(col_name)
            print(f"  Added column: {col_name} ({col_type})")

    if added:
        conn.commit()
        print(f"\nMigration complete: {len(added)} columns added.")
    else:
        print("No migration needed — all columns already exist.")

    conn.close()


if __name__ == "__main__":
    migrate()
