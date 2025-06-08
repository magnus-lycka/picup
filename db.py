import sqlite3
from pathlib import Path


class HashDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS images (
                hash TEXT PRIMARY KEY,
                rel_path TEXT NOT NULL
            )
        """
        )
        self.conn.commit()

    def get(self, hash_val: str) -> str | None:
        cur = self.conn.cursor()
        cur.execute("SELECT rel_path FROM images WHERE hash = ?", (hash_val,))
        row = cur.fetchone()
        return row[0] if row else None

    def add(self, hash_val: str, rel_path: str):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO images (hash, rel_path) VALUES (?, ?)",
            (hash_val, rel_path),
        )
        self.conn.commit()

    def all(self):
        cur = self.conn.cursor()
        cur.execute("SELECT hash, rel_path FROM images")
        return dict(cur.fetchall())
