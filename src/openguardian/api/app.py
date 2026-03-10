import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from openguardian.db.client import graph_client
from openguardian.db.migrations import run_migrations
from openguardian.connectors.registry import registry
from openguardian.api.routers import health, behavior, anomalies, connectors, onboarding, risk_files
from openguardian.ingestion.loop import run_ingestion_loop
from openguardian.analysis.loop import run_analysis_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openguardian.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages long-running system resources and background tasks robustly
    using asyncio.TaskGroup. If one task fails, they all tear down cleanly.
    """
    logger.info("Initializing OpenGuardian application lifecycle...")

    # Ensure Neo4j Database is active and migrate
    is_connected = await graph_client.verify_connectivity()
    if is_connected:
        await run_migrations()
    else:
        logger.error("Failed database connectivity check. Graceful degradation triggered.")
    
    app.state.driver = graph_client.get_driver()
    
    # Init Plugins
    registry.discover()
    app.state.registry = registry
    
    # Launch concurrent background processes
    try:
        async with asyncio.TaskGroup() as tg:
            # 1. Start network ingestion loops per active connector
            for _name, connector in registry.list_connectors().items():
                tg.create_task(run_ingestion_loop(connector, poll_interval=60))
                
            # 2. Start ML orchestrator pulling baseline data
            tg.create_task(run_analysis_loop(interval_hours=2))
                
            # Yield control back to FastAPI to serve REST requests
            yield
            
    except Exception as e:
        logger.error(f"TaskGroup exception triggered application shutdown: {e}")
        raise
    finally:
        # Tear down dependencies
        await graph_client.close()
        logger.info("Application lifecycle safely terminated.")

def create_app() -> FastAPI:
    app = FastAPI(
        title="OpenGuardian API",
        version="0.1.0",
        description="Local network behavior monitoring and LLM proxy.",
        lifespan=lifespan
    )
    
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(behavior.router, prefix="/api/v1")
    app.include_router(anomalies.router, prefix="/api/v1")
    app.include_router(connectors.router, prefix="/api/v1")
    app.include_router(onboarding.router, prefix="/api/v1")
    app.include_router(risk_files.router, prefix="/api/v1")
    return app

app = create_app()
