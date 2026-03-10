# Phase 1: Infrastructure Foundation - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Single `docker compose up` boots Neo4j 5.26-community and the Python service skeleton. Schema migrations run automatically at startup with `IF NOT EXISTS` guards. The service verifies Neo4j connectivity before accepting any work. All configuration via environment variables with `.env.example` as reference.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
The following implementation details are left to planning discretion based on best practices:

**Logging and output:**
- Human-readable console logs for development (structured JSON optional)
- `INFO` level default; `DEBUG` via env var for development
- Startup logs show: migration status, Neo4j connection result, service ready message

**Configuration validation:**
- Required variables cause immediate startup failure with clear error messages
- Optional variables have sensible defaults documented in `.env.example`
- Validation happens at service startup before any database operations

**Startup dependencies:**
- Service waits up to 30 seconds for Neo4j to be ready (healthcheck-based)
- Retry with exponential backoff (1s, 2s, 4s, 8s, 15s max)
- If Neo4j never becomes ready: exit with non-zero code and log error

**Migration error handling:**
- Migrations run before service accepts any requests
- Any migration failure: log the error and exit with non-zero code (fail fast)
- `IF NOT EXISTS` guards prevent duplicate constraint errors on restart
- Applied migrations tracked in Neo4j node to avoid re-running

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard Docker Compose + FastAPI patterns.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
None — greenfield project.

### Established Patterns
None — this is Phase 1, establishing the foundational patterns.

### Integration Points
None yet — this phase creates the foundation that later phases connect to:
- Phase 3 will use GraphClient for ingestion
- Phase 4 will wire ingestion loop into FastAPI lifespan
- Phase 5 will add analysis loop to lifespan TaskGroup

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-infrastructure-foundation*
*Context gathered: 2026-03-10*
