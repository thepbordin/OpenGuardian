import logging
import os
from pathlib import Path
from openguardian.db.client import graph_client

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

async def run_migrations():
    """
    Reads all .cypher files in the migrations directory in lexicographical order
    and executes them. Uses IF NOT EXISTS guards for idempotency.
    """
    logger.info("Starting schema migrations check...")
    
    if not MIGRATIONS_DIR.exists():
        logger.warning(f"Migrations directory not found at {MIGRATIONS_DIR}")
        return

    migration_files = sorted(
        [f for f in MIGRATIONS_DIR.iterdir() if f.is_file() and f.suffix == ".cypher"]
    )

    if not migration_files:
        logger.info("No migration files found.")
        return

    driver = graph_client.get_driver()
    
    async with driver.session() as session:
        for m_file in migration_files:
            logger.info(f"Applying migration: {m_file.name}")
            content = m_file.read_text(encoding="utf-8")
            
            # Execute split statements for constraints and schema updates
            statements = [s.strip() for s in content.split(';') if s.strip()]
            for statement in statements:
                try:
                    await session.run(statement)
                except Exception as e:
                    logger.error(f"Failed to execute statement in {m_file.name}: {e}")
                    raise

    logger.info("Schema migrations completed successfully.")
