# Research Summary: OpenGuardian

**Project:** OpenGuardian — local-only network behavior monitoring framework
**Domain:** Child safety / parental monitoring / behavioral anomaly detection
**Researched:** 2026-03-10
**Confidence:** MEDIUM-HIGH

---

## Executive Summary

OpenGuardian is a locally-run Python service that ingests DNS traffic from Pi-hole, constructs a behavioral knowledge graph in Neo4j, and uses an LLM to compare current activity patterns against an established baseline — flagging anomalies for guardian review via email. The system is deliberately local-only: no cloud persistence, no frontend (PoC delivers API + OpenAPI docs), and privacy-preserving by design (raw domain names never leave the ingestion layer). The architecture fits well-understood patterns: FastAPI lifespan for structured concurrency, a plugin-style connector interface for extensibility, and a provider-agnostic LLM adapter backed by LiteLLM + instructor.

The recommended build approach is bottom-up: infrastructure and schema first, then the ingest pipeline, then LLM analysis, then API surface, then notifications. Each layer is independently testable before the next is added. The connector protocol (`typing.Protocol`) is defined early so the Discord connector and any future connectors can be built in parallel without touching core logic. The LLM analysis layer is intentionally narrow — it receives structured natural-language summaries of behavioral aggregates, not raw data — which keeps prompt size manageable, protects privacy, and avoids the well-documented failures of asking LLMs to reason directly over raw graph triples.

The primary risks are operational complexity on constrained hardware (Neo4j memory footprint on a Raspberry Pi), Pi-hole v6 authentication changes (session SIDs, not static keys), and LLM false-positive management (alert fatigue destroys guardian trust). All three have concrete mitigations documented in research. The one meaningful unresolved gap is Ollama structured-output reliability with smaller models — this needs empirical testing before committing to a minimum model requirement for the offline path.

---

## Key Findings

### Recommended Stack

The stack is fully decided. All choices below are locked for PoC. See detailed rationale in individual research files.

**Core technologies:**

| Component | Choice | Version | Rationale |
|---|---|---|---|
| Language | Python | >=3.11 | `asyncio.TaskGroup` (3.11+) for structured concurrency; async neo4j driver requires 3.10+ |
| Package manager | uv | latest | 10-100x faster than pip/poetry; reads standard pyproject.toml; no PyPI publish needed |
| Web framework | FastAPI | >=0.115 | Async-first; lifespan context manager is the correct place to manage background tasks |
| Graph database | Neo4j | 5.26-community (Docker) | User decision; supports temporal queries natively; official async Python driver v6.1 |
| Python driver | neo4j (official) | >=6.1.0 | py2neo is EOL (archived Nov 2023); neomodel is OGM overhead not needed here |
| LLM routing | LiteLLM | >=1.40 | Provider-agnostic (100+ providers); single string change to swap provider; built-in async |
| Structured LLM output | instructor | >=1.5 | Pydantic-validated JSON from any provider; retry logic for malformed outputs |
| Settings | pydantic-settings | >=2.7 | .env + Docker secrets + env vars in priority order; SecretStr prevents key leakage |
| Async file I/O | aiofiles | >=24.1 | Required for non-blocking log reads inside asyncio event loop |
| HTTP client | httpx | >=0.28 | Async HTTP for Pi-hole API and LLM provider calls |
| Scheduling (PoC) | asyncio.sleep loop | stdlib | Zero dependencies; avoids APScheduler 4.x pre-release instability |
| Email | smtplib + jinja2 | stdlib + >=3.1 | No external email library needed for local SMTP relay |
| Testing: graph | testcontainers[neo4j] | >=4.9 | Real Neo4j container per test session; ~10-15s startup amortized across session |
| Testing: LLM | pytest-mockllm | >=0.2 | HTTP-level interception; cassette record/replay; no API keys in CI |
| Build backend | hatchling | latest | Works with uv; standard PEP 517/518 |

**Explicitly excluded:**
- `py2neo` — EOL, no security patches
- `APScheduler 4.x` — pre-release/alpha as of early 2026; use asyncio.sleep loop for PoC
- `networkx-temporal` — dns-behavior agent recommended it for in-memory graph; overridden by user decision to use Neo4j
- `LangChain` — adds 50+ transitive dependencies with no benefit for OpenGuardian's narrow LLM surface (summarize + detect anomaly + return JSON)
- `Celery` — requires Redis/RabbitMQ broker; incompatible with local-first constraint
- `PyOD` — ML anomaly detection library unnecessary since LLM handles interpretation

### Pi-hole Ingestion Strategy

Pi-hole v6 (released February 2025) is a breaking change from v5. **The API no longer uses a static `?auth=<key>` token.** Authentication is now session-based: POST to `/api/auth`, receive a SID, include it as `X-FTL-SID` header on subsequent requests. The SID stays alive while the poller is active; re-authenticate on 401.

For PoC: use the REST API (`GET /api/queries` with `from=<last_timestamp>`), not direct SQLite access. The API decouples OpenGuardian from Pi-hole's internal storage format. Only ingest queries with `status IN (2, 3)` — forwarded and cached (allowed). Blocked queries distort the behavioral baseline and should be tracked separately as a security signal if needed.

If co-located with Pi-hole (same host), direct SQLite access to `/etc/pihole/pihole-FTL.db` is an alternative. Critical: enable `PRAGMA journal_mode=WAL` on connection open, before any SELECT, or reads will fail with `database is locked` during FTL write operations.

### DNS Categorization

Build a local SQLite category map populated from StevenBlack Unified Hosts and hagezi/dns-blocklists at install time. The 20-category taxonomy (gaming, social, messaging, video, education, adult, vpn_proxy, darkweb, malware, etc.) is the right granularity for behavioral analysis. Strip `cdn_infra` and `advertising` categories before graph construction — they generate noise without behavioral signal.

Unknown domains default to `unknown_new` without blocking the pipeline. An `unknown_domain_ratio` spike (especially during night hours) is itself a behavioral signal. Do not block on unknown domain resolution.

### Graph Schema

The graph has a strict two-layer data model:

- **Layer 1 (private, never exposed):** Raw DNS events with domain stored as a salted SHA-256 hash and TLD only. Purged on a rolling 30-day window.
- **Layer 2 (guardian-visible):** Behavioral graph of `User`, `Device`, `ActivityCategory`, `TimeSlot`, and `Session` nodes. No domain references.

The pipeline is one-directional: raw events → categorization → sessions → graph. Raw events are never read back from the application layer once graph construction is complete.

Key Neo4j schema decisions:
- `VISITED` relationships use `CREATE` (append-only event log), not `MERGE`
- `Device`, `Domain`, `Category` nodes use `MERGE` (idempotent upsert)
- Batch ingest with `UNWIND $events AS e` — never one Cypher query per event (critical performance requirement on constrained hardware)
- All `CREATE CONSTRAINT` / `CREATE INDEX` statements require `IF NOT EXISTS` — without it, startup crashes after first run
- Use Neo4j native `datetime()` types on timestamps, not Unix integers as strings

### LLM Analysis Architecture

The LLM pipeline is: Neo4j Cypher aggregates → `GraphSummarizer` (structured natural language, not raw triples) → `RiskLoader` (keyword-filtered Known Risk files) → `PromptBuilder` → `LiteLLMProvider.analyze(response_schema=AnalysisResult)` → `EventRouter` (critical → immediate email, warning → weekly digest, informational → log only).

The LLM receives narrative summaries of behavioral statistics, never raw domain names, hashes, or IP addresses. Total prompt budget is ~1600–2900 tokens — fits within GPT-4o-mini's context and is compatible with `llama3.1:8b` (recommended minimum for Ollama structured output; `llama3.2:3b` may produce malformed JSON for complex schemas).

Temperature settings: 0.0 for anomaly analysis (deterministic flags), 0.2 for baseline summarization, 0.4 for guardian report narrative.

Known Risk files use keyword pre-filtering on `## Trigger Categories` sections — no vector embeddings or semantic search needed for a library of <50 files. Files must not be chunked; each file is a single coherent behavioral pattern.

**Critical research caveat (HIGH confidence):** 2025 peer-reviewed research shows LLMs struggle at grooming detection from conversation content. OpenGuardian avoids this problem by analyzing behavioral metadata only. The design is correct. However, false positive management remains critical — the system prompt explicitly instructs the model to prefer fewer, higher-confidence flags over many low-confidence ones. Alert fatigue destroys guardian trust.

### Privacy Architecture

Four-layer privacy enforcement:

1. **Ingestion:** Domain names hashed with a per-install salt before storage (`hashlib.sha256`). Hash never surfaced in outputs.
2. **Graph construction:** Graph built from category-level events only. Domain nodes are internal to the raw event store, not part of the behavioral graph.
3. **LLM prompts:** Prompts contain only narrative behavioral summaries (durations, session counts, category distributions, z-scores). No domains, no hashes, no IPs.
4. **Email / API outputs:** Same rule as LLM prompts. Weekly digest and critical alerts contain category names, durations, and LLM explanations only.

Each connector's `connector.json` manifest declares a `privacy_class` for each field (`raw_private`, `derived_ok`, `aggregate_ok`, `pseudonymous`). This classification gates what can appear in guardian-visible surfaces.

### Architecture Approach

OpenGuardian runs three concurrent long-running behaviors in a single asyncio process: continuous log ingestion (tail Pi-hole API, parse, write to graph), periodic analysis (pull graph aggregates, run LLM, generate flags), and the FastAPI HTTP server. All three launch inside `FastAPI(lifespan=...)` using `asyncio.TaskGroup` (Python 3.11+) for structured concurrency — if either background task crashes, the group cancels the other and re-raises instead of silently dropping tasks.

**Major components:**

1. **ConnectorRegistry** — discovers and loads connector plugins from `/connectors/*/connector.json` at startup via `importlib.util`; exposes them as a FastAPI `app.state` dependency
2. **NetworkConnector** — Pi-hole v6 API client; authenticates with SID; polls incrementally using `from=<last_timestamp>`; normalizes to `GraphEvent`
3. **GraphClient / GraphRepository** — single `AsyncDriver` instance per process (connection pool); `MERGE` for nodes, `CREATE` for visit relationships; batched `UNWIND` ingestion
4. **GraphSummarizer** — runs Cypher aggregates; renders structured natural language; produces baseline and current-window summaries for LLM
5. **RiskLoader** — scans `/known-risks/*.md`; filters by `## Trigger Categories` keyword match against active categories
6. **LiteLLMProvider** — wraps `litellm.acompletion()` + `instructor`; implements `LLMProviderProtocol`; provider selected by `llm_model` config string (e.g., `"openai/gpt-4o-mini"`, `"ollama/llama3.1"`)
7. **AnomalyDetector** — orchestrates GraphSummarizer + RiskLoader + LiteLLMProvider; returns `AnalysisResult` (Pydantic); feeds EventRouter
8. **EventRouter** — routes `AnalysisResult` flags to email notifications (critical) or digest queue (warning)
9. **FastAPI API layer** — exposes `/api/v1/` endpoints for behavior summaries, anomaly flags, devices; OpenAPI docs at `/docs`

### Critical Pitfalls

1. **Pi-hole v6 session auth** — v5 used `?auth=<static_key>`; v6 requires POST to `/api/auth`, cache the SID, include as `X-FTL-SID` header. Any v5 code or docs are wrong. Re-authenticate on 401.

2. **One Neo4j driver per process, not per request** — `AsyncGraphDatabase.driver()` IS the connection pool. Creating it per request causes connection exhaustion and OOM on constrained hardware. Create once in lifespan startup, inject via `app.state` or `Depends`.

3. **Silent task death via `create_task`** — Background tasks created with bare `asyncio.create_task()` silently discard exceptions. Use `asyncio.TaskGroup` (Python 3.11+) so any task crash cancels the group and re-raises.

4. **APScheduler 4.x instability** — Marked pre-release/alpha as of early 2026. Use the `asyncio.sleep` loop pattern for PoC (zero dependencies, no API risk). APScheduler 3.x `AsyncIOScheduler` is a fallback if cron-style scheduling is needed.

5. **Blocking the event loop with file I/O** — Synchronous `open()` / `readline()` inside `async def` stalls all HTTP requests and analysis. Always use `aiofiles` for file reads. Especially relevant on SD-card-backed Raspberry Pi hardware where disk I/O is slow.

6. **MERGE on every node per event** — At 1000 DNS queries/minute, single-event Cypher is a bottleneck. Batch with `UNWIND $events AS e MERGE ...`. Recommended batch size: 500–1000 events per transaction.

7. **`CREATE CONSTRAINT` without `IF NOT EXISTS`** — Crashes on every restart after first run. All schema setup statements require `IF NOT EXISTS`.

8. **Connector `importlib` relative imports** — Connector modules loaded via `importlib.util.spec_from_file_location` are not part of the package tree. Relative imports inside connector modules (`from .schemas import ...`) will fail. Use absolute imports and ensure project root is on `sys.path`.

9. **LLM false positives destroying guardian trust** — Optimizing for sensitivity inflates false positives. System prompt must explicitly instruct the model to prefer fewer, higher-confidence flags. This is a design constraint, not a tuning detail.

---

## Implications for Roadmap

### Phase 1: Infrastructure Foundation
**Rationale:** Nothing else runs without Neo4j, settings, and schema. Establish the operational baseline before writing any application code.
**Delivers:** Docker Compose with Neo4j running; `Settings` (pydantic-settings) wired; Cypher migration runner executing `001_initial_schema.cypher` at startup; `GraphClient` with `verify_connectivity()`.
**Avoids:** Pitfall of driver-per-request (design the single-driver pattern from day one); `IF NOT EXISTS` schema pattern locked in from first migration.
**Research flag:** Standard patterns — skip phase research.

### Phase 2: Core Data Model and Connector Protocol
**Rationale:** Define `GraphEvent` and `ConnectorProtocol` before any connector implementation. This contract allows the network and Discord connectors to be built in parallel and tested independently.
**Delivers:** `GraphEvent` Pydantic model; `ConnectorProtocol` (structural `typing.Protocol`); `ConnectorRegistry` with `importlib` discovery; `connector.json` manifest schema; DNS category map (SQLite, seeded from StevenBlack/hagezi); domain hashing utility.
**Avoids:** Connector tight coupling; importlib relative-import pitfall (define import rules here).
**Research flag:** Standard patterns for Protocol and importlib — skip phase research.

### Phase 3: Pi-hole Ingestion Pipeline
**Rationale:** The ingestion pipeline is the data source for everything else. Must be working and writing to Neo4j before analysis or API can be developed.
**Delivers:** `NetworkConnector` with Pi-hole v6 SID auth; incremental polling (`from=<last_timestamp>`); session construction (15-minute gap model); `GraphRepository` with `UNWIND` batch ingest; `aiofiles`-backed log tail; `asyncio.TaskGroup` lifespan wiring.
**Avoids:** Pi-hole v5 auth assumptions (SID-based auth from day one); blocking event loop (aiofiles required); MERGE-per-event bottleneck (UNWIND batching).
**Research flag:** Pi-hole v6 API behavior is well-documented in research — skip phase research. Validate session expiry behavior empirically during implementation.

### Phase 4: FastAPI Skeleton and Lifespan Wiring
**Rationale:** Wire the FastAPI app with lifespan so ingestion and (later) analysis run as background tasks. Establishes the API server baseline that all endpoint work builds on.
**Delivers:** `FastAPI(lifespan=...)` booting ingestion loop; Neo4j driver initialized and verified in lifespan startup; migrations running at startup; `/health` and `/docs` endpoints live; Pydantic response schemas for v1 API surface.
**Research flag:** Standard FastAPI patterns — skip phase research.

### Phase 5: LLM Analysis Pipeline
**Rationale:** Build on a running ingestion pipeline with real data in Neo4j. Analysis requires graph data to be meaningful.
**Delivers:** `GraphSummarizer` (Cypher aggregates to structured narrative); `RiskLoader` (keyword pre-filter on `## Trigger Categories`); `LiteLLMProvider` + `instructor` with `LLMProviderProtocol`; `AnalysisResult` / `AnomalyFlag` Pydantic schemas; `AnomalyDetector.run_cycle()`; onboarding baseline computation (7-day aggregate); `asyncio.sleep` analysis loop wired into lifespan.
**Avoids:** Raw graph dump to LLM (use narrative summaries only); false positive inflation (system prompt constraints baked in from first iteration).
**Research flag:** Ollama structured-output reliability with `llama3.1:8b` needs empirical validation — this is the one unresolved gap. May need phase research if Ollama is a first-class PoC target.

### Phase 6: API Endpoints
**Rationale:** API surface is the PoC's deliverable (no frontend). Build after analysis pipeline exists so endpoints return real data.
**Delivers:** `GET /api/v1/devices` and `GET /api/v1/devices/{id}/activity`; `GET /api/v1/alerts` (anomaly flags); `GET /api/v1/behavior/{device_id}/baseline`; `POST /api/v1/onboarding`; `POST /api/v1/risks` (upload Known Risk files); OpenAPI docs fully populated with examples.
**Research flag:** Standard FastAPI patterns — skip phase research.

### Phase 7: Notifications
**Rationale:** Final PoC deliverable. Builds on anomaly flags from Phase 5.
**Delivers:** `EventRouter` routing critical flags to immediate email; smtplib + Jinja2 HTML email templates (`critical_alert.html`, `weekly_digest.html`); `asyncio.sleep` digest loop (Monday 08:00 cadence); privacy enforcement on email content (no domains, no hashes).
**Research flag:** Standard smtplib + Jinja2 patterns — skip phase research. SMTP configuration for various providers (Gmail, local Postfix) may need lookup.

### Phase Ordering Rationale

- Phases 1-2 are pure infrastructure/contracts with no external dependencies — they can be built and tested in isolation.
- Phase 3 (ingestion) depends on Phase 2 (data model) and Phase 1 (Neo4j). It must produce data before Phase 5 (analysis) is meaningful.
- Phase 4 (FastAPI skeleton) can be developed in parallel with Phase 3 and wired together at the end of Phase 3.
- Phase 5 (LLM) depends on Phase 3 data being in Neo4j. The `LLMProviderProtocol` and `AnalysisResult` schemas can be designed in parallel, but the full pipeline needs real graph data to validate.
- Phases 6 and 7 are API surface work that adds no new architectural risk. They are deferred to avoid over-building before the core pipeline is validated.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 5 (LLM Analysis):** Ollama structured-output reliability with `llama3.1:8b` for the `AnalysisResult` schema is unvalidated. If Ollama is a PoC target, test instructor retry behavior and schema complexity tolerance before building the full pipeline.

Phases with standard patterns (skip research-phase):
- **Phase 1:** Docker Compose + Neo4j deployment is fully documented in official Neo4j Operations Manual.
- **Phase 2:** `typing.Protocol` and `importlib` discovery are standard Python patterns.
- **Phase 3:** Pi-hole v6 API is fully documented. Batch UNWIND ingest is standard Neo4j practice.
- **Phase 4:** FastAPI lifespan + `asyncio.TaskGroup` is documented in official FastAPI and Python asyncio docs.
- **Phase 6:** Standard FastAPI endpoint patterns.
- **Phase 7:** Standard smtplib + Jinja2 patterns.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack choices | HIGH | All core libraries verified via official docs; version requirements confirmed |
| Pi-hole v6 API | HIGH | Official Pi-hole v6 release notes + API auth docs; breaking changes from v5 confirmed |
| Neo4j patterns | HIGH | Official Neo4j Python Driver Manual; MERGE/CREATE/UNWIND patterns from official performance docs |
| FastAPI lifespan + TaskGroup | HIGH | Official FastAPI docs + Python 3.11 asyncio docs |
| LLM adapter (LiteLLM + instructor) | HIGH | Official docs; 3M+ monthly downloads for instructor; LiteLLM is OpenAI Agents SDK backend |
| Privacy architecture | HIGH | Two-layer data model and salt hashing patterns from 2025 arxiv research |
| DNS categorization taxonomy | HIGH | Cloudflare official category list; StevenBlack and hagezi are established community references |
| Session construction (15-min gap) | MEDIUM-HIGH | Standard from web behavioral studies; no authoritative source specific to DNS contexts |
| Prompt engineering for anomaly detection | HIGH | CoT + structured output pattern validated in multiple 2025 academic papers |
| LLM accuracy on grooming detection | LOW | Research explicitly finds "no models clearly appropriate" for grooming detection from content; OpenGuardian avoids worst case by analyzing metadata, not content |
| Ollama structured output (small models) | LOW | instructor has retry logic but small-model JSON reliability is empirically unknown for this schema complexity |
| Neo4j migration tooling | MEDIUM | Custom Cypher runner is community practice; no single authoritative Python-native source |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Ollama minimum model floor:** `llama3.2:3b` may produce malformed JSON for the `AnalysisResult` schema. Test `llama3.1:8b` empirically in Phase 5. If structured output fails, fall back to `gpt-4o-mini` as the minimum viable local-first alternative.
- **Pi-hole session expiry behavior:** SID stays alive while the poller is active. Behavior on idle timeout needs empirical validation. Implement re-authentication on 401 from day one.
- **Baseline robustness on atypical weeks:** A 7-day baseline established during school holidays or illness will corrupt anomaly detection. The requirement document flags this as open. Mitigation: allow guardian to mark baseline days as atypical via API before committing to a full baseline refresh mechanism.
- **VPN/DoH evasion:** If a device switches to DNS-over-HTTPS or a VPN, Pi-hole sees no queries. Detection heuristic: if `unknown_domain_ratio` drops to near-zero AND query volume drops significantly vs. baseline, surface as a warning. Not a solution — a proxy signal.
- **Multi-category session primary assignment:** When gaming and social queries interleave in a session window, `primary_category` = category with most queries; secondary categories stored in session metadata. Decide and document this policy before building session construction.
- **LLM response audit log:** For a child-safety system, every LLM call should be logged (full prompt, output, timestamp) for guardian review and false-positive debugging. Build this into `LiteLLMProvider` in Phase 5, not as a Phase 6+ afterthought.

---

## Sources

### Primary (HIGH confidence)
- [Neo4j Python Driver Manual](https://neo4j.com/docs/python-manual/current/) — driver initialization, async patterns, MERGE/CREATE/UNWIND, constraint syntax
- [Neo4j Operations Manual — Docker Compose Standalone](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/) — Docker Compose config, memory sizing
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) — lifespan context manager pattern
- [Python 3.11 asyncio TaskGroup](https://docs.python.org/3/library/asyncio-task.html#asyncio.TaskGroup) — structured concurrency
- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — settings priority order, SecretStr
- [Pi-hole v6 Release Notes](https://pi-hole.net/blog/2025/02/18/introducing-pi-hole-v6/) — breaking changes from v5
- [Pi-hole API Authentication Docs](https://docs.pi-hole.net/api/auth/) — SID auth flow
- [LiteLLM docs](https://docs.litellm.ai/docs/) — provider routing, async
- [instructor + LiteLLM integration](https://python.useinstructor.com/integrations/litellm/) — structured output pattern
- [Cloudflare Domain Categories (official)](https://developers.cloudflare.com/cloudflare-one/traffic-policies/domain-categories/) — taxonomy reference

### Secondary (MEDIUM confidence)
- [networkx-temporal documentation (Dec 2025)](https://networkx-temporal.readthedocs.io/) — temporal graph APIs (noted; overridden by Neo4j decision)
- [RAG chunking strategies (Weaviate 2025)](https://weaviate.io/blog/chunking-strategies-for-rag) — risk file non-chunking rationale
- [LLM anomaly detection with CoT (MDPI 2025)](https://www.mdpi.com/2076-3417/15/19/10384) — chain-of-thought accuracy claims
- [Privacy-Preserving Anonymization via Salt Hashing (arxiv 2507.21904)](https://arxiv.org/abs/2507.21904) — domain hashing design
- [testcontainers-python Neo4j module](https://testcontainers-python.readthedocs.io/) — test fixture pattern

### Tertiary (LOW confidence / needs empirical validation)
- [LLM grooming detection — ACM 2024/2025](https://dl.acm.org/doi/fullHtml/10.1145/3655693.3655694) — accuracy caveats; confirms metadata-only approach is safer
- [Early Detection of Online Grooming with LLMs (ResearchGate 2025)](https://www.researchgate.net/publication/391745641_Early_Detection_of_Online_Grooming_with_Language_Models) — consistency of "no models clearly appropriate" finding

---
*Research completed: 2026-03-10*
*Conflicts resolved: APScheduler 4.x → asyncio.sleep loop; networkx-temporal → Neo4j (user decision)*
*Ready for roadmap: yes*
