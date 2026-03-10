from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class GraphEvent(BaseModel):
    """
    Unified format for all telemetry events entering the OpenGuardian database.
    """
    timestamp: datetime = Field(description="ISO 8601 timestamp of when the event occurred.")
    source: str = Field(description="Name of the connector that produced this event (e.g., 'network').")
    user_id: str = Field(description="Identifier for the user associated with the event.")
    device_id: Optional[str] = Field(default=None, description="Identifier for the source device.")
    event_type: str = Field(description="Type of the event (e.g., 'dns_query').")
    category: str = Field(description="Normalized activity category (e.g., 'gaming', 'social').")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Connector-specific varying properties.")

    model_config = ConfigDict(
        frozen=True,
        extra="forbid"
    )
