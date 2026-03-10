import logging
from pydantic import BaseModel
from openguardian.db.client import graph_client

logger = logging.getLogger(__name__)

class BaselineSummary(BaseModel):
    narrative: str

class CurrentWindowSummary(BaseModel):
    narrative: str
    active_categories: list[str]

class GraphSummarizer:
    """
    Translates raw Knowledge Graph aggregates into structured natural language metrics.
    Ensures LLM prompts see behavior stories NOT explicit domains.
    """
    
    @staticmethod
    async def get_current_window_summary(device_id: str, hours: int = 24) -> CurrentWindowSummary:
        """
        Executes a Cypher aggregate compiling activity distributions sequentially over $hours.
        Translates numbers to English baseline references.
        """
        cypher = """
        MATCH (d:Device {id: $device_id})-[v:ACCESSED]->(a:Activity)
        WHERE v.start_time >= datetime() - duration({hours: $hours})
        
        WITH a.name AS category, 
             sum(v.duration_minutes) as category_duration, 
             sum(v.count) as total_events
             
        RETURN category, category_duration, total_events
        ORDER BY category_duration DESC
        """
        driver = graph_client.get_driver()
        narrative_parts = []
        categories = []
        
        try:
            async with driver.session() as session:
                result = await session.run(cypher, device_id=device_id, hours=hours)
                records = await result.data()
                
                if not records:
                    return CurrentWindowSummary(
                        narrative="No network activity recorded in the specified analysis window.",
                        active_categories=[]
                    )
                    
                total_duration = sum(rec["category_duration"] for rec in records)
                narrative_parts.append(f"In the last {hours} hours, the device was active for an estimated {total_duration:.1f} minutes.")
                
                for r in records:
                    cat = r["category"]
                    categories.append(cat)
                    mins = r["category_duration"]
                    evts = r["total_events"]
                    narrative_parts.append(f"- Category '{cat}': {evts} connections totaling {mins:.1f} minutes.")
                    
            return CurrentWindowSummary(
                narrative="\n".join(narrative_parts),
                active_categories=categories
            )
            
        except Exception as e:
            logger.error(f"Summarizer aggregate failure: {e}")
            return CurrentWindowSummary(narrative="Error analyzing current window.", active_categories=[])
            
    @staticmethod
    async def get_baseline_summary(device_id: str) -> BaselineSummary:
        """
        Mock for PoC: Pulls the 7-day initial onboarding baseline recorded internally.
        """
        return BaselineSummary(narrative="Baseline established: Standard school hours show 'education' usage. 'gaming' dominates 18:00 - 21:00.")
