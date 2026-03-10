# OpenGuardian — Roadmap

## Milestone 1: Core Pipeline PoC

---

### Phase 1: Infrastructure Foundation

**Goal:** A single `docker compose up` boots Neo4j and the Python service skeleton, schema migrations run at startup, and the service can verify database connectivity before accepting any work.

**Requirements covered:** F3.1, NF2, NF6

#### Plans

1. **Docker Compose stack** — `docker-compose.yml` with Neo4j 5.26-community (memory-bounded for constrained hardware), named volume for persistence, healthcheck; `.env.example` with all required vars
2. **Settings module** — `src/openguardian/config/settings.py` using `pydantic-settings` v2; `SecretStr` for `NEO4J_PASSWORD`, `LLM_API_KEY`; loads from `.env` → environment → Docker secrets in priority order
3. **Cypher migration runner** — `src/openguardian/db/migrations.py`; reads `migrations/*.cypher` files in lexicographic order; executes each with `IF NOT EXISTS` guard; records applied migrations; idempotent on every restart
4. **GraphClient** — `src/openguardian/db/client.py`; single `AsyncDriver` instance (not per-request); `verify_connectivity()` called at startup; `close()` called at shutdown

**UAT:**
1. `docker compose up` produces a healthy Neo4j instance accessible at `bolt://localhost:7687`; the Python service starts and logs `"Neo4j connectivity verified"` without error
2. Stopping and restarting the service re-runs migrations without error (`IF NOT EXISTS` prevents duplicate constraint failures)
3. `OPENGUARDIAN_NEO4J__PASSWORD=wrongpassword docker compose up` causes the service to log a connection error and exit with a non-zero code rather than hanging silently

---

### Phase 2: Core Data Model and Connector Protocol

**Goal:** The `GraphEvent` contract and `ConnectorProtocol` are defined and tested so that all subsequent connectors and graph writes share a single, type-safe interface with privacy enforcement baked in.

**Requirements covered:** F1.1, F1.2, F1.3, F1.4, F1.6, F2.1, F2.2, F2.3, F2.4, NF1, NF3, NF7

#### Plans

1. **`GraphEvent` Pydantic model** — `src/openguardian/models/graph_event.py`; fields: `timestamp` (ISO 8601), `source`, `user_id`, `device_id`, `event_type`, `category`, `metadata`; zero `Any` types; `model_config` with `frozen=True`
2. **`ConnectorProtocol`** — `src/openguardian/connectors/protocol.py`; structural `typing.Protocol` (not ABC) with `start()`, `stop()`, `poll()` → `AsyncIterator[GraphEvent]`; `connector_id` property
3. **`ConnectorRegistry`** — `src/openguardian/connectors/registry.py`; discovers plugins from `/connectors/*/connector.json` at startup using `importlib.util.spec_from_file_location`; validates manifest against `ConnectorManifest` Pydantic schema; exposes `registry.list_connectors()`; uses absolute imports (no relative imports inside plugin modules)
4. **`connector.json` manifest schema** — `src/openguardian/connectors/manifest.py`; `ConnectorManifest` Pydantic model: `name`, `version`, `data_fields` list, `privacy_class` per field (`raw_private | derived_ok | aggregate_ok | pseudonymous`)
5. **DNS category map** — `src/openguardian/categorization/category_map.py`; SQLite DB seeded from StevenBlack/hagezi blocklists via `scripts/seed_categories.py`; 20-category taxonomy; `categorize(domain: str) -> str` returns category or `"unknown_new"`; domains absent from table return `"unknown_new"` without blocking
6. **Domain hashing utility** — `src/openguardian/privacy/hashing.py`; `hash_domain(domain: str, salt: str) -> str` using `hashlib.sha256`; per-installation salt read from settings; used exclusively in the ingestion layer — never surfaced in outputs

**UAT:**
1. `ConnectorRegistry` discovers a test connector dropped into `/connectors/test_connector/` at runtime without restarting; `registry.list_connectors()` returns the new connector
2. Attempting to instantiate a `GraphEvent` with an unrecognized field type raises a `ValidationError` (Pydantic v2 strict mode)
3. Calling `categorize("google.com")` returns a category string from the taxonomy; calling `categorize("nonexistent-xyzabc123.io")` returns `"unknown_new"` — neither call raises an exception

---

### Phase 3: Pi-hole Ingestion Pipeline

**Goal:** The service continuously polls Pi-hole v6, normalizes allowed DNS queries to `GraphEvent` records, constructs sessions, and writes behavioral graph nodes and relationships to Neo4j in batches — without blocking the asyncio event loop.

**Requirements covered:** F1.5, F3.2, F3.3, F3.4, F3.5, NF4

#### Plans

1. **`NetworkConnector` (Pi-hole v6 client)** — `src/openguardian/connectors/network/connector.py`; POST to `/api/auth` for SID; `X-FTL-SID` header on all subsequent requests; `GET /api/queries?from=<last_timestamp>` for incremental poll; filters `status IN (2, 3)` (forwarded + cached only); re-authenticates on 401; checkpoint persisted to settings or SQLite so polling survives restarts
2. **`GraphEvent` normalization** — maps Pi-hole query fields to `GraphEvent`; calls `hash_domain()` on domain before any storage; calls `categorize()` to assign `category`; strips `cdn_infra` and `advertising` categories before emitting
3. **Session construction** — `src/openguardian/graph/sessions.py`; groups `GraphEvent` records within a 30-minute idle window into a `Session`; `primary_category` = category with most queries in window; secondary categories stored in session metadata; produces `Session` Pydantic model for graph write
4. **`GraphRepository` with UNWIND batch ingest** — `src/openguardian/db/repository.py`; `MERGE` for `User`, `Device`, `Activity` (category), `TimeSlot` nodes; `CREATE` for `VISITED` relationships (append-only event log); `UNWIND $events AS e` batch writes (500-event batch ceiling); `MERGE` uses `IF NOT EXISTS`-guarded constraints from Phase 1 migrations; native `datetime()` types on all timestamps
5. **Ingestion loop** — `src/openguardian/ingestion/loop.py`; `async def run_ingestion_loop(connector, repository)` with `asyncio.sleep` between polls; uses `aiofiles` for any file-backed log reads; wired into `asyncio.TaskGroup` inside FastAPI lifespan (Phase 4 wires this)

**UAT:**
1. With a live Pi-hole v6 instance pointed at the connector, querying `MATCH (d:Device)-[:ACCESSED]->(a:Activity) RETURN d, a LIMIT 10` in Neo4j Browser returns real nodes within two poll cycles of the service starting
2. Killing and restarting the service resumes from the last checkpoint timestamp — no duplicate `VISITED` relationships are created for already-ingested events
3. Deliberately expiring the Pi-hole SID (or setting a wrong password) causes the connector to log a re-authentication attempt and recover without crashing the ingestion loop

---

### Phase 4: FastAPI Skeleton and Lifespan Wiring

**Goal:** The FastAPI application boots with all long-running tasks (ingestion loop, future analysis loop) managed inside `asyncio.TaskGroup` via the lifespan context manager, and `/health` returns the verified status of all subsystems.

**Requirements covered:** F7.1, F7.2, F7.4, NF3, NF6

#### Plans

1. **FastAPI application factory** — `src/openguardian/api/app.py`; `create_app() -> FastAPI`; `lifespan` context manager using `asyncio.TaskGroup`; Neo4j `AsyncDriver` created once and stored on `app.state`; migrations executed before driver verification; ingestion loop task launched in `TaskGroup`; any task crash cancels the group and re-raises (no silent task death)
2. **`/health` endpoint** — `GET /api/v1/health`; response model `HealthResponse` (Pydantic v2): `status`, `neo4j_connected: bool`, `llm_available: bool`, `connector_count: int`, `version: str`; performs live `verify_connectivity()` check on each request; returns 503 if Neo4j is unreachable
3. **Pydantic response schemas** — `src/openguardian/api/schemas/`; base response models for all planned v1 endpoints (empty implementations allowed — no `Any` fields, all fields typed); OpenAPI docs at `/docs` populated from models at startup
4. **Dependency injection wiring** — `src/openguardian/api/dependencies.py`; `get_driver()`, `get_registry()`, `get_repository()` FastAPI `Depends` factories pulling from `app.state`; used by all endpoint routers

**UAT:**
1. `curl http://localhost:8000/api/v1/health` returns `{"status": "ok", "neo4j_connected": true, ...}` with HTTP 200 when Neo4j is running; returns HTTP 503 when Neo4j container is stopped
2. `http://localhost:8000/docs` renders the full OpenAPI UI with all planned endpoint stubs visible and their Pydantic response schemas documented
3. Raising an unhandled exception inside the ingestion loop task causes the entire FastAPI process to exit (not silently continue) — verified by injecting a deliberate `raise RuntimeError` into the loop

---

### Phase 5: LLM Analysis Pipeline

**Goal:** The service runs a configurable analysis cycle that reads behavioral aggregates from Neo4j, constructs a privacy-safe narrative prompt enriched with relevant Known Risk files, calls the LLM via LiteLLM + instructor, returns a validated `AnalysisResult`, and logs every call to an audit trail — with graceful degradation if the LLM is unreachable.

**Requirements covered:** F4.1, F4.2, F4.3, F4.4, F4.5, F4.6, F5.1, F5.2, F5.3, F5.4, F5.5, F5.6, F5.7, F5.8, F6.1, F6.2, F6.3, F6.4, F6.5, NF1, NF4, NF5, NF8

#### Plans

1. **`LLMProviderProtocol` + `LiteLLMProvider`** — `src/openguardian/llm/provider.py`; structural `typing.Protocol` with `analyze(prompt: str, response_schema: type[T]) -> T`; `LiteLLMProvider` wraps `litellm.acompletion()` + `instructor`; provider selected by `llm_model` config string (e.g., `"openai/gpt-4o-mini"`, `"ollama/llama3.1"`); `temperature=0.0` for anomaly analysis, `temperature=0.2` for baseline summarization; full prompt + response + timestamp written to audit log on every call; `F5.8` degradation: `LLMUnavailableError` caught by caller, analysis skipped, flag status set to `llm_unavailable`
2. **`GraphSummarizer`** — `src/openguardian/analysis/summarizer.py`; runs Cypher aggregate queries (session count, median duration, category distribution, peak hours, `unknown_domain_ratio`); serializes to structured narrative text; zero raw domain strings, zero hashes in output; produces `BaselineSummary` and `CurrentWindowSummary` Pydantic models
3. **`RiskLoader`** — `src/openguardian/analysis/risk_loader.py`; scans `/known-risks/*.md` using `aiofiles`; parses `## Trigger Categories` section; keyword pre-filter matches trigger categories against active category set from current graph window; returns list of full file contents (no chunking); re-loads on every cycle (no restart required); starter library: `risk_grooming_roblox.md`, `risk_grooming_discord.md`, `risk_radicalization_discord.md`
4. **`AnomalyDetector`** — `src/openguardian/analysis/detector.py`; orchestrates `GraphSummarizer` + `RiskLoader` + `LiteLLMProvider`; builds prompt from baseline summary + current window summary + filtered risk files; instructs model to prefer fewer high-confidence flags (false-positive mitigation in system prompt); returns `AnalysisResult` (list of `AnomalyFlag`: `severity`, `category`, `reasoning`, `risk_file_cited`); no flags generated during onboarding period (checked before calling LLM)
5. **Onboarding state machine** — `src/openguardian/onboarding/state.py`; `OnboardingState` Pydantic model persisted to Neo4j or SQLite: `device_id`, `user_name`, `age`, `school_schedule`, `started_at`, `status` (`onboarding | active`); `POST /api/v1/onboarding/setup` writes state; 7-day window computed from `started_at`; at day 7, `AnomalyDetector.compute_baseline()` runs, `status` flips to `active`; daily narrative summaries generated during onboarding via LLM (`temperature=0.4`)
6. **Analysis loop + `POST /risk-files`** — `src/openguardian/analysis/loop.py`; `asyncio.sleep` loop defaulting to 6-hour interval (configurable); wired into FastAPI lifespan `TaskGroup` alongside ingestion loop; `POST /api/v1/risk-files` writes uploaded file to `/known-risks/` directory; `GET /api/v1/risk-files` lists loaded files with metadata

**UAT:**
1. With 24+ hours of ingested data in Neo4j, `GET /api/v1/anomalies` returns a list (possibly empty) of `AnomalyFlag` objects with `severity`, `category`, and `reasoning` fields — no domain strings appear anywhere in the response
2. Setting `LLM_API_KEY` to an invalid value causes `GET /api/v1/health` to return `"llm_available": false` and `GET /api/v1/anomalies` to return an empty list with a `"llm_unavailable"` status field — ingestion continues unaffected
3. Every analysis cycle produces a new entry in the audit log containing the full prompt, the raw LLM response, and a timestamp; the audit log contains no domain names or domain hashes

---

### Phase 6: Full API Surface

**Goal:** All PoC API endpoints are implemented, return real data from Neo4j and the analysis pipeline, and are fully documented in the OpenAPI UI — making the API the complete deliverable of the PoC.

**Requirements covered:** F3.6, F7.3 (all endpoints), NF1, NF3

#### Plans

1. **Behavior endpoints** — `GET /api/v1/behavior/summary` returns `BehaviorSummary` (session count, category distribution, peak hours, `unknown_domain_ratio`) from `GraphSummarizer`; `GET /api/v1/behavior/baseline` returns `BaselineSummary` from stored onboarding result; all fields category-level only — no domains
2. **Anomaly endpoints** — `GET /api/v1/anomalies` returns paginated list of `AnomalyFlag` with severity filter and date range query params; `GET /api/v1/anomalies/{id}` returns single flag with full `reasoning` text and `risk_file_cited`; stored in Neo4j or SQLite with stable UUIDs
3. **Device + connector endpoints** — `GET /api/v1/connectors` returns list of registered connectors with `status` (`running | stopped | error`) and last-poll timestamp from `ConnectorRegistry`; `GET /api/v1/onboarding/status` returns current `OnboardingState` including days remaining and whether baseline is confirmed
4. **OpenAPI polish** — add `response_model_exclude_none=True` to all endpoints; add example values to all Pydantic schemas via `model_config` or `Field(examples=...)`; ensure `/docs` renders a complete, usable API reference with no `{}` or untyped fields

**UAT:**
1. `GET /api/v1/behavior/summary` returns a valid JSON response with category names and numeric session counts; `jq '.categories | keys'` on the response returns strings from the taxonomy (e.g., `"gaming"`, `"education"`) — never a domain name or hash
2. `GET /api/v1/anomalies?severity=critical` returns only `AnomalyFlag` objects where `severity == "critical"`; `GET /api/v1/anomalies/{id}` for a valid ID returns the full reasoning text
3. The `/docs` Swagger UI shows every endpoint with request/response schemas, all fields typed (no `object` or `{}` types visible), and at least one example value per response model

---

### Phase 7: Email Notifications

**Goal:** Critical anomaly flags trigger an immediate email to the configured guardian address, and a weekly digest summarizes informational and warning flags — both using Jinja2 HTML templates that contain only category-level information.

**Requirements covered:** F8.1, F8.2, F8.3, F8.4, F8.5, NF1

#### Plans

1. **`EmailNotifier`** — `src/openguardian/notifications/email.py`; `smtplib.SMTP` / `SMTP_SSL` with config from settings (`smtp_host`, `smtp_port`, `smtp_username`, `smtp_password` as `SecretStr`, `recipient_address`, `notification_level`); `send_critical_alert(flag: AnomalyFlag)` and `send_weekly_digest(flags: list[AnomalyFlag])`; delivery failures logged at `ERROR` level and swallowed — do not crash the service (F8.5)
2. **Jinja2 email templates** — `src/openguardian/notifications/templates/critical_alert.html` and `weekly_digest.html`; critical alert: severity badge, category, LLM reasoning, timestamp; weekly digest: table of flags grouped by severity; both templates: zero domain names, zero hashes, zero IPs — category names and plain-English reasoning only
3. **`EventRouter`** — `src/openguardian/notifications/router.py`; consumes `AnalysisResult` after each analysis cycle; routes `critical` flags to immediate `send_critical_alert()`; routes `warning` and `informational` flags to an in-memory digest queue; weekly digest loop runs via `asyncio.sleep` on the guardian-configured day/time (default: Monday 08:00); wired into lifespan `TaskGroup`

**UAT:**
1. Running an analysis cycle that produces a `critical` severity flag causes an email to arrive in the configured inbox within one analysis cycle; the email body contains the `reasoning` text and `category` — no domain names appear in subject or body
2. After 7 days (or simulated via a short test interval), the weekly digest email arrives with a summary table of `warning` and `informational` flags; the digest contains no domain strings
3. Setting the SMTP host to an unreachable address causes the notification attempt to log `"Email delivery failed: ..."` and the service continues running normally — `GET /api/v1/health` still returns HTTP 200

---

## Requirement Coverage Map

| Requirement | Phase |
|-------------|-------|
| F1.1 ConnectorProtocol | Phase 2 |
| F1.2 ConnectorRegistry | Phase 2 |
| F1.3 GraphEvent format | Phase 2 |
| F1.4 connector.json manifest | Phase 2 |
| F1.5 Pi-hole network connector | Phase 3 |
| F1.6 Extensible connector interface | Phase 2 |
| F2.1 SQLite category map | Phase 2 |
| F2.2 20-category taxonomy | Phase 2 |
| F2.3 unknown_new classification | Phase 2 |
| F2.4 Domain hashing (SHA-256 + salt) | Phase 2 |
| F3.1 Neo4j Docker Compose | Phase 1 |
| F3.2 Graph node types | Phase 3 |
| F3.3 Graph relationships | Phase 3 |
| F3.4 UNWIND batch MERGE | Phase 3 |
| F3.5 Session construction (30-min window) | Phase 3 |
| F3.6 Cypher aggregate queries for LLM | Phase 6 |
| F4.1 7-day onboarding period | Phase 5 |
| F4.2 Manual device assignment via API | Phase 5 |
| F4.3 Daily narrative summaries during onboarding | Phase 5 |
| F4.4 No anomaly flags during onboarding | Phase 5 |
| F4.5 Baseline summary at onboarding completion | Phase 5 |
| F4.6 GET /onboarding/status | Phase 5 |
| F5.1 LLMProviderProtocol + LiteLLMProvider | Phase 5 |
| F5.2 GraphSummarizer | Phase 5 |
| F5.3 RiskLoader with keyword pre-filter | Phase 5 |
| F5.4 AnomalyDetector prompt + LLM call | Phase 5 |
| F5.5 AnalysisResult / AnomalyFlag schema | Phase 5 |
| F5.6 LLM audit log | Phase 5 |
| F5.7 6-hour analysis cycle via asyncio.sleep | Phase 5 |
| F5.8 Graceful degradation when LLM offline | Phase 5 |
| F6.1 Risk files in /known-risks/ | Phase 5 |
| F6.2 Required risk file sections | Phase 5 |
| F6.3 Files reloaded each cycle (no restart) | Phase 5 |
| F6.4 POST /risk-files upload endpoint | Phase 5 |
| F6.5 Starter risk file library | Phase 5 |
| F7.1 FastAPI + OpenAPI docs | Phase 4 |
| F7.2 All models Pydantic v2 | Phase 4 |
| F7.3 All PoC endpoints | Phase 6 |
| F7.4 FastAPI lifespan + AsyncDriver | Phase 4 |
| F8.1 Critical alert email | Phase 7 |
| F8.2 Weekly digest email | Phase 7 |
| F8.3 smtplib + Jinja2 templates | Phase 7 |
| F8.4 Guardian SMTP configuration | Phase 7 |
| F8.5 Email failure does not crash service | Phase 7 |
| NF1 Privacy-by-design (no raw domains) | Phase 2, 5, 6, 7 |
| NF2 Local execution | Phase 1 |
| NF3 Type-safety (zero Any) | Phase 2, 4, 6 |
| NF4 Graceful degradation | Phase 3, 5 |
| NF5 Audit trail | Phase 5 |
| NF6 Single docker compose up | Phase 1, 4 |
| NF7 Pluggable connectors | Phase 2 |
| NF8 Pluggable LLM | Phase 5 |

**Coverage:** 53/53 requirements mapped. No orphans.

---

## Open Questions (Resolved Before Build)

| Question | Resolution |
|----------|------------|
| Pi-hole v5 vs v6 | **v6 only.** SID-based auth (`POST /api/auth`, `X-FTL-SID` header). All v5 `?auth=` patterns are wrong. |
| `bytes_transferred` availability | Treat as optional in `GraphEvent.metadata`; do not fail normalization if absent. |
| Analysis cycle frequency | 6-hour default in settings; guardian-configurable. Validate LLM cost empirically in Phase 5. |
| Session idle window | 30-minute gap per F3.5. Primary category = most-queried in window. Secondary categories in session metadata. |
| Ollama minimum model | `llama3.1:8b` working hypothesis. Empirically validate instructor structured-output reliability in Phase 5 before documenting minimum requirement. |
| Baseline on atypical weeks | Out of scope for PoC. Guardian can re-trigger `POST /api/v1/onboarding/setup` to restart the 7-day window. Document in onboarding flow. |
