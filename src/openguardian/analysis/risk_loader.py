import aiofiles
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# Base location for external models determining attack trajectories
RISKS_DIR = Path(__file__).parent.parent.parent.parent / "known-risks"

class RiskLoader:
    """
    Ingests local markdown signatures tracking recognized attack structures.
    Uses exact-match Trigger Categories avoiding vector search bloat.
    """
    
    @staticmethod
    async def load_applicable_risks(active_categories: List[str]) -> List[str]:
        """
        Asynchronously scans `/known-risks/*.md` parsing `## Trigger Categories`.
        Injects the full context if intersections with `active_categories` exist.
        """
        logger.info(f"Scanning for known risks applying to categories: {active_categories}")
        
        if not RISKS_DIR.exists() or not active_categories:
            return []
            
        applicable_files = []
        
        # Iteratively fetch disk models
        # Note: Aiofiles provides non-blocking iteration preventing Starvation in production APIs
        for file_path in RISKS_DIR.iterdir():
            if file_path.is_file() and file_path.suffix == ".md":
                
                try:
                    async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                        content = await f.read()
                        
                        # Lightweight local extraction without full Markdown AST trees
                        if "## Trigger Categories" in content:
                            trigger_section = content.split("## Trigger Categories")[1].split("## ")[0]
                            # Detect active category subset matches
                            if any(cat in trigger_section for cat in active_categories):
                                logger.info(f"Loaded Risk Model: {file_path.name}")
                                applicable_files.append(content)
                except Exception as e:
                    logger.error(f"Failed to load risk file '{file_path.name}': {e}")
                    
        return applicable_files
