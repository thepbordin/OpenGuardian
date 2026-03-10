from typing import List, Dict
from datetime import datetime
from collections import Counter
from pydantic import BaseModel, Field

from openguardian.models.graph_event import GraphEvent

class Session(BaseModel):
    """
    Represents a condensed window of activity across a timeslot.
    Mapped into Neo4j incrementally.
    """
    device_id: str
    user_id: str
    primary_category: str
    secondary_categories: List[str]
    start_time: datetime
    end_time: datetime
    event_count: int

def build_sessions(events: List[GraphEvent], window_minutes: int = 30) -> List[Session]:
    """
    Groups raw GraphEvents into coherent Sessions based on a time window threshold.
    
    A new session is established if the time gap between chronological events 
    mapping to the same device and user exceeds `window_minutes`.
    """
    if not events:
        return []

    # Requires events to be sorted chronologically for accurate windowing
    sorted_events = sorted(events, key=lambda e: e.timestamp)
    sessions: List[Session] = []
    
    # Internal grouping: (device_id, user_id) -> list of events
    groups: Dict[tuple, List[GraphEvent]] = {}
    
    for event in sorted_events:
        key = (event.device_id or "unknown_device", event.user_id)
        if key not in groups:
            groups[key] = []
        groups[key].append(event)
        
    for (device_id, user_id), user_events in groups.items():
        if not user_events:
            continue
            
        current_session_events = [user_events[0]]
        
        for event in user_events[1:]:
            last_event = current_session_events[-1]
            time_diff = (event.timestamp - last_event.timestamp).total_seconds() / 60.0
            
            if time_diff > window_minutes:
                # Cutoff session, finalize and push
                sessions.append(_finalize_session(device_id, user_id, current_session_events))
                current_session_events = [event]
            else:
                current_session_events.append(event)
                
        if current_session_events:
            sessions.append(_finalize_session(device_id, user_id, current_session_events))
            
    return sessions

def _finalize_session(device_id: str, user_id: str, events: List[GraphEvent]) -> Session:
    start_time = events[0].timestamp
    end_time = events[-1].timestamp
    
    category_counts = Counter(e.category for e in events)
    sorted_cats = [cat for cat, _ in category_counts.most_common()]
    
    primary = sorted_cats[0] if sorted_cats else "unknown_new"
    secondary = sorted_cats[1:] if len(sorted_cats) > 1 else []
    
    return Session(
        device_id=device_id,
        user_id=user_id,
        primary_category=primary,
        secondary_categories=secondary,
        start_time=start_time,
        end_time=end_time,
        event_count=len(events)
    )
