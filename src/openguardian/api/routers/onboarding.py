from fastapi import APIRouter
from datetime import datetime
from openguardian.analysis.detector import OnboardingState

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

@router.get("/status", response_model=OnboardingState)
async def get_onboarding_status():
    """
    Retrieves the machine evaluation interval bounds.
    (Mocked for PoC iteration bypassing Neo4j Node lookups)
    """
    return OnboardingState(
        device_id="pihole-network-router-1",
        user_name="Student",
        status="active",
        started_at=datetime.utcnow()
    )
    
@router.post("/setup")
async def register_device(device_id: str, user_name: str, age: int):
    """
    Registers a new network device mapping to track usage aggregates contextually.
    """
    return {"message": "Onboarding sequence initialized", "device_id": device_id}
