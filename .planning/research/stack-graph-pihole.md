# Stack Research: Neo4j + Pi-hole + FastAPI + Python Plugin Architecture

**Project:** OpenGuardian
**Researched:** 2026-03-10
**Overall confidence:** HIGH (official docs and verified sources throughout)

---

## 1. Neo4j + Python Driver

### 1.1 Library Decision: Official Driver Only

**Use `neo4j` (official driver). Do not use `py2neo`.**

`py2neo` is officially end-of-life (EOL declared November 2023). The GitHub repo is archived. No maintenance, no security patches. If you need an OGM (object-graph mapper), the recommended alternative is `neomodel`.

| Library | Status | Use When |
|---------|--------|----------|
| `neo4j` (official) | Active, v6.1.0 (Jan 2026) | All database access — nodes, relationships, Cypher queries |
| `neomodel` | Active, v5.4.3 (Feb 2025) | Optional: if you want Django-ORM-style model declarations |
| `py2neo` | EOL, archived | Never. Do not install. |

For OpenGuardian, the **official `neo4j` driver is sufficient and preferred**. The graph schema is custom (behavioral knowledge graph) — you are not modeling a domain with fixed entity types the way a web app models Users/Posts. OGM abstraction adds unnecessary indirection for Cypher-heavy analytical workloads.

### 1.2 Version Requirements

```
neo4j>=6.1.0       # Current. Requires Python >=3.10
```

Driver version 6.0 launched September 2025. Within a major version, no breaking API changes. Python 3.10+ is required (known performance issues with 3.8; 3.9 works but 3.10+ recommended).

### 1.3 Driver Initialization Pattern (FastAPI Lifespan)

The driver contains a connection pool. Create it **once** per application lifetime. Use FastAPI's `lifespan` context manager — not deprecated `@app.on_event("startup")`.

```python
# app/infrastructure/neo4j_client.py
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from neo4j import AsyncGraphDatabase, AsyncDriver

_driver: AsyncDriver | None = None


def get_driver() -> AsyncDriver:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized")
    return _driver


@asynccontextmanager
async def lifespan(app):
    global _driver
    _driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        max_connection_pool_size=50,
    )
    await _driver.verify_connectivity()
    yield
    await _driver.close()
```

```python
# app/main.py
from fastapi import FastAPI
from app.infrastructure.neo4j_client import lifespan

app = FastAPI(lifespan=lifespan)
```

### 1.4 Session Dependency Injection

Inject async sessions into route handlers via `Depends`. Sessions are cheap to create; the connection pool handles actual socket reuse.

```python
# app/infrastructure/neo4j_client.py (continued)
from typing import AsyncGenerator
from fastapi import Depends
from neo4j import AsyncSession

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_driver().session(database="neo4j") as session:
        yield session
```

```python
# app/routers/devices.py
from fastapi import APIRouter, Depends
from neo4j import AsyncSession
from app.infrastructure.neo4j_client import get_session

router = APIRouter()

@router.get("/devices/{device_id}/activity")
async def get_device_activity(
    device_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute_read(
        lambda tx: tx.run(
            "MATCH (d:Device {id: $id})-[:ACCESSED]->(a:Activity) RETURN a",
            id=device_id,
        ).data()
    )
    return result
```

### 1.5 Async vs Sync Driver

Use the `AsyncDriver` (via `AsyncGraphDatabase.driver()`). FastAPI is async-first; the async driver integrates naturally with the event loop without threadpool overhead. The API is identical to sync except all calls require `await`.

**Gotcha:** A session object is not concurrency-safe. Do not share a single session across concurrent coroutines. Each request gets its own session from `Depends(get_session)`.

### 1.6 MERGE vs CREATE: Performance Rule

| Situation | Use | Why |
|-----------|-----|-----|
| Event is definitively new (first insert) | `CREATE` | Half the internal queries vs MERGE |
| Entity may already exist (idempotent upsert) | `MERGE` | Avoids duplicates; required for graph correctness |
| Batch of known-new events | `UNWIND ... CREATE` | Fastest batch path |
| Batch of entities that may exist | `UNWIND ... MERGE` | Correct and still batched |

For DNS event ingestion: Device and Domain nodes should use `MERGE` (they persist across events). The `VISITED` relationship edges can use `MERGE` too (with timestamp as a property) or `CREATE` for truly append-only event logging.

### 1.7 Batch Ingestion Pattern (UNWIND)

Never loop over events and issue one Cypher query per event. Batch with `UNWIND`.

```python
# Correct: single query for N events
async def ingest_dns_events(session: AsyncSession, events: list[dict]) -> None:
    await session.execute_write(
        lambda tx: tx.run(
            """
            UNWIND $events AS e
            MERGE (dev:Device {id: e.device_id})
            MERGE (dom:Domain {name: e.domain})
            MERGE (cat:Category {name: e.category})
            MERGE (dom)-[:BELONGS_TO]->(cat)
            CREATE (dev)-[:VISITED {
                timestamp: datetime(e.timestamp),
                bytes: e.bytes_transferred,
                session_id: e.session_id
            }]->(dom)
            """,
            events=events,
        )
    )
```

Recommended batch size: **500–1000 events per transaction**. Larger batches consume more heap; smaller batches waste round-trip overhead.

### 1.8 Schema: Constraints and Indexes

Create constraints at startup — they create backing indexes automatically.

```python
# app/infrastructure/schema.py
SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (d:Device) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT domain_name IF NOT EXISTS FOR (d:Domain) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
    "CREATE CONSTRAINT category_name IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
    # Range index on VISITED.timestamp for temporal queries
    "CREATE INDEX visited_timestamp IF NOT EXISTS FOR ()-[r:VISITED]-() ON (r.timestamp)",
]

async def apply_schema(driver: AsyncDriver) -> None:
    async with driver.session(database="neo4j") as session:
        for stmt in SCHEMA_STATEMENTS:
            await session.run(stmt)
```

Call `apply_schema` inside the `lifespan` startup block after `verify_connectivity`.

**Gotcha:** `IF NOT EXISTS` is required on all constraint/index creation in production code. Without it, re-running startup crashes if the schema already exists.

### 1.9 Recommended Knowledge Graph Schema for OpenGuardian

```
(:User {id, name, age, onboarded_at})
  -[:OWNS]->
(:Device {id, mac_address, label, registered_at})
  -[:VISITED {timestamp, bytes_transferred, session_id, connector}]->
(:Domain {name, first_seen})
  -[:BELONGS_TO]->
(:Category {name, description})
  -[:OCCURRED_IN]->
(:TimeSlot {date, hour, day_of_week})

(:Session {id, device_id, start_time, end_time, dominant_category})
  -[:CONTAINS]->
(:Domain)
```

Key design decisions:
- `VISITED` is append-only. Do not MERGE on the relationship — each visit is a discrete event. Use `CREATE` for the relationship, `MERGE` for nodes.
- `TimeSlot` nodes allow fast "what was accessed at 2am last Tuesday" queries without full scan of relationship timestamps.
- `Category` is a shared node, not a property. This enables graph traversal like "find all devices that visited a category they had never visited before."
- Store `connector` on `VISITED` to know whether the event came from the network, Discord, or other source.

### 1.10 Temporal Queries

Neo4j natively supports `datetime()`, `date()`, `duration()` types. Use them instead of Unix timestamps as strings.

```cypher
-- Find visits outside baseline hours (anomaly detection support query)
MATCH (d:Device {id: $device_id})-[v:VISITED]->(dom:Domain)
WHERE v.timestamp.hour < 6 OR v.timestamp.hour > 22
RETURN dom.name, v.timestamp
ORDER BY v.timestamp DESC
```

---

## 2. Pi-hole Log Ingestion

### 2.1 Pi-hole v6 Architecture Change (Critical)

Pi-hole v6 (released February 2025) made a significant breaking change: the REST API and embedded web server are now built directly into `pihole-FTL`. There is no longer any dependency on `lighttpd` or `PHP`. All configuration is in a single TOML file at `/etc/pihole/pihole.toml`.

**Two valid ingestion strategies exist. Choose one based on deployment:**

| Strategy | When to Use | Pros | Cons |
|----------|-------------|------|------|
| Pi-hole REST API (`/api/queries`) | Pi-hole is on a separate device (network-separated Raspberry Pi) | Clean, no direct file access, version-stable | Requires auth token management, polling overhead |
| Direct SQLite read (`pihole-FTL.db`) | OpenGuardian runs on same host as Pi-hole | Lower latency, richer query capability | Database locking risk, tightly coupled to Pi-hole internals |

**Recommendation for PoC:** Use the REST API. It decouples OpenGuardian from Pi-hole's internal storage. It is the officially supported interface. Switch to direct SQLite only if API polling latency is unacceptable.

### 2.2 Pi-hole v6 API Authentication

The v6 API uses a **session-based SID (Session ID)**. There is no static API key in v6 — this is a breaking change from v5.

Authentication flow:

```python
import httpx
from dataclasses import dataclass

@dataclass
class PiholeSession:
    sid: str
    csrf: str


async def authenticate(base_url: str, password: str) -> PiholeSession:
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.post(
            f"{base_url}/api/auth",
            json={"password": password},
        )
        resp.raise_for_status()
        data = resp.json()
        return PiholeSession(
            sid=data["session"]["sid"],
            csrf=data["session"]["csrf"],
        )
```

The SID is extended on each successful request. If the poller is active, the session stays alive. If idle for the configurable timeout, re-authenticate.

**Best practice:** Use an application password (not the admin password) via `pihole-FTL --config webserver.api.app_password`. This is a separate credential for programmatic access.

Include the SID in subsequent requests via the `X-FTL-SID` header:

```python
headers = {"X-FTL-SID": session.sid}
resp = await client.get(f"{base_url}/api/queries", headers=headers, params={...})
```

### 2.3 Query Log API Endpoint

The query log endpoint is `/api/queries`. It supports server-side pagination (new in v6).

```python
async def fetch_queries(
    client: httpx.AsyncClient,
    base_url: str,
    sid: str,
    from_timestamp: int,
    limit: int = 500,
) -> list[dict]:
    resp = await client.get(
        f"{base_url}/api/queries",
        headers={"X-FTL-SID": sid},
        params={
            "from": from_timestamp,   # Unix timestamp — fetch only new events
            "limit": limit,
        },
    )
    resp.raise_for_status()
    return resp.json().get("queries", [])
```

**Polling strategy:** Store the Unix timestamp of the last ingested query. On each poll cycle (e.g., every 60 seconds), pass `from=<last_timestamp>` to get only new records. This avoids re-processing old data.

**Rate limit:** Pi-hole returns HTTP 429 if you poll too aggressively. A 30–60 second interval is safe for home use.

### 2.4 Direct SQLite Access (Alternative Path)

If running on the same host, you can read `pihole-FTL.db` directly. Default location: `/etc/pihole/pihole-FTL.db`.

**Schema of the `queries` VIEW:**

| Column | Type | Meaning |
|--------|------|---------|
| `id` | integer | Auto-increment PK |
| `timestamp` | integer | Unix timestamp of query |
| `type` | integer | Query type (1=A, 2=AAAA, 9=MX, etc.) |
| `status` | integer | 1=blocked, 2=forwarded, 3=cached, 4=regex block, 5=exact block |
| `domain` | text | Requested domain name |
| `client` | text | Client IP address |
| `forward` | text | Upstream resolver used (nullable) |
| `reply_type` | integer | NODATA, NXDOMAIN, etc. (nullable) |
| `reply_time` | real | Resolution time in seconds (nullable) |
| `dnssec` | integer | DNSSEC status (nullable) |

The `queries` VIEW is assembled from `query_storage` + linking tables (`domain_by_id`, `client_by_id`, `forward_by_id`). Do not query `query_storage` directly; use the VIEW.

**Critical gotcha: Database locking.** Pi-hole's FTL process holds write locks on `pihole-FTL.db` constantly. Direct reads from Python will hit `sqlite3.OperationalError: database is locked` without WAL mode.

Workaround:

```python
import sqlite3

conn = sqlite3.connect(
    "/etc/pihole/pihole-FTL.db",
    timeout=5.0,                  # Wait up to 5s for lock release
    check_same_thread=False,
)
conn.execute("PRAGMA journal_mode=WAL")   # Enable WAL before any query
conn.execute("PRAGMA query_only=ON")       # Read-only safeguard

# Incremental fetch
cursor = conn.execute(
    "SELECT timestamp, domain, client, status, type FROM queries WHERE timestamp > ? ORDER BY timestamp ASC",
    (last_seen_timestamp,),
)
rows = cursor.fetchall()
```

**WAL mode allows concurrent readers with a single writer.** Without it, any attempt to read while FTL is writing fails immediately. Enable WAL first, before any query.

**Note:** If you do not own the Pi-hole process (e.g., it's on a Raspberry Pi you don't control the filesystem of), the API is the only viable path.

### 2.5 Polling Architecture with APScheduler

Use `APScheduler` with `AsyncIOScheduler` for the polling loop inside FastAPI.

```python
# app/connectors/network/poller.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

def start_network_poller(interval_seconds: int = 60) -> None:
    scheduler.add_job(
        poll_pihole_queries,
        trigger="interval",
        seconds=interval_seconds,
        id="network_poller",
        replace_existing=True,
    )
    scheduler.start()
```

Start and stop the scheduler inside the FastAPI lifespan:

```python
@asynccontextmanager
async def lifespan(app):
    # ... neo4j init
    start_network_poller(interval_seconds=60)
    yield
    scheduler.shutdown()
    # ... neo4j close
```

---

## 3. FastAPI Patterns

### 3.1 Project Structure (Domain-Oriented)

```
src/
├── main.py                    # FastAPI app, lifespan
├── config.py                  # Pydantic BaseSettings
├── infrastructure/
│   ├── neo4j_client.py        # Driver init, get_session dependency
│   └── schema.py              # Constraint/index setup
├── connectors/
│   ├── base.py                # BaseConnector ABC
│   ├── registry.py            # ConnectorRegistry
│   ├── network/
│   │   ├── connector.py       # NetworkConnector implementation
│   │   ├── pihole_client.py   # Pi-hole API client
│   │   └── schemas.py         # Pydantic models for raw Pi-hole events
│   └── discord/
│       ├── connector.py
│       └── schemas.py
├── graph/
│   ├── merge.py               # Graph merge logic (UNWIND queries)
│   └── queries.py             # Read queries for API
├── analysis/
│   ├── baseline.py            # Baseline computation
│   ├── anomaly.py             # Anomaly detection coordinator
│   └── llm_adapter.py        # LLM provider abstraction
├── api/
│   ├── devices.py             # Router: devices
│   ├── activity.py            # Router: activity summary
│   ├── alerts.py              # Router: anomaly flags
│   └── onboarding.py         # Router: onboarding flow
└── models/
    └── graph_event.py         # GraphEvent unified model
```

### 3.2 Pydantic v2 — Configuration

Use `pydantic-settings` (separate package in v2, not bundled):

```python
# src/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str

    pihole_base_url: str = Field(default="http://pi.hole")
    pihole_password: str

    poll_interval_seconds: int = Field(default=60)
    llm_provider: str = Field(default="ollama")
    llm_model: str = Field(default="llama3")


settings = Settings()
```

**Gotcha:** In pydantic v2, `pydantic-settings` is a separate install (`pip install pydantic-settings`). Importing `BaseSettings` from `pydantic` directly raises an `ImportError`.

### 3.3 Pydantic v2 — GraphEvent Unified Model

```python
# src/models/graph_event.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal


class GraphEvent(BaseModel):
    timestamp: datetime
    source: str                              # connector name
    user_id: str | None = None              # resolved at graph layer
    device_id: str | None = None
    event_type: str                          # e.g. "dns_query", "dm_sent"
    category: str
    metadata: dict = Field(default_factory=dict)  # connector-specific, not exposed
```

For connector-specific raw events, use discriminated unions to get fast validation and clear OpenAPI schemas:

```python
# src/connectors/network/schemas.py
from pydantic import BaseModel
from typing import Literal


class DnsQueryEvent(BaseModel):
    event_type: Literal["dns_query"] = "dns_query"
    domain: str
    client_ip: str
    status: int
    query_type: int
    reply_time: float | None = None
    timestamp: int                           # Unix timestamp from Pi-hole
```

### 3.4 Pydantic v2 — Validators

`field_validator` and `model_validator` syntax changed in v2. Use `mode="before"` for input coercion, `mode="after"` for cross-field validation.

```python
from pydantic import BaseModel, field_validator, model_validator
from typing import Self


class DnsQueryEvent(BaseModel):
    domain: str
    status: int

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, v: str) -> str:
        return v.lower().strip(".")

    @model_validator(mode="after")
    def check_blocked_has_no_forward(self) -> Self:
        # status 1 = blocked, forward should not be set
        return self
```

**Performance note:** Pydantic v2 runs validation in Rust. Adding Python-level validators incurs a measurable overhead vs. pure declarative constraints. Use `field_validator` only when Rust-native constraints (e.g., `min_length`, `pattern`) cannot express the rule.

### 3.5 Dependency Injection — Connector Registry

Expose the connector registry as a FastAPI dependency:

```python
# src/connectors/registry.py
from fastapi import Request

def get_registry(request: Request) -> "ConnectorRegistry":
    return request.app.state.connector_registry
```

Store the registry on `app.state` during lifespan:

```python
@asynccontextmanager
async def lifespan(app):
    app.state.connector_registry = ConnectorRegistry()
    app.state.connector_registry.load_from_directory(Path("connectors"))
    yield
```

### 3.6 OpenAPI Enrichment

FastAPI generates OpenAPI 3.1 specs from Pydantic v2 models automatically. To keep the spec clean:

- Use `response_model=` on every endpoint (not just `return` type annotations).
- Use `model_config = ConfigDict(json_schema_extra={"example": {...}})` for doc examples.
- Tag routers: `router = APIRouter(prefix="/api/v1/devices", tags=["devices"])`.

---

## 4. Python Plugin / Connector Architecture

### 4.1 Abstract Base Class

```python
# src/connectors/base.py
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from src.models.graph_event import GraphEvent


class BaseConnector(ABC):
    """All connectors must implement this interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique connector identifier, e.g. 'network', 'discord'."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string, e.g. '1.0.0'."""

    @abstractmethod
    async def initialize(self, config: dict[str, Any]) -> None:
        """Called once at startup. Load credentials, set up polling clients."""

    @abstractmethod
    async def events(self) -> AsyncIterator[GraphEvent]:
        """
        Yield normalized GraphEvent objects.
        Called by the scheduler on each poll cycle.
        """

    async def teardown(self) -> None:
        """Called at shutdown. Override to close HTTP clients, flush buffers."""
```

Key design notes:
- `events()` is an `AsyncIterator[GraphEvent]`. The connector handles its own polling state (last seen timestamp, cursor, etc.) internally. The framework just calls `events()` and streams the results into the graph merge layer.
- `initialize()` receives the connector's config slice from the global settings. The connector is responsible for parsing its own config.
- `teardown()` is non-abstract with a default no-op so connectors only override when needed.

### 4.2 Connector Manifest (connector.json)

Each connector directory contains a `connector.json` declaring metadata:

```json
{
  "name": "network",
  "version": "1.0.0",
  "description": "DNS traffic ingestion via Pi-hole FTL API",
  "data_fields": [
    {"field": "domain", "privacy": "sensitive", "description": "Queried domain"},
    {"field": "client_ip", "privacy": "sensitive", "description": "Device IP"},
    {"field": "category", "privacy": "public", "description": "Traffic category"},
    {"field": "bytes_transferred", "privacy": "public", "description": "Traffic volume"}
  ],
  "connector_class": "NetworkConnector",
  "module": "connector"
}
```

The `privacy` field drives what gets exposed in reports (only `public` fields reach the guardian dashboard).

### 4.3 Connector Registry with importlib Discovery

```python
# src/connectors/registry.py
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.connectors.base import BaseConnector

if TYPE_CHECKING:
    pass


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {}

    def load_from_directory(self, connectors_dir: Path) -> None:
        for manifest_path in connectors_dir.glob("*/connector.json"):
            connector_dir = manifest_path.parent
            self._load_connector(connector_dir, manifest_path)

    def _load_connector(self, connector_dir: Path, manifest_path: Path) -> None:
        manifest = json.loads(manifest_path.read_text())
        module_file = connector_dir / f"{manifest['module']}.py"

        spec = importlib.util.spec_from_file_location(
            f"connectors.{manifest['name']}", module_file
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load connector module: {module_file}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        cls = getattr(module, manifest["connector_class"])
        if not issubclass(cls, BaseConnector):
            raise TypeError(f"{cls} does not implement BaseConnector")

        instance: BaseConnector = cls()
        self._connectors[manifest["name"]] = instance

    def get(self, name: str) -> BaseConnector | None:
        return self._connectors.get(name)

    def all(self) -> list[BaseConnector]:
        return list(self._connectors.values())

    def names(self) -> list[str]:
        return list(self._connectors.keys())
```

**Gotcha:** `spec.loader.exec_module(module)` executes the module's top-level code. Any import errors inside the connector module will propagate here. Wrap in a `try/except ImportError` per connector so one broken connector does not prevent others from loading.

### 4.4 Network Connector: Full Example

```python
# connectors/network/connector.py
from collections.abc import AsyncIterator
from typing import Any
import httpx

from src.connectors.base import BaseConnector
from src.models.graph_event import GraphEvent
from connectors.network.pihole_client import PiholeClient
from connectors.network.categorizer import categorize_domain


class NetworkConnector(BaseConnector):
    _client: PiholeClient
    _last_timestamp: int = 0

    @property
    def name(self) -> str:
        return "network"

    @property
    def version(self) -> str:
        return "1.0.0"

    async def initialize(self, config: dict[str, Any]) -> None:
        self._client = PiholeClient(
            base_url=config["pihole_base_url"],
            password=config["pihole_password"],
        )
        await self._client.authenticate()

    async def events(self) -> AsyncIterator[GraphEvent]:
        queries = await self._client.fetch_queries(from_timestamp=self._last_timestamp)
        for q in queries:
            if q["status"] not in (2, 3):  # Skip blocked queries
                continue
            yield GraphEvent(
                timestamp=q["timestamp"],
                source=self.name,
                device_id=q["client"],          # IP — resolved to device at graph layer
                event_type="dns_query",
                category=categorize_domain(q["domain"]),
                metadata={"domain": q["domain"], "reply_time": q.get("reply_time")},
            )
            self._last_timestamp = max(self._last_timestamp, int(q["timestamp"].timestamp()))

    async def teardown(self) -> None:
        await self._client.close()
```

---

## 5. Key Gotchas and Pitfalls

### 5.1 Pi-hole v6 API — No Static Token

**Pitfall:** Pi-hole v5 used a static API key (`?auth=<key>` query parameter). v6 replaced this with session-based SIDs. Any code or documentation referencing `?auth=` is for v5.

**Fix:** Always POST to `/api/auth` first. Cache the SID. Re-authenticate on 401.

### 5.2 SQLite Locking on Direct DB Access

**Pitfall:** Querying `pihole-FTL.db` directly without WAL mode causes `database is locked` errors when FTL is writing (which is nearly always during active use).

**Fix:** Issue `PRAGMA journal_mode=WAL` on connection open, before any SELECT. Use `timeout=5.0` on the connection object.

### 5.3 py2neo Is Dead

**Pitfall:** py2neo appears in many tutorials. It is EOL as of late 2023 and receives no security updates.

**Fix:** Use the official `neo4j` driver. The API is `session.execute_read()` / `session.execute_write()` with transaction functions.

### 5.4 MERGE Performance on High-Volume Ingestion

**Pitfall:** Using `MERGE` for every individual node in a loop causes one round-trip per event. At 1000 DNS queries/minute this is a bottleneck.

**Fix:** Batch with `UNWIND $events AS e MERGE ...`. Use `CREATE` for `VISITED` relationships (they are always new). Use `MERGE` only for `Device`, `Domain`, `Category` nodes.

### 5.5 pydantic-settings is Not pydantic

**Pitfall:** Pydantic v2 removed `BaseSettings` from the core `pydantic` package. `from pydantic import BaseSettings` raises `ImportError`.

**Fix:** `pip install pydantic-settings` and `from pydantic_settings import BaseSettings`.

### 5.6 AsyncDriver Session Concurrency

**Pitfall:** Sharing a single `AsyncSession` across concurrent requests causes cryptic errors about overlapping reads/writes.

**Fix:** Always use `Depends(get_session)` to get a fresh session per request. The connection pool handles efficiency; do not try to share sessions.

### 5.7 Connector importlib and Relative Imports

**Pitfall:** Connector modules loaded via `importlib.util.spec_from_file_location` are not part of the Python package tree. Relative imports inside connector modules (`from .schemas import ...`) will fail.

**Fix:** Use absolute imports inside connector modules (`from connectors.network.schemas import ...`) and ensure the project root is on `sys.path`. Alternatively, structure connectors as installed packages and use entry points.

### 5.8 Pi-hole Status Codes — Filter Appropriately

**Pitfall:** Including blocked queries (status 1, 4, 5) in the behavior graph distorts the picture. A device that hits a blocked ad network does not "use" that service.

**Fix:** Only ingest queries where `status IN (2, 3)` — forwarded (allowed) and cached (allowed). Blocked queries can be separately tracked as a security signal but should not contribute to the behavioral baseline.

### 5.9 Neo4j `IF NOT EXISTS` on Schema Setup

**Pitfall:** Running `CREATE CONSTRAINT` without `IF NOT EXISTS` crashes on every restart after the first one.

**Fix:** All `CREATE CONSTRAINT` and `CREATE INDEX` statements must include `IF NOT EXISTS`.

---

## 6. Library Versions Summary

| Library | Recommended Version | Notes |
|---------|--------------------|-|
| `neo4j` | `>=6.1.0` | Official driver. Python 3.10+ required. |
| `fastapi` | `>=0.115.0` | Lifespan events stable. |
| `pydantic` | `>=2.7.0` | v2 required. Not v1. |
| `pydantic-settings` | `>=2.3.0` | Separate package for `BaseSettings`. |
| `httpx` | `>=0.27.0` | Async HTTP client for Pi-hole API. |
| `apscheduler` | `>=3.10.0` | Use `AsyncIOScheduler`. v4 is in beta — avoid. |
| `uvicorn` | `>=0.30.0` | ASGI server. Use with `--loop uvloop` for performance. |
| `python` | `>=3.10` | Required by neo4j driver v6. |

**Do not install:**
- `py2neo` — EOL
- `neo4j-driver` — old package name, now replaced by `neo4j`
- `pydantic==1.*` — incompatible with all modern FastAPI patterns

---

## 7. Installation

```bash
# Core runtime
pnpm ... # N/A - this is Python; use:
uv pip install \
  neo4j>=6.1.0 \
  fastapi>=0.115.0 \
  pydantic>=2.7.0 \
  pydantic-settings>=2.3.0 \
  httpx>=0.27.0 \
  apscheduler>=3.10.0 \
  uvicorn[standard]>=0.30.0

# Dev
uv pip install \
  pytest \
  pytest-asyncio \
  mypy \
  ruff
```

Or in `pyproject.toml`:

```toml
[project]
requires-python = ">=3.10"
dependencies = [
  "neo4j>=6.1.0",
  "fastapi>=0.115.0",
  "pydantic>=2.7.0",
  "pydantic-settings>=2.3.0",
  "httpx>=0.27.0",
  "apscheduler>=3.10.0",
  "uvicorn[standard]>=0.30.0",
]
```

---

## 8. Sources

- [Neo4j Python Driver Manual (current)](https://neo4j.com/docs/python-manual/current/)
- [Neo4j Python Driver Performance Recommendations](https://neo4j.com/docs/python-manual/current/performance/)
- [Neo4j Async API Documentation v6.1](https://neo4j.com/docs/api/python-driver/current/async_api.html)
- [neo4j PyPI — version history](https://pypi.org/project/neo4j/)
- [Py2neo End-of-Life Migration Guide](https://neo4j.com/blog/developer/py2neo-end-migration-guide/)
- [Neomodel 2024 Wrap-up](https://neo4j.com/blog/developer/neomodel-2024-wrap-up/)
- [Introducing Pi-hole v6](https://pi-hole.net/blog/2025/02/18/introducing-pi-hole-v6/)
- [Pi-hole API Authentication Docs](https://docs.pi-hole.net/api/auth/)
- [Pi-hole Query Database Schema](https://docs.pi-hole.net/database/query-database/)
- [How to Build Plugin Systems in Python (Jan 2026)](https://oneuptime.com/blog/post/2026-01-30-python-plugin-systems/view)
- [FastAPI Best Practices (zhanymkanov)](https://github.com/zhanymkanov/fastapi-best-practices)
- [Pydantic v2 Validators](https://docs.pydantic.dev/latest/concepts/validators/)
- [Pydantic v2 Discriminated Unions](https://docs.pydantic.dev/latest/concepts/unions/)
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/testing-events/)
- [Neo4j Run Concurrent Transactions](https://neo4j.com/docs/python-manual/current/concurrency/)
- [Neo4j Temporal Values (Cypher)](https://neo4j.com/docs/cypher-manual/current/values-and-types/temporal/)
