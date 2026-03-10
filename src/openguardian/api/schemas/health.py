from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    """
    Standard heartbeat schema validating subsystem connectivity.
    """
    status: str = Field(description="Service stability status (e.g., 'ok', 'degraded')")
    neo4j_connected: bool = Field(description="Flag denoting if knowledge graph db is reachable")
    llm_available: bool = Field(description="Flag denoting if LLM provider returns context windows")
    connector_count: int = Field(description="Quantity of active plugin connectors yielding data")
    version: str = Field(default="0.1.0", description="Current backend release identifier")
