import logging
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from openguardian.analysis.summarizer import GraphSummarizer
from openguardian.analysis.risk_loader import RiskLoader
from openguardian.llm.provider import get_llm_provider, LLMUnavailableError

logger = logging.getLogger(__name__)

class AnomalyFlag(BaseModel):
    severity: Literal["informational", "warning", "critical"]
    category: str
    reasoning: str = Field(description="Guardian-facing plain English explanation of the behavioral pivot.")
    risk_file_cited: Optional[str] = Field(default=None, description="Name of the specific Risk file triggering this flag")

class AnalysisResult(BaseModel):
    flags: List[AnomalyFlag] = Field(default_factory=list, description="Ammount of deviations found vs baseline. Prefer fewer, higher-confidence flags over many low-confidence flags.")

class OnboardingState(BaseModel):
    device_id: str
    user_name: str
    status: Literal["onboarding", "active"]
    started_at: datetime
    # Age/Schedule are mocked here to focus on the pipeline logic for PoC

class AnomalyDetector:
    """
    Orchestrates Context building, translates Cypher to English, fetches Known Risks,
    and dispatches rigid Instruction to LiteLLM adapter.
    """
    
    SYSTEM_PROMPT = """You are a behavioral safety orchestrator for OpenGuardian.
You analyze narrative summaries of categorized network traversal and flag significant deviations based on standard educational or familial boundaries.
You MUST prefer fewer, extremely high-confidence flags over many low-confidence ones to prevent alert fatigue.
Output validations only in strict JSON adhering to the provided schemas.

If known risk topologies are supplied in context, cross-reference them explicitly and cite their name if a behavior overlaps directly with their progression patterns.
NEVER invent domain names. Return only the reasoning."""

    @staticmethod
    async def run_analysis_cycle(device_id: str) -> AnalysisResult:
        """
        Executes a single end-to-end evaluation cycle utilizing Graph data mapped entirely over text.
        """
        logger.info(f"Starting analysis cycle for device: {device_id}")
        
        # 1. Fetch baselines and windows (Onboarding logic assumes active for PoC run)
        baseline = await GraphSummarizer.get_baseline_summary(device_id)
        current = await GraphSummarizer.get_current_window_summary(device_id, hours=6)
        
        # 2. Extract potential Known Risks
        risks_payload = ""
        if current.active_categories:
            applicable_risks = await RiskLoader.load_applicable_risks(current.active_categories)
            if applicable_risks:
                risks_payload = "--- KNOWN RISK PATTERNS OBSERVED VIA CONTEXT ---\n" + "\n\n".join(applicable_risks)
                
        # 3. Assemble Prompt
        prompt = f"""
BASELINE BEHAVIOR:
{baseline.narrative}

CURRENT ACTIVITY WINDOW (LAST 6 HOURS):
{current.narrative}

{risks_payload}

Evaluate the CURRENT ACTIVITY against the BASELINE. If activities heavily deviate
(e.g., massive spikes in unused categories, appearance of VPN proxies, or overlaps with
the KNOWN RISK PATTERNS), yield severe flags. Otherwise return an empty array.
"""
        
        provider = get_llm_provider()
        
        try:
            result = await provider.analyze(
                system_prompt=AnomalyDetector.SYSTEM_PROMPT,
                user_prompt=prompt,
                response_schema=AnalysisResult,
                temperature=0.0 # Deterministic structured bounds
            )
            logger.info(f"Analysis completed yielding {len(result.flags)} flags.")
            return result
            
        except LLMUnavailableError:
            logger.warning("LLM Unavailable, bypassing analysis loop securely.")
            return AnalysisResult(flags=[])
