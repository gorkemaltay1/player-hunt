"""Convert JSON athletes database to SQLite for faster lookups."""

import json
import sqlite3
from pathlib import Path

JSON_FILE = Path(__file__).parent / "athletes_db.json"
SQLITE_FILE = Path(__file__).parent / "athletes_db.sqlite"


def convert():
    print("Loading JSON...")
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} athletes")

    # Create SQLite database
    print("Creating SQLite database...")
    if SQLITE_FILE.exists():
        SQLITE_FILE.unlink()

    conn = sqlite3.connect(SQLITE_FILE)
    cursor = conn.cursor()

    # Create table
    cursor.execute("""
        CREATE TABLE athletes (
            key TEXT PRIMARY KEY,
            name TEXT,
            sport TEXT,
            country TEXT
        )
    """)

    # Create index for faster search
    cursor.execute("CREATE INDEX idx_name ON athletes(name)")

    # Insert data
    print("Inserting data...")
    rows = [(key, v["name"], v["sport"], v["country"]) for key, v in data.items()]
    cursor.executemany("INSERT INTO athletes VALUES (?, ?, ?, ?)", rows)

    conn.commit()
    conn.close()

    size_mb = SQLITE_FILE.stat().st_size / 1024 / 1024
    print(f"Done! SQLite file size: {size_mb:.1f} MB")


if __name__ == "__main__":
    convert()
