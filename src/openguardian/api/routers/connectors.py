from fastapi import APIRouter, Depends
from typing import Dict, Any
from openguardian.connectors.registry import ConnectorRegistry
from openguardian.api.dependencies import get_registry

router = APIRouter(prefix="/connectors", tags=["System"])

@router.get("")
async def list_connectors(registry: ConnectorRegistry = Depends(get_registry)):
    """
    Returns registered data telemetry plugins and mapped internal version info.
    """
    manifests = registry.list_manifests()
    return {
        name: {
            "version": m.version,
            "data_fields": m.data_fields,
            "status": "running"
        }
        for name, m in manifests.items()
    }
