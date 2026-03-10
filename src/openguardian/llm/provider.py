import json
import logging
from typing import Protocol, Type, TypeVar
import litellm
import instructor
from pydantic import BaseModel

from openguardian.config.settings import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class LLMUnavailableError(Exception):
    """Raised when the LLM provider fails securely terminating analysis fallback gracefully."""
    pass

class LLMProviderProtocol(Protocol):
    """
    Interface definition that abstract LLM APIs must implement.
    """
    async def analyze(self, system_prompt: str, user_prompt: str, response_schema: Type[T], temperature: float = 0.0) -> T:
        """
        Executes a deterministic LLM prompt adhering rigidly to the Pydantic schema context provided.
        """
        ...

class LiteLLMProvider(LLMProviderProtocol):
    """
    Adaptor wrapping Instructor and litellm to query configured models blindly.
    Includes built-in audit logging for Guardian transparency.
    """
    def __init__(self):
        # We patch litellm's acompletion through instructor to enforce strict schema parsing
        self._client = instructor.from_litellm(litellm.acompletion)
        
    async def analyze(self, system_prompt: str, user_prompt: str, response_schema: Type[T], temperature: float = 0.0) -> T:
        logger.info(f"Dispatching LLM query via litellm provider: {settings.llm_model}")
        
        try:
            response = await self._client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_model=response_schema,
                temperature=temperature,
                max_retries=2,
                api_key=settings.llm_api_key.get_secret_value()
            )
            
            # Simple Audit logging (In a robust system this persists to Neo4j or Postgres)
            self._audit_log(system_prompt, user_prompt, response)
            
            return response
            
        except Exception as e:
            logger.error(f"LiteLLM Provider failed to generate analysis: {e}")
            raise LLMUnavailableError("Core LLM engine failed processing.") from e

    def _audit_log(self, sys: str, user: str, response: BaseModel):
        """
        Writes immutable records detailing precisely what the LLM assessed for accountability.
        """
        audit_payload = {
            "system_prompt": sys,
            "user_prompt": user,
            "response": response.model_dump()
        }
        # Dump to stdout for Docker logging (Proof of Concept implementation)
        # Production would append to a WORM (Write Once Read Many) log file
        logger.debug(f"[LLM AUDIT LOG]: {json.dumps(audit_payload)}")
        
def get_llm_provider() -> LLMProviderProtocol:
    """Dependency injection resolution fallback."""
    return LiteLLMProvider()
