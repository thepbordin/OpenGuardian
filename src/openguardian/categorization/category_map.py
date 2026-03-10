import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "categories.db"

class CategoryMap:
    """
    Lightweight SQLite-backed category mapper. 
    Seeds domains into predefined behavioral categories.
    """
    def __init__(self):
        self._conn = None
        self._init_db()

    def _init_db(self):
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS domain_categories (
                domain TEXT PRIMARY KEY,
                category TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def categorize(self, domain: str) -> str:
        """
        Given a raw domain string, returns its behavioral category.
        Defaults to 'unknown_new' if not mapped, preventing blocking.
        """
        if not self._conn:
            return "unknown_new"
            
        cur = self._conn.cursor()
        cur.execute("SELECT category FROM domain_categories WHERE domain = ?", (domain.lower(),))
        row = cur.fetchone()
        
        if row:
            return row[0]
        return "unknown_new"
    
    def seed_categories(self, mappings: dict[str, str]):
        """
        Seeds categories from a dictionary. Used dynamically or via script.
        """
        if not self._conn:
            return

        cur = self._conn.cursor()
        cur.executemany(
            "INSERT OR REPLACE INTO domain_categories (domain, category) VALUES (?, ?)",
            list(mappings.items())
        )
        self._conn.commit()
        logger.info(f"Seeded {len(mappings)} domains into Categorization map.")
        
category_map = CategoryMap()
