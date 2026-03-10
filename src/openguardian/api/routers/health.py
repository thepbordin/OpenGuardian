from fastapi import APIRouter, Depends, HTTPException, status
from openguardian.api.schemas.health import HealthResponse
from openguardian.api.dependencies import get_driver, get_registry

from neo4j import AsyncDriver
from openguardian.connectors.registry import ConnectorRegistry

router = APIRouter(prefix="/health", tags=["System"])

@router.get("", response_model=HealthResponse)
async def health_check(
    driver: AsyncDriver = Depends(get_driver),
    registry: ConnectorRegistry = Depends(get_registry)
):
    """
    Verifies subsystems and returns stability telemetry to proxies.
    """
    try:
        await driver.verify_connectivity()
        neo4j_ok = True
    except Exception:
        neo4j_ok = False

    # Standard check for LLM pipeline (mocked for Phase 4 as true for now)
    llm_ok = True 
    
    health_status = "ok" if (neo4j_ok and llm_ok) else "degraded"
    
    if not neo4j_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Neo4j connection unreachable"
        )
        
    return HealthResponse(
        status=health_status,
        neo4j_connected=neo4j_ok,
        llm_available=llm_ok,
        connector_count=len(registry.list_connectors()),
    )
