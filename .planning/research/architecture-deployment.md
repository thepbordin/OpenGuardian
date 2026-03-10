# Architecture & Deployment Research: OpenGuardian

**Project:** OpenGuardian — locally-run network behavior monitoring service
**Researched:** 2026-03-10
**Overall confidence:** MEDIUM-HIGH (core patterns verified via official docs and multiple sources)

---

## 1. Python Project Structure

### Layout: src vs flat

**Recommendation: src layout.**

The `src/` layout is the PyPA-recommended approach for anything beyond a quick demo. It forces installation before import, which means tests run against the installed package (not the working directory), catching packaging issues that users will hit. For a service with a modular connector architecture that may later be distributed or pip-installed, this is the correct choice from day one.

```
openguardian/
├── src/
│   └── openguardian/
│       ├── __init__.py
│       ├── main.py                  # entry point: boots FastAPI + lifespan
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py            # Settings (pydantic-settings)
│       │   ├── logging.py
│       │   └── events.py            # GraphEvent dataclass / Pydantic model
│       ├── connectors/
│       │   ├── __init__.py
│       │   ├── base.py              # ConnectorProtocol definition
│       │   ├── network/             # Pi-hole DNS log connector
│       │   │   ├── __init__.py
│       │   │   ├── connector.py
│       │   │   ├── parser.py
│       │   │   └── connector.json
│       │   └── discord/
│       │       ├── __init__.py
│       │       ├── connector.py
│       │       └── connector.json
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── client.py            # Neo4j driver wrapper / session factory
│       │   ├── queries.py           # Cypher query constants
│       │   ├── repository.py        # graph read/write operations
│       │   └── migrations/          # versioned Cypher migration scripts
│       │       ├── 001_initial_schema.cypher
│       │       └── 002_add_timeslot_index.cypher
│       ├── analysis/
│       │   ├── __init__.py
│       │   ├── llm/
│       │   │   ├── __init__.py
│       │   │   ├── base.py          # LLMProviderProtocol
│       │   │   ├── openai_provider.py
│       │   │   ├── anthropic_provider.py
│       │   │   └── ollama_provider.py
│       │   ├── baseline.py          # onboarding / baseline computation
│       │   ├── anomaly.py           # anomaly detection pipeline
│       │   └── risk_loader.py       # loads /known-risks/*.md files
│       ├── api/
│       │   ├── __init__.py
│       │   ├── router.py            # root APIRouter
│       │   ├── v1/
│       │   │   ├── alerts.py
│       │   │   ├── behavior.py
│       │   │   └── users.py
│       │   └── schemas.py           # Pydantic response/request models
│       └── notifications/
│           ├── __init__.py
│           └── email.py
├── tests/
│   ├── conftest.py                  # shared fixtures (Neo4j container, mock LLM)
│   ├── unit/
│   │   ├── test_parser_network.py
│   │   ├── test_anomaly.py
│   │   └── test_risk_loader.py
│   └── integration/
│       ├── test_graph_repository.py
│       └── test_ingestion_pipeline.py
├── known-risks/
│   ├── risk_grooming_roblox.md
│   └── risk_grooming_discord.md
├── docker/
│   ├── docker-compose.yml
│   └── neo4j_auth.txt.example
├── pyproject.toml
├── .env.example
└── README.md
```

**Confidence: HIGH** — PyPA official documentation recommends src layout for all packaged projects.

---

### Package Manager: uv

**Recommendation: uv.**

As of early 2026, `uv` (written in Rust, by Astral/Ruff authors) is the clear winner for new Python projects that are not published to PyPI. It is 10-100x faster than pip/poetry, handles venvs, Python version management, lockfiles, and pyproject.toml natively. Poetry still has a marginally smoother PyPI publish workflow, but OpenGuardian is a self-hosted service — not a library — so publish ergonomics are irrelevant.

Migration path: `uv` reads standard `pyproject.toml` (PEP 517/518), so switching away later is not a lock-in risk.

**Confidence: HIGH** — Multiple 2026 sources agree; uv is now the default recommendation for new applications.

---

### pyproject.toml Structure

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "openguardian"
version = "0.1.0"
description = "Locally-run network behavior monitoring with Knowledge Graph + LLM analysis"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "neo4j>=6.0",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "aiofiles>=24.1",
    "httpx>=0.28",          # async HTTP for LLM providers
    "openai>=1.58",
    "anthropic>=0.40",
    "python-multipart>=0.0.20",
    "apscheduler>=4.0a5",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "testcontainers[neo4j]>=4.9",
    "pytest-mockllm>=0.2",
    "ruff>=0.9",
    "mypy>=1.13",
    "coverage[toml]>=7.6",
]

[project.scripts]
openguardian = "openguardian.main:run"

[tool.hatch.build.targets.wheel]
packages = ["src/openguardian"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
strict = true
python_version = "3.11"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src/openguardian"]
```

**Note on APScheduler 4.x:** APScheduler v4 is still alpha/pre-release as of early 2026. If stability is needed for the PoC, use APScheduler 3.x (`apscheduler>=3.10`) with `AsyncIOScheduler` — it is production-stable and well-understood. Pin to `apscheduler>=3.10,<4` until v4 stabilises.

---

## 2. Background Service Architecture

### Core Problem

OpenGuardian needs three concurrent long-running behaviours inside one process:

1. **Continuous ingestion** — tail Pi-hole logs in near-real-time, parse, write to graph
2. **Periodic analysis** — every N minutes, pull recent graph data, run LLM analysis
3. **API server** — FastAPI handling dashboard/notification requests

All three run in the same asyncio event loop. FastAPI's lifespan context manager is the canonical place to launch and cancel them.

### Recommended Pattern: FastAPI Lifespan + asyncio.TaskGroup

```python
# src/openguardian/main.py
from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from openguardian.core.config import settings
from openguardian.connectors.network.connector import NetworkConnector
from openguardian.analysis.anomaly import run_analysis_loop
from openguardian.graph.client import GraphClient

@asynccontextmanager
async def lifespan(app: FastAPI):
    graph = GraphClient(settings.neo4j_uri, settings.neo4j_auth)
    connector = NetworkConnector(settings.pihole_log_path, graph)

    # Python 3.11+ structured concurrency: both tasks cancel together on shutdown
    async with asyncio.TaskGroup() as tg:
        ingest_task = tg.create_task(connector.run_forever())
        analysis_task = tg.create_task(
            run_analysis_loop(graph, interval_seconds=settings.analysis_interval)
        )
        yield  # serve HTTP requests here
        # TaskGroup cancels both tasks on exit

app = FastAPI(lifespan=lifespan)
```

**Why TaskGroup over create_task directly:** `asyncio.TaskGroup` (Python 3.11+) implements structured concurrency. If either background task crashes, the group cancels the other and re-raises, rather than silently dropping tasks. This is the correct pattern for a long-lived service where silent task death is a critical failure mode.

**Confidence: HIGH** — FastAPI official docs + Python 3.11 asyncio docs confirm this pattern.

---

### Continuous Log Ingestion Pattern

Pi-hole DNS logs are append-only flat files. The ingestion loop must tail them without blocking the event loop.

```python
# src/openguardian/connectors/network/connector.py
import asyncio
import aiofiles
from pathlib import Path
from openguardian.core.events import GraphEvent

class NetworkConnector:
    def __init__(self, log_path: Path, graph: "GraphClient") -> None:
        self._log_path = log_path
        self._graph = graph

    async def run_forever(self) -> None:
        async with aiofiles.open(self._log_path, mode="r") as f:
            # seek to end — only process new lines
            await f.seek(0, 2)
            while True:
                line = await f.readline()
                if line:
                    event = self._parse(line)
                    if event:
                        await self._graph.merge_event(event)
                else:
                    # no new data — yield control, don't spin
                    await asyncio.sleep(0.5)

    def _parse(self, line: str) -> GraphEvent | None:
        ...
```

**Key detail:** `await asyncio.sleep(0.5)` on empty reads prevents CPU spin. `aiofiles` delegates file I/O to a thread pool, keeping the event loop free.

**Confidence: HIGH** — aiofiles is the standard library for async file I/O in asyncio services.

---

### Periodic Analysis Pattern

```python
# src/openguardian/analysis/anomaly.py
import asyncio
from openguardian.graph.client import GraphClient

async def run_analysis_loop(
    graph: GraphClient,
    interval_seconds: int = 300,
) -> None:
    while True:
        try:
            await _run_analysis_cycle(graph)
        except Exception as exc:
            # log but do not crash the loop — graceful degradation requirement
            import logging
            logging.getLogger(__name__).error("Analysis cycle failed: %s", exc)
        await asyncio.sleep(interval_seconds)
```

This satisfies the NFR "graceful degradation" — if the LLM is unavailable, the loop logs and continues rather than bringing down the service.

---

### Connector Protocol

All connectors implement a structural protocol — no forced inheritance, just interface compliance:

```python
# src/openguardian/connectors/base.py
from typing import Protocol, AsyncIterator
from openguardian.core.events import GraphEvent

class ConnectorProtocol(Protocol):
    """All connectors must be discoverable by name and produce GraphEvents."""

    @property
    def name(self) -> str: ...

    async def run_forever(self) -> None:
        """Long-running ingestion loop. Must handle its own exceptions."""
        ...

    def __aiter__(self) -> AsyncIterator[GraphEvent]: ...
```

`Protocol` (not ABC) is preferred because it enables structural subtyping — third-party connectors dropped in the `/connectors` directory do not need to import from `openguardian.connectors.base`. This is important for the plugin-drop model described in the requirements.

**Confidence: HIGH** — Python 3.8+ `typing.Protocol` is the standard for structural interfaces.

---

## 3. Neo4j Local Deployment

### Docker Compose

```yaml
# docker/docker-compose.yml
services:
  neo4j:
    image: neo4j:5.26-community   # pin minor, not :latest
    container_name: openguardian-neo4j
    restart: unless-stopped
    ports:
      - "7474:7474"   # Neo4j Browser (HTTP)
      - "7687:7687"   # Bolt protocol (driver connection)
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - neo4j_import:/import
      - neo4j_plugins:/plugins
      - ./neo4j.conf:/conf/neo4j.conf:ro
    environment:
      # Avoid storing credentials in compose; use secrets file instead
      - NEO4J_AUTH_FILE=/run/secrets/neo4j_auth
      - NEO4J_server_memory_heap_initial__size=512m
      - NEO4J_server_memory_heap_max__size=1G
      - NEO4J_server_memory_pagecache_size=512m
    secrets:
      - neo4j_auth
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "$$NEO4J_PASSWORD", "RETURN 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s

secrets:
  neo4j_auth:
    file: ./neo4j_auth.txt   # git-ignored; contains "neo4j/your_password"

volumes:
  neo4j_data:
  neo4j_logs:
  neo4j_import:
  neo4j_plugins:
```

**Memory sizing:** The defaults above (512m heap, 1G max heap, 512m pagecache) are appropriate for a home NAS or Raspberry Pi 4. For a Pi with 4GB RAM, total Neo4j footprint will be ~1.5-2GB. Reduce heap if running on a device with <=2GB.

**Image pinning:** Pin to a specific minor version (`neo4j:5.26-community`), not `latest`. Neo4j breaking changes happen between minors. The `2025.x` release line (new naming convention) is available but 5.x LTS is more stable for a PoC.

**Confidence: HIGH** — Official Neo4j Operations Manual docker-compose-standalone documentation.

---

### Python Driver: Connection Management

```python
# src/openguardian/graph/client.py
from neo4j import AsyncGraphDatabase, AsyncDriver
from openguardian.core.config import settings

class GraphClient:
    """
    Thin wrapper around the Neo4j async driver.
    One instance per application lifetime; driver manages connection pool internally.
    """
    def __init__(self, uri: str, auth: tuple[str, str]) -> None:
        self._driver: AsyncDriver = AsyncGraphDatabase.driver(uri, auth=auth)

    async def verify_connectivity(self) -> None:
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        await self._driver.close()

    async def merge_event(self, event: "GraphEvent") -> None:
        async with self._driver.session(database="neo4j") as session:
            await session.execute_write(self._write_event_tx, event)

    @staticmethod
    async def _write_event_tx(tx: "AsyncManagedTransaction", event: "GraphEvent") -> None:
        await tx.run(
            """
            MERGE (d:Device {device_id: $device_id})
            MERGE (a:Activity {category: $category})
            MERGE (ts:TimeSlot {slot: $slot})
            MERGE (d)-[:ACCESSED]->(a)
            MERGE (a)-[:OCCURRED_AT]->(ts)
            """,
            device_id=event.device_id,
            category=event.category,
            slot=event.time_slot,
        )
```

**Key principle:** One `AsyncDriver` instance per process. The driver manages an internal connection pool. Do not create a new driver per request — this is a critical pitfall (see Section 6).

**Driver version:** neo4j >= 6.0 supports Python >= 3.10. The `neo4j-rust-ext` package is a drop-in performance boost (same API, Rust-backed serialization).

**Confidence: HIGH** — Official Neo4j Python Driver Manual.

---

### Database Migration Strategy

Neo4j is schemaless but benefits from explicit constraint and index management. The Liquibase Neo4j plugin exists but is Java-based — overkill for a local PoC.

**Recommended for PoC: simple versioned Cypher scripts + startup migration runner.**

```python
# src/openguardian/graph/migrations/__init__.py
"""
Migration runner. Executes numbered .cypher files in order.
Idempotent: tracks applied migrations in a :Migration node.
"""
import importlib.resources
from pathlib import Path
from neo4j import AsyncDriver

MIGRATIONS_PATH = Path(__file__).parent

async def run_migrations(driver: AsyncDriver) -> None:
    async with driver.session() as session:
        await session.run(
            "MERGE (:Migration {applied: []})"  # ensure node exists
        )
        applied: list[str] = await _get_applied(session)
        scripts = sorted(MIGRATIONS_PATH.glob("*.cypher"))
        for script in scripts:
            if script.name not in applied:
                cypher = script.read_text()
                await session.run(cypher)
                await _mark_applied(session, script.name)

async def _get_applied(session) -> list[str]:
    result = await session.run("MATCH (m:Migration) RETURN m.applied AS applied")
    record = await result.single()
    return record["applied"] if record else []

async def _mark_applied(session, name: str) -> None:
    await session.run(
        "MATCH (m:Migration) SET m.applied = m.applied + [$name]",
        name=name,
    )
```

Example migration:

```cypher
-- 001_initial_schema.cypher
CREATE CONSTRAINT device_id_unique IF NOT EXISTS
  FOR (d:Device) REQUIRE d.device_id IS UNIQUE;

CREATE CONSTRAINT user_id_unique IF NOT EXISTS
  FOR (u:User) REQUIRE u.user_id IS UNIQUE;

CREATE INDEX activity_category_index IF NOT EXISTS
  FOR (a:Activity) ON (a.category);
```

Run migrations in the lifespan startup, before launching background tasks.

**Confidence: MEDIUM** — Pattern is established community practice; no single authoritative source for Python-native Neo4j migration tooling.

---

## 4. Configuration Management

### Pydantic Settings v2

```python
# src/openguardian/core/config.py
from pathlib import Path
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        secrets_dir="/run/secrets",   # Docker secrets mount point
        case_sensitive=False,
    )

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("changeme")

    # LLM Provider
    llm_provider: str = "openai"           # openai | anthropic | ollama
    llm_model: str = "gpt-4o-mini"
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"

    # Ingestion
    pihole_log_path: Path = Path("/var/log/pihole/pihole.log")
    analysis_interval: int = 300           # seconds between analysis cycles

    # Service
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"

    @property
    def neo4j_auth(self) -> tuple[str, str]:
        return (self.neo4j_user, self.neo4j_password.get_secret_value())

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"openai", "anthropic", "ollama"}
        if v not in allowed:
            raise ValueError(f"llm_provider must be one of {allowed}")
        return v

# Singleton — import this, not the class
settings = Settings()
```

**.env.example** (committed to repo, `.env` is git-ignored):

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme-in-dev

LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

PIHOLE_LOG_PATH=/var/log/pihole/pihole.log
ANALYSIS_INTERVAL=300
```

**Priority order (pydantic-settings):**
1. Constructor arguments
2. Environment variables
3. `.env` file
4. `/run/secrets/` directory (Docker secrets)
5. Field defaults

**Secrets handling:** Use `SecretStr` for API keys — `.get_secret_value()` is required to extract the string, which prevents accidental logging. In production Docker environments, mount secrets via Docker secrets or a bind-mounted secrets directory rather than `.env` files.

**Confidence: HIGH** — Official pydantic-settings documentation.

---

## 5. Testing Strategy

### Test Layout

```
tests/
├── conftest.py                    # shared fixtures
├── unit/
│   ├── test_network_parser.py     # pure parsing logic, no I/O
│   ├── test_anomaly_logic.py      # analysis logic with mocked graph
│   ├── test_risk_loader.py        # markdown parsing
│   └── test_config.py             # settings validation
└── integration/
    ├── test_graph_repository.py   # real Neo4j via testcontainers
    └── test_ingestion_pipeline.py # connector -> graph write
```

---

### Fixture: Neo4j via Testcontainers

```python
# tests/conftest.py
import pytest
from testcontainers.neo4j import Neo4jContainer
from neo4j import AsyncGraphDatabase

@pytest.fixture(scope="session")
def neo4j_container():
    """Shared Neo4j container for all integration tests in the session."""
    with Neo4jContainer("neo4j:5.26-community") as neo4j:
        yield neo4j

@pytest.fixture
async def graph_client(neo4j_container):
    """Fresh async driver per test, pointing at the shared container."""
    driver = AsyncGraphDatabase.driver(
        neo4j_container.get_connection_url(),
        auth=(neo4j_container.NEO4J_USER, neo4j_container.NEO4J_PASSWORD),
    )
    # wipe graph state between tests
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    yield driver
    await driver.close()
```

**Why session-scoped container:** Spinning up a Neo4j container takes ~10-15 seconds. Using `scope="session"` shares one container across all integration tests and resets the graph state per test by wiping nodes.

**Confidence: HIGH** — testcontainers-python official documentation and Neo4j community resources.

---

### Fixture: Mocking the LLM

**Recommended library: `pytest-mockllm`**

It intercepts calls to OpenAI, Anthropic, and Gemini at the HTTP level with no API keys required. Supports cassette recording/replay (record real calls once, replay offline).

```python
# tests/unit/test_anomaly_logic.py
import pytest
from unittest.mock import AsyncMock, patch
from openguardian.analysis.anomaly import AnomalyDetector
from openguardian.analysis.llm.base import LLMProviderProtocol

@pytest.fixture
def mock_llm() -> LLMProviderProtocol:
    """
    Unit test approach: mock at the provider protocol level.
    Faster than pytest-mockllm cassettes when testing logic, not prompt quality.
    """
    llm = AsyncMock(spec=LLMProviderProtocol)
    llm.analyze.return_value = {
        "flags": [],
        "summary": "No anomalies detected.",
        "severity": "informational",
    }
    return llm

async def test_no_anomaly_returns_empty_flags(mock_llm, graph_client):
    detector = AnomalyDetector(graph=graph_client, llm=mock_llm)
    result = await detector.run_cycle()
    assert result.flags == []
    mock_llm.analyze.assert_called_once()
```

For testing **prompt content and LLM response parsing** (not logic), use `pytest-mockllm` cassettes:

```python
# pyproject.toml addition
[tool.pytest.ini_options]
# When MOCKLLM_RECORD=1, calls go to real API and save cassettes
# Otherwise, cassettes replay offline
```

**LLM Provider Protocol:**

```python
# src/openguardian/analysis/llm/base.py
from typing import Protocol, TypedDict

class AnalysisResult(TypedDict):
    flags: list[dict]
    summary: str
    severity: str  # informational | warning | critical

class LLMProviderProtocol(Protocol):
    async def analyze(self, context: str, risk_files: list[str]) -> AnalysisResult: ...
    async def summarize_baseline(self, activity_summary: str) -> str: ...
```

All LLM providers implement this protocol. Tests mock it. Integration tests swap in a real Ollama (local) instance. This is the "provider-agnostic" design the requirements specify.

**Confidence: MEDIUM** — pytest-mockllm PyPI confirmed, API details from project description.

---

### Testing Graph Queries

For unit-testing Cypher query correctness without a running database, mock the driver's `execute_write` / `run` methods:

```python
# tests/unit/test_graph_repository.py
import pytest
from unittest.mock import AsyncMock, patch
from openguardian.graph.repository import GraphRepository

async def test_merge_event_calls_correct_cypher():
    mock_session = AsyncMock()
    mock_driver = AsyncMock()
    mock_driver.session.return_value.__aenter__.return_value = mock_session

    repo = GraphRepository(mock_driver)
    await repo.merge_device_activity(device_id="D01", category="gaming")

    mock_session.execute_write.assert_called_once()
    call_args = mock_session.execute_write.call_args
    assert call_args is not None
```

Integration tests (via testcontainers) verify actual Cypher results. Unit tests verify call signatures and argument passing.

**Confidence: MEDIUM** — Pattern derived from official Python driver mocking documentation and community examples.

---

## 6. Critical Pitfalls

### Pitfall 1: Creating a Neo4j Driver Per Request

**What goes wrong:** Instantiating `AsyncGraphDatabase.driver()` inside a request handler or per-query function.
**Why it happens:** Mirrors SQLAlchemy patterns where `create_engine()` is called once but `Session()` per request. The Neo4j driver does not work the same way — it IS the connection pool.
**Consequences:** Connection exhaustion, slow queries, resource leaks, OOM on resource-constrained hardware.
**Prevention:** Create ONE driver in lifespan startup, inject via dependency. Close it in lifespan shutdown.

### Pitfall 2: Blocking the Event Loop with File I/O

**What goes wrong:** Using `open()` / `f.readline()` synchronously inside an `async def` function in the ingestion loop.
**Consequences:** The entire event loop blocks during disk I/O, stalling all HTTP requests and the analysis loop.
**Prevention:** Always use `aiofiles` for file reads in async context. Even for Pi-hole logs (small reads), this matters on a slow SD card.

### Pitfall 3: Silent Task Death

**What goes wrong:** Using `asyncio.create_task()` without awaiting the result or attaching a callback. If the task raises an uncaught exception, it is silently discarded (logged only as "Task exception was never retrieved").
**Consequences:** Ingestion or analysis stops without any observable failure.
**Prevention:** Use `asyncio.TaskGroup` (Python 3.11+). Any task exception cancels the group and re-raises. Alternatively, add `task.add_done_callback(lambda t: t.result())` to surface exceptions.

### Pitfall 4: APScheduler 4.x Instability

**What goes wrong:** Using APScheduler 4.x in production — the package is marked pre-release/alpha as of early 2026.
**Consequences:** API changes between alpha releases break the service.
**Prevention:** Use APScheduler 3.x with `AsyncIOScheduler` for production stability, or use the `asyncio.sleep` loop pattern shown above (simpler, zero dependencies, no API risk).

### Pitfall 5: Storing LLM API Keys in .env Files on a Shared NAS

**What goes wrong:** `.env` file with `OPENAI_API_KEY` is readable by all users on a shared device, or accidentally committed to git.
**Prevention:** Use `SecretStr` in pydantic-settings so the value is never logged. Add `.env` to `.gitignore`. For multi-user NAS, use Docker secrets (file mounted at `/run/secrets/`) instead of `.env`.

### Pitfall 6: Cypher Injection via Unparameterized Queries

**What goes wrong:** String-formatting user-provided values directly into Cypher strings.
**Prevention:** Always use parameterized queries (`session.run(cypher, param=value)`). Never use f-strings to build Cypher.

---

## 7. Recommended Phase Order Implications

Based on the above, the natural build order is:

1. **Infrastructure first** — Docker Compose + Neo4j running, migrations working, Settings wired
2. **Core data model** — `GraphEvent`, `ConnectorProtocol`, network connector parsing Pi-hole logs
3. **Graph write path** — `GraphClient`, `GraphRepository`, Cypher queries for the entity model
4. **FastAPI skeleton + lifespan** — API boots, ingestion loop runs, graph is being written
5. **LLM integration** — `LLMProviderProtocol`, OpenAI/Anthropic/Ollama adapters, baseline
6. **Analysis pipeline** — anomaly detection, risk file loading, flag generation
7. **API endpoints** — expose graph data, flags, behavior summaries
8. **Notifications** — email alerts on critical flags

This order ensures each layer is independently testable before building on it. The connector protocol being defined in Phase 2 means Discord and future connectors can be built in parallel or later without touching core logic.

---

## Sources

- [PyPA: src layout vs flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [Python Packaging Guide: pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [uv vs Poetry 2026 comparison](https://scopir.com/posts/best-python-package-managers-2026/)
- [Python Dependency Management in 2026 — Cuttlesoft](https://cuttlesoft.com/blog/2026/01/27/python-dependency-management-in-2026/)
- [Neo4j Docker Compose Standalone — Official Ops Manual](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/)
- [Neo4j Python Driver Manual — Installation](https://neo4j.com/docs/python-manual/current/install/)
- [FastAPI Lifespan Events — Official Docs](https://fastapi.tiangolo.com/advanced/events/)
- [asyncio TaskGroup — Python 3.11 docs](https://docs.python.org/3/library/asyncio-task.html#asyncio.TaskGroup)
- [pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [testcontainers-python Neo4j module](https://testcontainers-python.readthedocs.io/en/testcontainers-v4.3.2/modules/neo4j/README.html)
- [pytest-mockllm PyPI](https://pypi.org/project/pytest-mockllm/)
- [aiofiles GitHub](https://github.com/Tinche/aiofiles)
- [Neo4j LLM Knowledge Graph Builder architecture](https://neo4j.com/blog/developer/llm-knowledge-graph-builder-back-end/)
- [Neo4j FastAPI bulk ingest example](https://github.com/prrao87/neo4j-python-fastapi)
- [fastapi-apscheduler4 PyPI](https://pypi.org/project/fastapi-apscheduler4/)
