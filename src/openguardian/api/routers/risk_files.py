from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from openguardian.analysis.risk_loader import RISKS_DIR

router = APIRouter(prefix="/risk-files", tags=["System"])

class RiskFileContext(BaseModel):
    filename: str
    size_bytes: int

@router.get("", response_model=List[RiskFileContext])
async def list_loaded_risks():
    """
    Returns references to installed Known-Risk topology signatures currently active.
    """
    files = []
    if RISKS_DIR.exists():
        for f in RISKS_DIR.iterdir():
            if f.is_file() and f.suffix == '.md':
                files.append(RiskFileContext(filename=f.name, size_bytes=f.stat().st_size))
                
    return files
