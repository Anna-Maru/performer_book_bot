import csv
import sqlite3
from pathlib import Path

DB_PATH = Path("data/performers.sqlite3")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS performers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT,
            specialty TEXT,
            willing_to_work INTEGER NOT NULL DEFAULT 0,
            has_tools INTEGER NOT NULL DEFAULT 0,
            has_car INTEGER NOT NULL DEFAULT 0,
            comment TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS discipline_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            performer_id INTEGER NOT NULL UNIQUE,
            score INTEGER NOT NULL CHECK(score IN (0,1)),
            author_telegram_id INTEGER NOT NULL,
            author_name TEXT NOT NULL,
            rated_at TEXT NOT NULL,
            FOREIGN KEY(performer_id) REFERENCES performers(id) ON DELETE CASCADE
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_performers_name ON performers(full_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_performers_phone ON performers(phone)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_performers_specialty ON performers(specialty)")

def rowdict(row):
    return dict(row) if row else None

def search_performers(query, limit=10, offset=0, specialty_only=False):
    q = f"%{query.strip()}%"
    with connect() as conn:
        if specialty_only:
            rows = conn.execute(
                "SELECT * FROM performers WHERE specialty LIKE ? COLLATE NOCASE ORDER BY full_name LIMIT ? OFFSET ?",
                (q, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM performers
                   WHERE full_name LIKE ? COLLATE NOCASE
                      OR phone LIKE ?
                      OR specialty LIKE ? COLLATE NOCASE
                   ORDER BY full_name LIMIT ? OFFSET ?""",
                (q, q, q, limit, offset)
            ).fetchall()
    return [dict(r) for r in rows]

def list_performers(limit=10, offset=0):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM performers ORDER BY full_name LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]

def count_performers(query=None, specialty_only=False):
    with connect() as conn:
        if query is None:
            return conn.execute("SELECT COUNT(*) FROM performers").fetchone()[0]
        q = f"%{query.strip()}%"
        if specialty_only:
            sql = "SELECT COUNT(*) FROM performers WHERE specialty LIKE ? COLLATE NOCASE"
            params = (q,)
        else:
            sql = """SELECT COUNT(*) FROM performers
                     WHERE full_name LIKE ? COLLATE NOCASE OR phone LIKE ? OR specialty LIKE ? COLLATE NOCASE"""
            params = (q, q, q)
        return conn.execute(sql, params).fetchone()[0]

def get_performer(performer_id):
    with connect() as conn:
        return rowdict(conn.execute("SELECT * FROM performers WHERE id=?", (performer_id,)).fetchone())

def get_discipline_rating(performer_id):
    with connect() as conn:
        return rowdict(conn.execute(
            "SELECT * FROM discipline_ratings WHERE performer_id=?", (performer_id,)
        ).fetchone())

def set_discipline_rating(performer_id, score, author_id, author_name, rated_at):
    with connect() as conn:
        conn.execute("""
            INSERT INTO discipline_ratings
              (performer_id, score, author_telegram_id, author_name, rated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(performer_id) DO UPDATE SET
              score=excluded.score,
              author_telegram_id=excluded.author_telegram_id,
              author_name=excluded.author_name,
              rated_at=excluded.rated_at
        """, (performer_id, score, author_id, author_name, rated_at))

def import_csv(path):
    """Импорт строк с заголовками: full_name, phone, specialty, willing_to_work, has_tools, has_car, comment.
Существующие записи автоматически не обновляются; при импорте строки только добавляются.
    """
    path = Path(path)
    if not path.exists():
        return 0
    inserted = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        with connect() as conn:
            for row in reader:
                full_name = (row.get("full_name") or row.get("ФИО") or "").strip()
                if not full_name:
                    continue
                conn.execute("""
                    INSERT INTO performers
                    (full_name, phone, specialty, willing_to_work, has_tools, has_car, comment)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    full_name,
                    (row.get("phone") or row.get("Телефон") or "").strip(),
                    (row.get("specialty") or row.get("Специальность") or "").strip(),
                    int((row.get("willing_to_work") or "0").strip() in {"1", "да", "Да", "yes", "true"}),
                    int((row.get("has_tools") or "0").strip() in {"1", "да", "Да", "yes", "true"}),
                    int((row.get("has_car") or "0").strip() in {"1", "да", "Да", "yes", "true"}),
                    (row.get("comment") or row.get("Комментарий") or "").strip()
                ))
                inserted += 1
    return inserted
