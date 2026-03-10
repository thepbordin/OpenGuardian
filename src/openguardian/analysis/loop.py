import asyncio
import logging
from openguardian.analysis.detector import AnomalyDetector
from openguardian.notifications.router import EventRouter

logger = logging.getLogger(__name__)

async def run_analysis_loop(interval_hours: int = 6):
    """
    Background worker loop firing analysis evaluations safely isolated away
    from the web request stack. Designed to be overseen by FastAPI's TaskGroup.
    """
    poll_seconds = interval_hours * 3600
    
    # Fast polling interval for PoC/Demo testing if explicitly set to 0.01 hours
    if interval_hours < 1:
        poll_seconds = interval_hours * 3600
        
    logger.info(f"Starting Background LLM Analysis Loop (every {poll_seconds} seconds)")
    
    try:
        while True:
            await asyncio.sleep(poll_seconds)
            logger.info("Executing scheduled LLM behavior evaluation cycle...")
            # Hardcoded device routing mock for PoC single device architecture
            result = await AnomalyDetector.run_analysis_cycle("pihole-network-router-1")
            EventRouter.dispatch_analysis_results(result)
            
    except asyncio.CancelledError:
        logger.info("LLM Analysis loop cancelled cleanly.")
    except Exception as e:
        logger.critical(f"Critical failure shutting down analysis pipeline: {e}")
        raise
