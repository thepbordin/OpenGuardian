import asyncio
import logging
from typing import List
from openguardian.models.graph_event import GraphEvent
from openguardian.graph.sessions import build_sessions
from openguardian.db.repository import GraphRepository
from openguardian.connectors.protocol import ConnectorProtocol

logger = logging.getLogger(__name__)

async def run_ingestion_loop(connector: ConnectorProtocol, poll_interval: int = 60):
    """
    Continuous background loop tying telemetry fetching, categorization, sessioning,
    and database appending together organically.

    Should be supervised by a FastAPI `TaskGroup`.
    """
    logger.info(f"Starting ingestion loop for connector '{connector.connector_id}' "
                f"with interval {poll_interval}s.")
    
    await connector.start()
    
    try:
        while True:
            events_buffer: List[GraphEvent] = []
            
            # 1. Fetch
            try:
                async for event in connector.poll():
                    events_buffer.append(event)
            except Exception as e:
                logger.error(f"Poll iteration failed for '{connector.connector_id}': {e}")
            
            # 2. Sessionize & Persist
            if events_buffer:
                logger.info(f"Ingested {len(events_buffer)} new events from '{connector.connector_id}'.")
                
                # Default 30 min window hardcoded for PoC
                sessions = build_sessions(events_buffer, window_minutes=30)
                
                if sessions:
                    await GraphRepository.batch_ingest_sessions(sessions)
            
            # 3. Sleep
            await asyncio.sleep(poll_interval)
            
    except asyncio.CancelledError:
        logger.info(f"Ingestion loop for '{connector.connector_id}' cancelled cleanly.")
    except Exception as e:
        logger.critical(f"Critical failure in ingestion loop: {e}", exc_info=True)
        raise
    finally:
        await connector.stop()
