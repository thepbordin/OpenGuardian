import asyncio
import logging
from typing import AsyncIterator, Optional, List, Dict, Any
import httpx
from datetime import datetime

from openguardian.config.settings import settings
from openguardian.models.graph_event import GraphEvent
from openguardian.connectors.protocol import ConnectorProtocol
from openguardian.privacy.hashing import hash_domain
from openguardian.categorization.category_map import category_map

logger = logging.getLogger(__name__)

class NetworkConnector(ConnectorProtocol):
    """
    Ingests DNS requests from a Pi-hole v6 instance via REST API.
    Uses session-based SID authentication.
    """
    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._sid: str | None = None
        self._last_timestamp: int = 0
        self._is_running = False

    @property
    def connector_id(self) -> str:
        return "network"
    
    async def start(self) -> None:
        logger.info("Starting Network Connector (Pi-hole v6)")
        self._client = httpx.AsyncClient(base_url=settings.pihole_url.rstrip('/'), timeout=10.0)
        self._is_running = True
        await self._authenticate()

    async def _authenticate(self):
        if not self._client:
            return
            
        logger.info("Authenticating with Pi-hole v6 API...")
        try:
            resp = await self._client.post(
                "/api/auth",
                json={"password": settings.pihole_password}
            )
            resp.raise_for_status()
            data = resp.json()
            if "session" in data and "sid" in data["session"]:
                self._sid = data["session"]["sid"]
                self._client.headers.update({"X-FTL-SID": self._sid})
                logger.info("Successfully authenticated with Pi-hole and cached SID.")
            else:
                logger.error("Pi-hole auth response did not contain session SID.")
        except Exception as e:
            logger.error(f"Failed to authenticate with Pi-hole: {e}")
            self._sid = None

    async def stop(self) -> None:
        self._is_running = False
        if self._client:
            await self._client.aclose()
        logger.info("Network Connector stopped.")

    async def poll(self) -> AsyncIterator[GraphEvent]:
        if not self._is_running or not self._client:
            return

        if not self._sid:
            await self._authenticate()
            if not self._sid:
                logger.warning("Network connector lacks authentication. Skipping poll.")
                return

        # Fetch incremental queries
        try:
            resp = await self._client.get(f"/api/queries?from={self._last_timestamp}")
            if resp.status_code == 401:
                logger.warning("Pi-hole session expired. Re-authenticating...")
                await self._authenticate()
                return # Skip this poll loop, we will try again next interval.

            resp.raise_for_status()
            data = resp.json()
            queries = data.get("queries", [])
            
            for q in queries:
                # Based on Pi-hole v6 schema (simplified array payload or object representation)
                # Typically [id, timestamp, type, status, domain, client, forward, reply_type, reply_time_10us, dnssec]
                # If it's returning objects, adjust accordingly. We'll anticipate dict items here for safety if API wrapped it.
                if isinstance(q, dict):
                    status = q.get("status", 0)
                    ts = q.get("timestamp", 0)
                    domain = q.get("domain", "")
                    device_id = q.get("client", "unknown_device")
                else: 
                    # fallback for tuple/array formatted queries based on standard FTL logs
                    if len(q) >= 6:
                        ts = q[1]
                        status = q[3]
                        domain = q[4]
                        device_id = str(q[5])
                    else:
                        continue

                # We only ingest Forwarded (2) or Cached (3)
                if status not in (2, 3):
                    continue
                
                # Update checkpoint
                if ts > self._last_timestamp:
                    self._last_timestamp = ts

                # Categorize
                category = category_map.categorize(domain)
                
                # Strip CDN/Ads to reduce noise (design decision)
                if category in ("cdn_infra", "advertising"):
                    continue

                hashed_domain = hash_domain(domain)
                
                event = GraphEvent(
                    timestamp=datetime.fromtimestamp(ts),
                    source=self.connector_id,
                    user_id="pending_assignment", # Resolved dynamically later or defaults
                    device_id=device_id,
                    event_type="dns_query",
                    category=category,
                    metadata={
                        "domain_hash": hashed_domain,
                        "status": status
                    }
                )
                yield event
        except httpx.NetworkError as e:
            logger.error(f"Network error polling Pi-hole: {e}")
        except Exception as e:
            logger.error(f"Unexpected error polling Pi-hole: {e}")

def get_connector() -> ConnectorProtocol:
    """Factory dependency injection required by ConnectorRegistry."""
    return NetworkConnector()
