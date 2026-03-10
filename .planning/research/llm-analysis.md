# LLM Analysis Research: OpenGuardian

**Domain:** LLM-driven behavioral anomaly detection in a local monitoring system
**Researched:** 2026-03-10
**Overall confidence:** MEDIUM-HIGH (architecture patterns are HIGH; grooming-specific LLM accuracy is LOW with strong research caveats)

---

## 1. LLM Provider Abstraction

### Recommendation: LiteLLM + instructor

**Use LiteLLM as the transport layer** (provider routing, credential management, async support) and **instructor for structured outputs** (Pydantic-validated JSON from any provider). Do not write a custom adapter from scratch — LiteLLM already solves the provider-agnostic interface problem and is actively maintained.

**Confidence:** HIGH — verified via official docs and PyPI (3M+ monthly downloads for instructor, LiteLLM is default model backend for OpenAI Agents SDK).

### Why LiteLLM over raw SDKs

| Factor | LiteLLM | Roll-your-own adapter |
|--------|---------|----------------------|
| Provider support | 100+ providers (OpenAI, Anthropic, Ollama, Gemini, Bedrock) | 3 providers, manual maintenance |
| API surface | OpenAI-compatible for all providers | Must normalize each provider's quirks |
| Async | `acompletion()` built-in | Must re-implement per provider |
| Cost tracking | Built-in `response_cost` | None |
| Breaking changes | Absorbed by library | Hit your code directly |
| Dependency weight | Single package | Equivalent effort, no reuse |

### Why NOT LangChain for this use case

LangChain is appropriate when you need multi-step orchestration, tool calling pipelines, or agent loops with state. OpenGuardian's LLM surface is narrow: summarize graph state, detect anomaly, return structured JSON. LangChain adds 50+ transitive dependencies, obscures behavior behind abstractions, and couples you to its release cycle. For this project, LangChain is overhead with no benefit.

**Decision: LiteLLM + instructor. No LangChain.**

### Interface Design Pattern

Define a Protocol-based interface so the adapter layer is testable and mockable:

```python
# llm/interface.py
from typing import Protocol, runtime_checkable
from pydantic import BaseModel


@runtime_checkable
class LLMProvider(Protocol):
    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
    ) -> BaseModel: ...

    async def summarize(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str: ...
```

```python
# llm/litellm_provider.py
import instructor
import litellm
from pydantic import BaseModel

from .interface import LLMProvider


class LiteLLMProvider:
    """Provider-agnostic LLM adapter backed by LiteLLM + instructor."""

    def __init__(self, model: str, temperature: float = 0.0) -> None:
        # model examples:
        #   "openai/gpt-4o"
        #   "anthropic/claude-3-5-sonnet-20241022"
        #   "ollama/llama3.2"
        self._model = model
        self._temperature = temperature
        self._client = instructor.from_provider(
            f"litellm/{model}",
            async_client=True,
        )

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
    ) -> BaseModel:
        return await self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_model=response_schema,
        )

    async def summarize(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        response = await litellm.acompletion(
            model=self._model,
            temperature=self._temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content
```

### Configuration

Drive provider selection from environment/config, not code:

```python
# config.py
from pydantic_settings import BaseSettings


class LLMConfig(BaseSettings):
    llm_model: str = "openai/gpt-4o"
    llm_temperature: float = 0.0
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    # Ollama: no key needed, set llm_model = "ollama/llama3.2"

    class Config:
        env_file = ".env"
```

### Graceful Degradation

Wrap the LLM call with a timeout and fallback so core monitoring continues even if the LLM is unavailable:

```python
import asyncio


async def safe_analyze(provider: LLMProvider, ...) -> AnalysisResult | None:
    try:
        return await asyncio.wait_for(
            provider.analyze(...),
            timeout=30.0,
        )
    except (asyncio.TimeoutError, Exception):
        # Log and return None — caller queues event for retry
        return None
```

---

## 2. Behavioral Baseline Establishment

### The Core Problem

The LLM needs to answer: "Is today's behavior meaningfully different from normal?" That requires feeding it a structured, token-efficient representation of:
1. What "normal" looks like (the baseline)
2. What today looks like

The naive approach — dumping raw Neo4j node/edge lists — is both token-wasteful and semantically poor. The LLM reasons better on natural-language summaries than on graph wire formats.

### Graph-to-Text Serialization Strategy

**Confidence:** MEDIUM — based on 2025 academic findings on KG-to-text encodings + Neo4j community patterns.

Build a `GraphSummarizer` that runs Cypher queries to extract aggregated statistics, then renders them as structured natural language. Never serialize raw triples.

```
# GOOD — structured narrative
User activity summary (Mon Mar 3 – Sun Mar 9, 2025):
- Gaming: 18 sessions, avg 62 min/session, peak hours 16:00–20:00
- Education: 11 sessions, avg 28 min/session, exclusively 08:00–15:00
- Social media: 3 sessions, avg 15 min/session
- Streaming: 2 sessions, avg 90 min/session
- No sessions after 22:00

# BAD — raw graph dump
(Device:D01)-[:accessed]->(Activity:gaming {count: 18, avg_duration: 62})...
```

**Key insight from research:** "Appropriate encodings can yield large accuracy gains." Natural language node/edge descriptions outperform raw triple dumps for reasoning tasks.

### Cypher Queries for Baseline Extraction

Run aggregating queries against Neo4j, not row-level dumps:

```cypher
// Activity frequency by category, grouped by hour-of-day bucket
MATCH (d:Device {id: $device_id})-[:accessed]->(a:Activity)-[:occurred_at]->(t:TimeSlot)
WHERE t.timestamp >= $window_start AND t.timestamp <= $window_end
RETURN
    a.category AS category,
    count(*) AS session_count,
    avg(a.duration_minutes) AS avg_duration,
    collect(DISTINCT t.hour_bucket) AS active_hours
ORDER BY session_count DESC
```

### Temporal Windowing

Structure the baseline context as a rolling statistical window, not a flat log:

```python
# Baseline = 7-day onboarding aggregate
# Current window = last 24 hours (or last analysis cycle)

BASELINE_PROMPT_TEMPLATE = """
## Established Behavioral Baseline (Onboarding: {start_date} to {end_date})

{baseline_summary}

## Current Observation Window ({observation_start} to {observation_end})

{current_summary}

## Known Risk Context

{risk_files_content}
"""
```

The baseline summary is regenerated once per day from a Cypher aggregate. The current window summary is regenerated each analysis cycle (suggested: every 6 hours during active monitoring, every hour if anomaly already flagged).

### Token Budget

| Context section | Estimated tokens | Notes |
|----------------|-----------------|-------|
| System prompt + role | ~300 | Fixed |
| Baseline summary (7-day) | ~400–600 | Narrative aggregate |
| Current window summary | ~200–300 | Narrative aggregate |
| Loaded risk files (relevant) | ~500–1500 | See Section 4 |
| Output schema hint | ~200 | Pydantic model docstring |
| **Total budget** | **~1600–2900** | Well within GPT-4o 128k |

Keep total context under 4000 tokens for Ollama compatibility (smaller models have 4k–8k windows). The above budget fits even `llama3.2:3b`.

---

## 3. Prompt Engineering for Risk Detection

### Recommended Pattern: Chain-of-Thought with Structured Output

**Confidence:** HIGH — CoT for anomaly detection is validated in multiple 2025 academic papers (MDPI, ACL Anthology, ICLR 2025). Structured JSON output via Pydantic is standard practice.

The key finding from research: CoT + Self-Consistency achieves up to 0.96 accuracy on classification tasks without task-specific training. The reasoning trace also serves as the guardian-facing explanation — you get the explanation for free.

### Pydantic Output Schema

```python
# llm/schemas.py
from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    informational = "informational"
    warning = "warning"
    critical = "critical"


class AnomalyFlag(BaseModel):
    anomaly_type: str = Field(
        description="Short label: e.g. 'new_category', 'time_shift', 'frequency_spike'"
    )
    reasoning: str = Field(
        description="Step-by-step reasoning comparing current vs baseline behavior"
    )
    plain_english_explanation: str = Field(
        description="Guardian-facing explanation in plain English, 2-3 sentences, no jargon"
    )
    severity: Severity
    matched_risk_file: str | None = Field(
        default=None,
        description="Filename of Known Risk file that matches this pattern, if any"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Model's self-assessed confidence in this flag (0.0–1.0)"
    )


class AnalysisResult(BaseModel):
    analysis_summary: str = Field(
        description="One-paragraph overall assessment of behavior in current window"
    )
    anomaly_flags: list[AnomalyFlag] = Field(
        default_factory=list,
        description="List of detected anomalies. Empty list if behavior is within baseline."
    )
    baseline_drift_score: float = Field(
        ge=0.0, le=1.0,
        description="Holistic drift from baseline: 0.0 = identical, 1.0 = completely novel"
    )
```

### System Prompt Template

```python
ANALYSIS_SYSTEM_PROMPT = """
You are a behavioral safety analyst for a child monitoring system.
Your role is to compare a child's recent online activity against their established baseline
and identify meaningful behavioral deviations that may indicate risk.

CRITICAL CONSTRAINTS:
- You are analyzing activity categories only (e.g., "gaming", "social media", "education").
  You do NOT have access to, and must NOT infer, specific websites or applications.
- Flag anomalies only when they represent a meaningful deviation from the established baseline.
  Normal variation within expected ranges is NOT an anomaly.
- Err on the side of fewer, higher-confidence flags over many low-confidence flags.
  False alarms erode guardian trust and lead to alert fatigue.
- When a behavior pattern matches a Known Risk file, reference it explicitly by filename.

SEVERITY GUIDELINES:
- informational: Notable change, worth monitoring. No immediate concern.
- warning: Significant deviation that warrants guardian awareness and follow-up.
- critical: Pattern matches a known risk sequence or represents a severe behavioral shift
  requiring immediate guardian attention.

REASONING REQUIREMENT:
For each flag, reason step-by-step before assigning severity:
1. What specifically changed vs. baseline?
2. How significant is the change (magnitude, frequency, timing)?
3. Does it match any loaded Known Risk pattern?
4. What is the most benign explanation? What is the most concerning explanation?
5. Given both explanations, what severity is appropriate?
""".strip()
```

### User Prompt Template

```python
def build_analysis_prompt(
    baseline_summary: str,
    current_summary: str,
    risk_files_content: str,
    observation_window: str,
) -> str:
    return f"""
## Observation Window
{observation_window}

## Established Behavioral Baseline (7-day onboarding)
{baseline_summary}

## Current Behavior ({observation_window})
{current_summary}

## Loaded Known Risk Patterns
{risk_files_content if risk_files_content else "No risk files loaded for this analysis cycle."}

Analyze the current behavior against the baseline and the loaded risk patterns.
Reason step-by-step for each anomaly before assigning severity.
If no meaningful anomalies are detected, return an empty anomaly_flags list.
""".strip()
```

### Baseline Prompt (Onboarding Phase)

During the 7-day onboarding, use a different prompt that asks the LLM to characterize normal behavior rather than flag anomalies:

```python
ONBOARDING_SYSTEM_PROMPT = """
You are establishing a behavioral baseline for a child monitoring system.
You are observing the first week of activity. Your task is to summarize what
"normal" looks like for this user — not to flag anything as anomalous.

Produce a structured baseline profile covering:
- Typical active hours (morning / afternoon / evening / late night)
- Activity categories and their relative frequency
- Session duration ranges per category
- Any regular patterns (e.g., education activity on weekdays 08:00–15:00)
- Categories that appeared only once (note as occasional, not baseline)

Be descriptive and specific. This profile will be used in future analysis cycles.
""".strip()
```

### Temperature Settings

| Use case | Temperature | Rationale |
|----------|-------------|-----------|
| Anomaly analysis | 0.0 | Deterministic, reproducible flags |
| Baseline summarization | 0.2 | Slight creativity for narrative prose |
| Guardian report narrative | 0.4 | More natural language in digest emails |

---

## 4. Known Risk File Library

### File Format (finalized from requirements)

The format defined in `requirement.md` is well-structured. One addition recommended: a **trigger signals** section listing specific activity categories (not domains) that trigger loading this file, so the retrieval layer can do fast keyword matching before vector search.

```markdown
# [Skill Name]

## Risk Type
grooming | radicalization | self-harm | exploitation

## Trigger Categories
<!-- Activity categories that, if present, should load this file -->
- gaming
- social_media
- messaging

## Context
Plain-language description of the real-world incident or behavioral pattern.

## Behavioral Signals
- Signal 1: [category] activity at [time pattern]
- Signal 2: shift from [category A] to [category B]
- Signal 3: frequency spike in [category]

## Progression Pattern
Step-by-step sequence of behavioral changes indicating risk escalation.
Example: gaming (sustained) → social_media spike → unknown_category appearance

## Cross-Connector Signals
- network: [activity categories to watch]
- discord: [event types, if connector active]
- location: [zone patterns, if connector active]

## Severity
critical | warning

## Sources
- [Reference URL or citation]
```

### Loading Strategy: Keyword Pre-filter + Full-file Injection

**Confidence:** MEDIUM — based on 2025 RAG chunking research and the specific constraints of OpenGuardian.

For this use case, **do NOT use vector embeddings and semantic search** for risk file retrieval. Reasons:
1. The risk file library will be small (< 50 files in any realistic deployment).
2. Vector search adds infrastructure complexity (embedding model, vector store).
3. The `Trigger Categories` field enables a simple, reliable pre-filter.
4. Risk files are short (< 500 tokens each) — injecting 3–5 is well within budget.

**Strategy:**

```python
# llm/risk_loader.py
from pathlib import Path
import re


def load_relevant_risk_files(
    known_risks_dir: Path,
    active_categories: set[str],
    max_files: int = 5,
) -> str:
    """
    Load risk files whose Trigger Categories overlap with active_categories.
    Returns concatenated markdown content for LLM context injection.
    """
    loaded: list[str] = []

    for risk_file in sorted(known_risks_dir.glob("risk_*.md")):
        content = risk_file.read_text(encoding="utf-8")
        trigger_categories = _extract_trigger_categories(content)

        if trigger_categories & active_categories:
            loaded.append(f"### {risk_file.stem}\n\n{content}")

        if len(loaded) >= max_files:
            break

    if not loaded:
        return ""

    return "\n\n---\n\n".join(loaded)


def _extract_trigger_categories(content: str) -> set[str]:
    """Extract bullet items under '## Trigger Categories' section."""
    match = re.search(
        r"## Trigger Categories\s*\n((?:- .+\n?)+)",
        content,
        re.IGNORECASE,
    )
    if not match:
        return set()
    return {
        line.strip("- ").strip().lower()
        for line in match.group(1).splitlines()
        if line.strip().startswith("-")
    }
```

### Chunking Decision

Risk files should **not** be chunked. Each file is a single coherent behavioral pattern — splitting it destroys the progression context that makes it useful. Keep files under 600 tokens (about 450 words) by design. The file format enforces this naturally.

If files grow beyond 600 tokens, split at the section boundary (each H2 section becomes a chunk with the filename as context prefix), not at arbitrary character/token counts.

### File Management

- Files in `/known-risks/` are loaded at analysis cycle start, not cached indefinitely.
- Guardian uploads via API create `.md` files in the same directory — no special registration needed.
- Validate uploaded files against the schema before accepting them (check required H2 sections).

---

## 5. LangChain vs Raw SDK: Final Decision Matrix

| Criterion | LiteLLM + instructor | LangChain |
|-----------|---------------------|-----------|
| Provider switching | Single string change | Requires LangChain-specific configuration |
| Structured output | instructor + Pydantic, all providers | LCEL chains, more setup |
| Async support | `acompletion()` native | Async support present but more complex |
| Dependencies | ~5 packages | 50+ transitive dependencies |
| Token/cost tracking | Built-in | Requires callbacks |
| Debugging | Direct SDK calls visible | Hidden in abstractions |
| Learning curve | Low | High |
| Ollama support | `ollama/model_name` string | Requires LangChain-Ollama integration |
| Use case fit for OpenGuardian | Excellent — narrow LLM surface | Over-engineered for this scope |

**Verdict: LiteLLM + instructor. LangChain is not needed and adds complexity without benefit for this project.**

The one scenario where LangChain would be reconsidered: if future phases add agentic tool-calling loops (e.g., the LLM autonomously decides to run additional Cypher queries, look up external threat feeds, or draft emails). That scope is explicitly out of PoC scope.

---

## 6. Known Risks: Research Caveats

The literature on LLM-based grooming/radicalization detection raises important accuracy caveats that must inform the design:

**Confidence: HIGH on the caveats themselves** (multiple 2025 peer-reviewed sources from ACM, Frontiers, arXiv).

### Critical Findings from 2025 Research

1. **Grooming detection by LLMs is hard.** A 2025 ACM study found "no models were clearly appropriate for online grooming prevention" in direct chat detection, with "low precision and inconsistent temporal performance." Current LLMs struggle with behaviors that "unfold gradually and rely on social context."

2. **OpenGuardian's approach avoids the hardest problem.** The system does NOT ask the LLM to analyze conversation content (it has no access to message content). It analyzes behavioral metadata — activity categories, timing, frequency patterns — which is a meaningfully different and more tractable task.

3. **Risk files shift the burden.** By encoding expert-curated progression patterns in Known Risk files, the LLM's job is pattern-matching against a known template rather than open-ended content reasoning. This is more reliable.

4. **False positive management is critical.** Research consistently shows that optimizing for sensitivity (catching all true positives) inflates false positives, which destroys guardian trust. The system prompt above explicitly instructs the model to prefer fewer, higher-confidence flags. This is the right tradeoff for a guardian-facing tool.

5. **Guardian context matters.** The LLM has access to age and schedule context provided at onboarding. This must be included in the system prompt — a 16-year-old online at 11pm is different from a 9-year-old.

### Design Implication

Add a `user_context` section to the analysis prompt:

```python
USER_CONTEXT_TEMPLATE = """
## User Profile (Guardian-provided at onboarding)
- Age: {age}
- School schedule: {school_schedule}
- Guardian notes: {guardian_notes}
"""
```

The LLM should weight anomalies relative to age-appropriate norms, not absolute norms. A 16-year-old gaming until midnight is different from a 10-year-old doing the same.

---

## 7. Architecture Sketch: LLM Pipeline

```
[Neo4j Graph]
      |
      | Cypher aggregates (every analysis cycle)
      v
[GraphSummarizer]
  - baseline_summary (7-day window)
  - current_summary  (last N hours)
      |
      v
[RiskLoader]
  - scans /known-risks/*.md
  - filters by active categories
  - returns concatenated markdown
      |
      v
[PromptBuilder]
  - combines: system_prompt + user_context
             + baseline_summary + current_summary
             + risk_files_content
      |
      v
[LiteLLMProvider.analyze(response_schema=AnalysisResult)]
      |
      v
[AnalysisResult (Pydantic)]
  - anomaly_flags: list[AnomalyFlag]
  - severity per flag
  - matched_risk_file per flag
      |
      v
[EventRouter]
  - critical → immediate email notification
  - warning  → queue for weekly digest
  - informational → log only
```

---

## 8. Library Recommendations Summary

| Library | Version | Purpose | Install |
|---------|---------|---------|---------|
| `litellm` | latest (≥1.40) | Provider-agnostic LLM routing, async | `pnpm` N/A — `pip install litellm` |
| `instructor` | latest (≥1.5) | Structured outputs via Pydantic, all providers | `pip install instructor` |
| `pydantic` | v2 | Schema definition, validation, response parsing | `pip install pydantic` |
| `pydantic-settings` | v2 | Config from env vars / .env | `pip install pydantic-settings` |

No additional LLM libraries needed. Specifically: do not add `langchain`, `llama-index`, `openai` (direct), or `anthropic` (direct) — LiteLLM handles all provider SDKs as optional dependencies under the hood.

---

## 9. Open Questions / Gaps

1. **Ollama model quality floor.** Structured output reliability degrades significantly with smaller local models (7B and below). `llama3.2:3b` may produce malformed JSON for complex schemas. instructor has retry logic but this needs empirical testing. Recommend testing with `llama3.1:8b` minimum for structured output.

2. **Analysis cycle frequency.** How often does the system re-run analysis? Every hour is feasible for cloud LLMs but expensive; every 6 hours is more practical. Critical-severity patterns need a faster path — consider a lightweight rule-based pre-screen that triggers the LLM only on specific category combinations (e.g., gaming + unknown_category appearing together).

3. **Baseline drift over time.** A 7-day baseline established in March may be stale by June (summer vacation changes patterns dramatically). Need a baseline refresh strategy — either rolling window or guardian-triggered re-onboarding.

4. **Multi-session aggregation.** Current design aggregates at the category level. If a child uses "social media" across 14 separate 5-minute micro-sessions vs. one 70-minute session, the total time is identical but the behavioral pattern is different. Consider tracking session count and median session duration separately in graph nodes.

5. **LLM response auditability.** For a system making child-safety decisions, every LLM response should be logged with its full prompt, output, and timestamp. This creates an audit trail for guardian review and for debugging false positives. Build this into the `LiteLLMProvider` wrapper, not as an afterthought.

---

## Sources

- [LiteLLM official docs](https://docs.litellm.ai/docs/)
- [instructor + LiteLLM integration](https://python.useinstructor.com/integrations/litellm/)
- [instructor GitHub (567-labs)](https://github.com/567-labs/instructor)
- [OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs/)
- [LangChain vs LangGraph vs Raw OpenAI comparison](https://www.droptica.com/blog/langchain-vs-langgraph-vs-raw-openai-how-choose-your-rag-stack/)
- [LiteLLM vs LangChain breakdown (Medium)](https://medium.com/@agile.cadre.testing/langchain-vs-llamaindex-vs-litellm-vs-ollama-vs-no-frameworks-a-3-minute-breakdown-1c8f93b9d979)
- [LLM anomaly detection — chain-of-thought (MDPI)](https://www.mdpi.com/2076-3417/15/19/10384)
- [LLM-powered anomaly detection (TDS)](https://towardsdatascience.com/boosting-your-anomaly-detection-with-llms/)
- [Anomaly detection step-by-step guide (Theodo)](https://blog.theodo.com/2024/01/anomaly-detection-llm/)
- [Knowledge graph injection into LLMs (arXiv 2025)](https://arxiv.org/html/2505.07554v1)
- [Temporal RAG via graph (arXiv 2025)](https://arxiv.org/pdf/2510.16715)
- [Neo4j LangChain Cypher search patterns](https://neo4j.com/blog/developer/langchain-cypher-search-tips-tricks/)
- [RAG chunking strategies (Weaviate 2025)](https://weaviate.io/blog/chunking-strategies-for-rag)
- [Markdown chunking best practices (Firecrawl)](https://www.firecrawl.dev/blog/best-chunking-strategies-rag)
- [LLM grooming detection — ACM 2024/2025](https://dl.acm.org/doi/fullHtml/10.1145/3655693.3655694)
- [Early detection of online grooming with LLMs (ResearchGate 2025)](https://www.researchgate.net/publication/391745641_Early_Detection_of_Online_Grooming_with_Language_Models)
- [LLMs and childhood safety risks (arXiv 2025)](https://arxiv.org/pdf/2502.11242)
- [LLM false positive rate management (DataDog)](https://www.datadoghq.com/blog/using-llms-to-filter-out-false-positives/)
- [Context window management strategies (Agenta)](https://agenta.ai/blog/top-6-techniques-to-manage-context-length-in-llms)
- [AnyLLM unified interface overview](https://atalupadhyay.wordpress.com/2025/08/23/anyllm-the-ultimate-unified-interface-for-multiple-llm-providers/)
