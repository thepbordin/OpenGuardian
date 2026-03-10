import logging
from typing import List, Any
from openguardian.db.client import graph_client
from openguardian.graph.sessions import Session

logger = logging.getLogger(__name__)

class GraphRepository:
    """
    Handles batched queries pushing data into Neo4j incrementally via UNWIND operations.
    """
    
    @staticmethod
    async def batch_ingest_sessions(sessions: List[Session]):
        """
        Takes a list of normalized activity sessions and creates/merges them 
        into the Knowledge Graph structure efficiently.
        """
        if not sessions:
            return
            
        driver = graph_client.get_driver()
        
        # We structure the payload to send via UNWIND
        # Notice we extract start_time properties to tie into the TimeSlot concepts
        payload = []
        for s in sessions:
            # We map temporal slots to a 'YYYY-MM-DD-HH' string representation
            timeslot_id = s.start_time.strftime("%Y-%m-%d-%H")
            
            payload.append({
                "device_id": s.device_id,
                "user_id": s.user_id,
                "category": s.primary_category,
                "timeslot_id": timeslot_id,
                "event_count": s.event_count,
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat(),
                "duration_minutes": (s.end_time - s.start_time).total_seconds() / 60.0
            })
            
        cypher = """
        UNWIND $events AS e
        
        // 1. Ensure Target Entities Exist (Idempotent Merge)
        MERGE (d:Device {id: e.device_id})
        MERGE (u:User {id: e.user_id})
        MERGE (a:Activity {name: e.category})
        MERGE (t:TimeSlot {id: e.timeslot_id})
        
        // Ensure manual/automatic assignments exist
        MERGE (u)-[:OWNS]->(d)
        
        // Temporal mapping
        MERGE (a)-[:OCCURRED_AT]->(t)
        
        // 2. Append Activity Instance Graph Traversal (CREATE Event Log conceptually)
        CREATE (d)-[v:ACCESSED {
            count: toInteger(e.event_count),
            duration_minutes: toFloat(e.duration_minutes),
            start_time: e.start_time,
            end_time: e.end_time
        }]->(a)
        """
        
        try:
            async with driver.session() as session:
                await session.run(cypher, events=payload)
            logger.info(f"Successfully ingested {len(sessions)} batched session nodes.")
        except Exception as e:
            logger.error(f"Failed to run UNWIND batch ingestion: {e}")
