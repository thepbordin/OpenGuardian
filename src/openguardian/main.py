import asyncio
import logging
from openguardian.db.client import graph_client
from openguardian.db.migrations import run_migrations

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("openguardian.main")

async def init_infrastructure():
    logger.info("Initializing OpenGuardian infrastructure...")
    is_connected = await graph_client.verify_connectivity()
    if is_connected:
        await run_migrations()
    else:
        logger.error("Could not connect to Neo4j. Ensure docker compose is running.")
        
    await graph_client.close()

if __name__ == "__main__":
    asyncio.run(init_infrastructure())
