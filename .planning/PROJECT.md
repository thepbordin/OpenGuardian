# OpenGuardian

## What This Is

OpenGuardian is an open-source, locally-run framework that monitors network behavior for a single user/device, constructs a Knowledge Graph from traffic data, and surfaces behavioral insights for guardians or administrators. It is designed for home or school environments with a strong emphasis on privacy and consent — guardians see activity categories, never raw domains.

## Core Value

A guardian can be alerted to meaningful behavioral changes (grooming, radicalization, usage shifts) before harm occurs, without invading privacy or relying on cloud services.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Modular connector architecture with Pi-hole as PoC DNS connector
- [ ] Graph Event unified format normalizing all connector output
- [ ] Knowledge Graph construction using Neo4j (local) from ingested events
- [ ] 1-week onboarding period: LLM observes traffic and establishes behavioral baseline with guardian
- [ ] LLM-driven anomaly detection (no hardcoded thresholds) via OpenAI adapter
- [ ] Provider-agnostic LLM adapter interface (OpenAI, Anthropic, Ollama)
- [ ] Known Risk file library (`/known-risks/*.md`) loaded as LLM context during analysis
- [ ] Severity-rated anomaly flags (informational / warning / critical) with plain-English explanations
- [ ] FastAPI backend with fully type-safe, documented API (OpenAPI/Swagger)
- [ ] Email notifications: real-time for critical flags, weekly digest for informational/warning
- [ ] Privacy-by-design: guardians see activity categories only, raw domains never exposed in outputs
- [ ] All processing runs locally; no cloud dependency except optional LLM API calls

### Out of Scope

- Discord connector — deferred to post-PoC
- Location connector — optional, not implemented in PoC
- Multi-device support — PoC is single device
- Multi-user households — PoC is single user
- Deep packet inspection — DNS-level only
- Mobile app — not in scope
- Cloud deployment — local only
- Automated consent flow UI — manual onboarding
- Frontend dashboard — backend + API only for PoC; frontend is a future milestone

## Context

- **Domain:** Child/student safety monitoring via passive network observation
- **Deployment target:** Home or small school network, single device (e.g., family router with Pi-hole, NAS, or laptop)
- **DNS capture method:** Pi-hole log ingestion for PoC; connector interface designed to be pluggable (future: packet sniffing, custom DNS server)
- **Graph backend:** Neo4j (local instance)
- **LLM default:** OpenAI (cloud), provider-agnostic via adapter — Ollama local model is a valid alternative
- **Known Risks library:** Structured markdown files describing real-world behavioral risk patterns (e.g., Roblox grooming progression); loaded as LLM context during analysis cycles
- **Sensitivity:** The system handles data about minors. Privacy and consent are non-negotiable design constraints.

## Constraints

- **Tech Stack:** Python backend, FastAPI for API layer, Neo4j for graph storage
- **Local execution:** No cloud dependencies for core pipeline; LLM API calls are the only external network requirement
- **Privacy:** Activity categories exposed to guardian; raw domain data never leaves internal processing layer
- **PoC scope:** Single device, single user — horizontal scaling is a future concern
- **Open source:** Codebase must be self-hostable with minimal setup friction

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Pi-hole as PoC DNS connector | Lowest barrier for home users; pluggable interface allows future backends | — Pending |
| Neo4j for graph storage | Full graph query capability; overkill for PoC but right long-term choice | — Pending |
| No frontend in PoC | Focus execution effort on core pipeline correctness; API-first makes any frontend easy to bolt on | — Pending |
| OpenAI as default LLM | Easy onboarding; adapter interface means no lock-in | — Pending |
| LLM-only anomaly detection | Avoids brittle hardcoded thresholds; baseline is behavioral, not numeric | — Pending |
| Discord connector deferred | Scope control for PoC; API design should account for it | — Pending |

---
*Last updated: 2026-03-10 after initialization*
