# OpenGuardian — Project State

## Current Position

- **Milestone:** 1 — Core Pipeline PoC
- **Current Phase:** None started
- **Next Action:** `/gsd:plan-phase 1`

## Milestone 1 Progress

| Phase | Name | Status |
|-------|------|--------|
| 1 | Infrastructure Foundation | Not started |
| 2 | Core Data Model and Connector Protocol | Not started |
| 3 | Pi-hole Ingestion Pipeline | Not started |
| 4 | FastAPI Skeleton and Lifespan Wiring | Not started |
| 5 | LLM Analysis Pipeline | Not started |
| 6 | Full API Surface | Not started |
| 7 | Email Notifications | Not started |

## Key Decisions (Locked)

- Python 3.11+, uv, src/ layout
- Neo4j 5.x LTS via Docker Compose
- Official `neo4j` driver v6 (py2neo is EOL)
- FastAPI + Pydantic v2
- LiteLLM + instructor for LLM (NOT LangChain)
- asyncio.sleep loops for scheduling (no APScheduler in PoC)
- Pi-hole v6 only (SID auth)
- OpenAI default LLM, provider-agnostic via LiteLLMProvider
- No Discord connector in PoC
- No frontend in PoC — API + OpenAPI docs only

## Planning Artifacts

| File | Status |
|------|--------|
| `.planning/PROJECT.md` | Done |
| `.planning/REQUIREMENTS.md` | Done |
| `.planning/ROADMAP.md` | Done |
| `.planning/research/SUMMARY.md` | Done |
| `.planning/config.json` | Done |

---
*Last updated: 2026-03-10*
