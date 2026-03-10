# OpenGuardian — Requirements

**Version:** 0.1 — PoC
**Milestone:** 1 — Core Pipeline
**Status:** Active

---

## Summary

Local-only Python service that ingests Pi-hole DNS traffic, builds a behavioral Knowledge Graph (Neo4j), and uses an LLM (OpenAI default, provider-agnostic) to detect behavioral anomalies in children/students. Guardians receive plain-English alerts by severity. No frontend for PoC — FastAPI backend with full OpenAPI/type-safe docs only.

---

## Functional Requirements

### F1 — Connector Architecture

- **F1.1** Framework defines a `ConnectorProtocol` (Python ABC/Protocol) specifying the interface every data connector must implement
- **F1.2** A `ConnectorRegistry` discovers and loads connector plugins from the `/connectors` directory at startup using `importlib.util` — no core changes required to add a connector
- **F1.3** Each connector produces events in a unified `GraphEvent` format (Pydantic v2 model):
  - `timestamp` (ISO 8601), `source`, `user_id`, `device_id`, `event_type`, `category`, `metadata`
- **F1.4** Each connector ships a `connector.json` manifest declaring its name, version, data fields, and privacy classification per field
- **F1.5** **Network Connector (Pi-hole)** — ingests DNS queries from a Pi-hole v6 instance:
  - Authenticates via Pi-hole v6 session-based auth (POST `/api/auth`, SID header)
  - Polls Pi-hole REST API incrementally for new queries since last checkpoint
  - Re-authenticates automatically on 401 responses (session expiry)
  - Normalizes each query to `GraphEvent` with `event_type: dns_query`
  - Fields captured: `timestamp`, `device_id`, `domain`, `category`, `bytes_transferred` (where available)
- **F1.6** Connector interface is designed to accommodate future connectors (Discord, location) without interface changes

### F2 — Domain Categorization

- **F2.1** A local SQLite lookup table maps domains to activity categories, seeded from StevenBlack/hagezi blocklists at install time
- **F2.2** Category taxonomy (20 categories max): `gaming`, `education`, `social`, `streaming`, `search`, `news`, `shopping`, `adult`, `vpn_proxy`, `unknown_new`, and others based on Cloudflare taxonomy
- **F2.3** Domains not in the lookup table are classified as `unknown_new` and queued for async LLM inference or TLD heuristics
- **F2.4** Raw domain strings are hashed (SHA-256 + per-installation salt) before storage in any guardian-visible layer

### F3 — Knowledge Graph

- **F3.1** Graph stored in a local Neo4j 5.x LTS instance (Docker Compose)
- **F3.2** Node types: `User`, `Device`, `Activity` (category), `TimeSlot`
- **F3.3** Relationships:
  - `(User)-[:OWNS]->(Device)` — manual assignment during onboarding
  - `(Device)-[:ACCESSED {count, total_duration}]->(Activity)` — updated incrementally
  - `(Activity)-[:OCCURRED_AT]->(TimeSlot)` — temporal bucketing (hour-of-day + day-of-week)
- **F3.4** Graph updated via `UNWIND`-based batch MERGE statements (not individual CREATE calls)
- **F3.5** Session construction: DNS queries within a 30-minute idle window are grouped into a single session before graph merge
- **F3.6** Cypher aggregate queries produce behavioral summaries (session count, median duration, category distribution, peak hours) consumed by the LLM analysis layer

### F4 — Onboarding

- **F4.1** Onboarding period: 7 days from first guardian-confirmed device assignment
- **F4.2** Guardian manually assigns a device to a user via API call during setup, providing: user name, age, school schedule (free-text)
- **F4.3** During onboarding, the LLM observes traffic and generates daily narrative summaries for the guardian to review
- **F4.4** No anomaly flags are generated during the onboarding period
- **F4.5** At onboarding completion, the LLM generates a baseline summary confirmed by the system; monitoring mode activates automatically
- **F4.6** Onboarding status exposed via API (`GET /onboarding/status`)

### F5 — LLM Analysis Pipeline

- **F5.1** `LLMProvider` protocol defines the adapter interface; `LiteLLMProvider` is the default implementation (supports OpenAI, Anthropic, Ollama via single config string)
- **F5.2** `GraphSummarizer` serializes the Knowledge Graph into narrative text for LLM context (aggregate stats — never raw domain strings)
- **F5.3** `RiskLoader` loads Known Risk files from `/known-risks/` directory; keyword pre-filter on `Trigger Categories` field selects relevant files per analysis cycle
- **F5.4** `AnomalyDetector` builds prompt from: baseline summary + current window summary + relevant risk files; calls LLM with `temperature=0.0`; parses structured `AnalysisResult` (via `instructor` library)
- **F5.5** `AnalysisResult` Pydantic schema: list of `AnomalyFlag` objects, each with: `severity` (informational/warning/critical), `category`, `reasoning` (guardian-facing explanation), `risk_file_cited` (optional)
- **F5.6** Every LLM call is logged with full prompt + response to an audit log (file or DB table) — mandatory for a child-safety system
- **F5.7** Analysis cycle runs on a configurable interval (default: 6 hours) via `asyncio.sleep` loop
- **F5.8** System degrades gracefully if LLM is unavailable: graph continues to update, no flags generated, API returns `llm_unavailable` status

### F6 — Known Risk Library

- **F6.1** Risk files stored under `/known-risks/` in the format `risk_[type]_[platform].md`
- **F6.2** Required sections: `Risk Type`, `Context`, `Behavioral Signals`, `Progression Pattern`, `Cross-Connector Signals`, `Trigger Categories` (for pre-filter), `Severity`, `Sources`
- **F6.3** Files loaded automatically at each analysis cycle (no restart required)
- **F6.4** Guardians/admins can upload new risk files via `POST /risk-files` API endpoint
- **F6.5** Starter library ships with: `risk_grooming_roblox.md`, `risk_grooming_discord.md`, `risk_radicalization_discord.md`

### F7 — REST API (FastAPI)

- **F7.1** FastAPI application with full OpenAPI/Swagger docs auto-generated from Pydantic v2 models
- **F7.2** All request/response models are Pydantic v2 — no `dict`, no untyped fields
- **F7.3** Endpoints (PoC):

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health + Neo4j + LLM status |
| POST | `/onboarding/setup` | Assign device to user, start onboarding |
| GET | `/onboarding/status` | Current onboarding state |
| GET | `/behavior/summary` | Current behavioral summary (categories, sessions) |
| GET | `/behavior/baseline` | Established baseline summary |
| GET | `/anomalies` | List anomaly flags (filterable by severity, date) |
| GET | `/anomalies/{id}` | Single flag detail with full LLM reasoning |
| POST | `/risk-files` | Upload a new Known Risk file |
| GET | `/risk-files` | List loaded risk files |
| GET | `/connectors` | List registered connectors and their status |

- **F7.4** FastAPI lifespan manages Neo4j `AsyncDriver` (one per process) and background task lifecycle

### F8 — Email Notifications

- **F8.1** Critical-severity flags trigger a real-time email alert (within one analysis cycle)
- **F8.2** Weekly digest email summarizes informational/warning flags for the past 7 days
- **F8.3** Email sent via `smtplib` + Jinja2 templates (SMTP config in settings)
- **F8.4** Guardian configures: recipient address, SMTP server, notification level, weekly digest day/time
- **F8.5** Email delivery failures are logged but do not crash the service

---

## Non-Functional Requirements

| ID | Requirement | Acceptance |
|----|-------------|------------|
| NF1 | Privacy-by-design | Raw domains never appear in API responses, LLM prompts, or email content |
| NF2 | Local execution | All processing runs locally; only outbound calls are optional LLM API requests |
| NF3 | Type-safety | Zero use of `Any` type; all API models fully typed with Pydantic v2 |
| NF4 | Graceful degradation | Monitoring continues if LLM is offline; API returns degraded status |
| NF5 | Audit trail | Every LLM call logged with full prompt, response, timestamp |
| NF6 | Self-hostable | Single `docker compose up` starts all dependencies (Neo4j, service) |
| NF7 | Pluggable connectors | New connector = drop files in `/connectors/`, no core changes |
| NF8 | Pluggable LLM | Change LLM provider via config string change, no code changes |

---

## Out of Scope (PoC)

- Discord connector — deferred post-PoC
- Location connector — optional, not implemented
- Frontend dashboard — API + OpenAPI docs only; frontend is a future milestone
- Multi-device support
- Multi-user households
- Deep packet inspection
- Mobile app
- Cloud deployment
- Automated consent flow UI
- Multi-admin support

---

## Tech Stack (Definitive)

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Package manager | uv |
| Project layout | `src/` layout |
| API framework | FastAPI + Pydantic v2 |
| Graph database | Neo4j 5.x LTS (Docker) |
| Neo4j driver | `neo4j` official driver v6 (NOT py2neo — EOL) |
| LLM adapter | LiteLLM + instructor |
| Default LLM | OpenAI (configurable) |
| Scheduling | `asyncio.sleep` loop (no APScheduler in PoC) |
| Config | pydantic-settings v2 + `SecretStr` for API keys |
| Email | smtplib + Jinja2 |
| Testing | pytest + pytest-asyncio + testcontainers-python (Neo4j) |
| Containerization | Docker Compose |

---

## Open Questions

1. **Pi-hole version**: Pi-hole v5 vs v6 API auth differs significantly. Target version must be confirmed before parser implementation.
2. **bytes_transferred**: Not confirmed as a direct column in Pi-hole v6 SQLite schema — may require fallback.
3. **Analysis cycle frequency**: 6-hour default is a guess. Should be validated against LLM cost and detection latency requirements.
4. **Baseline refresh**: How the system handles atypical weeks (school holidays, illness) is not defined — open for post-PoC.
5. **VPN evasion**: Chrome/Firefox DoH can bypass Pi-hole. A query-volume-drop heuristic can signal probable VPN use but cannot confirm. Should be documented in onboarding.
6. **Ollama minimum model**: `llama3.1:8b` is the working hypothesis for offline LLM support. Needs empirical validation for structured output reliability.
