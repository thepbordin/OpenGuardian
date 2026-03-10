# OpenGuardian Architecture

This document describes the design behind the OpenGuardian software architecture and pipeline, providing an overview of how traffic signals convert into Neo4j graph data and are synthesized by LLMs for guardians.

## 1. System Layers

1. **Connector Layer**: Plugins (like `NetworkConnector`) pull outside activity data (`Pi-hole v6` DNS requests) and convert them to internal `GraphEvent` shapes.
2. **Persistence Layer**: A local `Neo4j` instance managed via asynchronous drivers stores behavior entities.
3. **Analysis Layer**: A pipeline utilizing LiteLLM abstracts interactions to large language models (OpenAI, Ollama), producing semantic warnings from numerical aggregates (the "Summary Pipeline").
4. **Web API**: Built utilizing `FastAPI`, tying asynchronous execution loops with user-query endpoints.

## 2. Ingestion Loop

Background processes managed inside FastAPI's `lifespan` continuously fetch telemetry without halting REST queries. The flow:
- `Connector` identifies unseen requests using a persisted checkpoint timestamp.
- Domains are categorized locally by an internal mapping using SQLite/Dict mapping logic to determine if traffic refers to "gaming", "social", or "vpn_proxy".
- **Hashing**: All domains are securely hashed before reaching Neo4j (`hash_domain(domain, salt)`) to prioritize physical privacy. Raw DNS data is not preserved long-term.
- `GraphRepository` runs batch `UNWIND ... MERGE` cypher queries efficiently depositing records into Neo4j nodes (User, Device, Activity).

## 3. Threat Detection

A decoupled inference loop runs periodically to cross-reference behavioral distributions against pre-established baselines.
- The `GraphSummarizer` asks the database questions like "What is the median session duration for gaming usage mapped alongside the VPN ratio?".
- The answers are serialized plainly to a prompt builder.
- Alongside it, `RiskLoader` automatically appends relevant `.md` known-risk records regarding platform abuse or grooming indicators explicitly tied to surfaced trigger categories.
- LiteLLM interprets these texts. When producing flags, the result MUST match an `AnalysisResult` Pydantic schema enforcing structured data parsing.

## 4. Privacy Design

To safeguard users and reduce hallucination liabilities:
- **No Raw Domains**: The LLM *never* interacts with explicit domain names or IP routes. It only sees aggregate metrics derived by `GraphSummarizer`.
- **Anonymization**: Output flags and email digests explicitly scrub domains.

See `REQUIREMENTS.md` for extended system specifications regarding privacy bounds and design.
