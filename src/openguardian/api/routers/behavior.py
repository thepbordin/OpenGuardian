from fastapi import APIRouter
from openguardian.analysis.summarizer import GraphSummarizer, BaselineSummary, CurrentWindowSummary

router = APIRouter(prefix="/behavior", tags=["Behavior"])

@router.get("/summary", response_model=CurrentWindowSummary)
async def get_behavior_summary(device_id: str = "pihole-network-router-1", hours: int = 24):
    """
    Retrieves aggregated knowledge graph categorizations without leaking exact URLs.
    """
    return await GraphSummarizer.get_current_window_summary(device_id, hours)

@router.get("/baseline", response_model=BaselineSummary)
async def get_behavior_baseline(device_id: str = "pihole-network-router-1"):
    """
    Retrieves established context rules configured post onboarding.
    """
    return await GraphSummarizer.get_baseline_summary(device_id)
