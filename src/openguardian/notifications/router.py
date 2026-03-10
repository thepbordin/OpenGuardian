import logging
from typing import List
from openguardian.analysis.detector import AnalysisResult, AnomalyFlag
from openguardian.notifications.email import email_notifier

logger = logging.getLogger(__name__)

class EventRouter:
    """
    Evaluates LLM output severities and routes them to appropriate async 
    delivery channels or batches them for periodic digests.
    """
    
    # Internal mock queue for digest batching in PoC. 
    # Production dictates pushing this into Redis or Neo4j temporal layers.
    _digest_queue: List[AnomalyFlag] = []
    
    @classmethod
    def dispatch_analysis_results(cls, result: AnalysisResult):
        if not result.flags:
            logger.info("No actionable flags generated during this cycle. System Nominal.")
            return
            
        logger.info(f"Routing {len(result.flags)} behavioral flags...")
        
        for flag in result.flags:
            if flag.severity == "critical":
                # F6.1 immediate warning relay
                logger.warning(f"Immediate Critical relay triggered: {flag.category}")
                email_notifier.send_critical_alert(flag)
            else:
                # F6.3 periodic digest batching
                logger.debug(f"Queuing lower severity flag for periodic digest: {flag.category}")
                cls._digest_queue.append(flag)
                
    @classmethod
    def flush_weekly_digest(cls):
        """
        Transmits the bundled lower severity queues as a single read.
        Empty queue states transmit nothing to prevent fatigue.
        """
        if not cls._digest_queue:
            return
            
        logger.info(f"Flushing {len(cls._digest_queue)} queued events via Weekly Digest protocol.")
        email_notifier.send_weekly_digest(cls._digest_queue)
        
        # Reset queue state post-delivery
        cls._digest_queue.clear()
