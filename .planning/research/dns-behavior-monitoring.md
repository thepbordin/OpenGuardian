# DNS-Based Behavioral Monitoring: Domain Research

**Project:** OpenGuardian
**Researched:** 2026-03-10
**Mode:** Ecosystem
**Overall Confidence:** MEDIUM-HIGH

---

## 1. DNS Traffic Categorization

### 1.1 Taxonomy Strategy

The most practical approach for a local, offline-first system is a **layered taxonomy**: a local category map as the authoritative source, seeded from curated public blocklists, with an optional runtime enrichment call to a remote API for unknown domains.

**Recommended local taxonomy (20 categories):**

| Category Key | Description | Risk Relevance |
|---|---|---|
| `gaming` | Game platforms (roblox.com, steam, twitch) | Low-medium baseline |
| `social` | Social networks (discord, instagram, snapchat) | Escalation vector |
| `messaging` | Messaging apps (whatsapp, telegram, signal) | Escalation vector |
| `video` | Video streaming (youtube, netflix, tiktok) | Content risk |
| `education` | School/learning platforms | Absence = anomaly |
| `search` | Search engines | Baseline |
| `adult` | Adult content | Critical flag |
| `vpn_proxy` | VPN and proxy services | Evasion signal |
| `cloud_storage` | Cloud file services (drive, dropbox, mega) | Exfiltration risk |
| `crypto` | Cryptocurrency exchanges and wallets | Financial risk |
| `gambling` | Gambling platforms | Risk |
| `violence` | Extremism, violence content | Critical flag |
| `darkweb` | Tor exits, onion resolvers | Critical flag |
| `malware` | Known malware/C2 domains | Critical flag |
| `phishing` | Known phishing domains | Critical flag |
| `unknown_new` | Recently registered, no category match | Watch signal |
| `advertising` | Ad networks (stripped from analysis) | Low value |
| `cdn_infra` | CDN and infrastructure (cloudflare, aws) | Strip from analysis |
| `news` | News and media | Low risk |
| `other` | Fallback | Needs review |

Categories `cdn_infra` and `advertising` should be stripped before graph construction — they generate noise without behavioral signal.

### 1.2 Blocklist Sources (Confidence: HIGH)

**StevenBlack Unified Hosts** — The standard community reference. Consolidates adware, malware, fakenews, gambling, social, and porn extension lists. Contains ~79,000 base entries, extensible per category. Format is a plain-text hosts file, parseable with a Python line-reader. Available at: https://github.com/StevenBlack/hosts

**hagezi/dns-blocklists** — More comprehensive (~multi-million entries), categorized into tiers (Light, Normal, Pro, Ultimate). Updated daily. Separates security categories cleanly. Available at: https://github.com/hagezi/dns-blocklists

**Cloudflare Gateway Categories** (Confidence: HIGH) — Cloudflare categorizes domains into two taxonomies used by their DNS filtering product (Cloudflare One / Gateway):

Security categories (authoritative list from official docs):
`Anonymizer`, `Command and Control & Botnet`, `Compromised Domain`, `Cryptomining`, `DGA Domains`, `DNS Tunneling`, `Malware`, `Phishing`, `Potentially Unwanted Software`, `Scam`, `Spam`, `Spyware`

Content categories (official list):
`Adult Themes`, `Child Abuse`, `CIPA`, `Education`, `Entertainment`, `Gambling`, `Government & Politics`, `Health`, `Information Technology`, `Internet Communication`, `Questionable Content`, `Security Risks`, `Shopping & Auctions`, `Social & Family`, `Sports`, `Technology`, `Travel`, `Violence`

Special: `New Domains`, `Newly Seen Domains`, `Parked & For Sale Domains` — highly relevant for the `unknown_new` category signal.

Source: https://developers.cloudflare.com/cloudflare-one/traffic-policies/domain-categories/
(Updated Oct 2025 — 3 new categories added under Technology parent)

### 1.3 Local Lookup Architecture (Confidence: HIGH)

Build a static category map loaded at startup from a SQLite table. Populate it from:

1. Parse StevenBlack hosts files into category buckets at install time
2. Load hagezi category-specific lists for security domains
3. Maintain a `user_overrides` table for guardian-defined category corrections

```
dns_category_map
  domain TEXT PRIMARY KEY
  category TEXT NOT NULL
  source TEXT          -- 'stevenblack' | 'hagezi' | 'manual' | 'llm_inferred'
  confidence REAL      -- 0.0–1.0
  last_seen TIMESTAMP
```

**Handling unknown domains:** When a DNS query arrives for a domain not in the map:

1. Check TLD heuristics (e.g., `.onion` → `darkweb`, `.bit` → `crypto`)
2. Check subdomain: if `mail.unknowndomain.com`, inherit parent class `other`, flag `unknown_new`
3. Check domain age signal: newly registered domains (WHOIS lookup if network available) → `unknown_new`
4. Queue for LLM inference: pass bare domain string to LLM with taxonomy prompt, cache result
5. Default to `unknown_new` and surface to guardian

**Do not block on unknown resolution.** Log the raw query, assign `unknown_new`, and resolve asynchronously. The pipeline must not stall waiting for categorization.

### 1.4 Category Lookup in Python

```python
# Recommended: dnspython for DNS capture + custom SQLite category map
# dnspython >= 2.7 (current as of 2025)

import sqlite3
import hashlib

def categorize_domain(domain: str, conn: sqlite3.Connection) -> str:
    # Normalize: strip www prefix and trailing dots
    normalized = domain.lstrip("www.").rstrip(".")

    cursor = conn.execute(
        "SELECT category FROM dns_category_map WHERE domain = ?",
        (normalized,)
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    # Try parent domain (e.g., sub.example.com -> example.com)
    parts = normalized.split(".")
    if len(parts) > 2:
        parent = ".".join(parts[-2:])
        cursor = conn.execute(
            "SELECT category FROM dns_category_map WHERE domain = ?",
            (parent,)
        )
        row = cursor.fetchone()
        if row:
            return row[0]

    return "unknown_new"
```

---

## 2. Behavioral Graph Modeling

### 2.1 Graph Model Design (Confidence: HIGH)

The recommended graph representation for OpenGuardian is a **temporal knowledge graph** with category-level nodes (not domain-level nodes) for the guardian-visible surface, and a separate raw event store for internal processing.

**Node types:**

| Node Label | Properties | Privacy Tier |
|---|---|---|
| `User` | `user_id`, `name`, `age_group` | Guardian-visible |
| `Device` | `device_id`, `mac_hash` | Guardian-visible |
| `ActivityCategory` | `category`, `display_name` | Guardian-visible |
| `TimeSlot` | `date`, `hour_bucket` (0–23), `day_of_week` | Guardian-visible |
| `Session` | `session_id`, `start_ts`, `end_ts`, `category` | Internal |

**Edge types:**

| Edge | From → To | Properties | Privacy Tier |
|---|---|---|---|
| `OWNS` | User → Device | `assigned_at` | Guardian-visible |
| `ACCESSED` | Device → ActivityCategory | `timestamp`, `duration_s`, `query_count` | Guardian-visible |
| `OCCURRED_IN` | Session → TimeSlot | `date`, `hour_bucket` | Guardian-visible |
| `BELONGS_TO` | Session → ActivityCategory | `query_count` | Internal |

**Raw domain events are stored in a separate flat log table, never in the graph.** The graph is constructed from already-categorized events.

### 2.2 Session Construction from DNS Queries (Confidence: MEDIUM-HIGH)

DNS queries do not carry natural session boundaries. Session construction uses a **sliding time-window gap model**:

```
Session boundary rule:
  - A new session begins when a gap of > T_gap occurs between DNS queries
    to the same category from the same device
  - T_gap = 15 minutes is the standard for web behavioral studies
  - A session minimum length is 2 queries (filter single-query noise)
```

**Algorithm:**

```
Input: sorted stream of (timestamp, device_id, category) tuples

For each device:
  current_session = None
  for each event in sorted order:
    if current_session is None:
      current_session = open_session(event)
    elif event.timestamp - current_session.last_ts > T_gap:
      close_session(current_session)
      current_session = open_session(event)
    elif event.category != current_session.category:
      # Multi-category sessions: allow category blending within gap window
      current_session.add_category(event.category)
      current_session.last_ts = event.timestamp
    else:
      current_session.last_ts = event.timestamp
      current_session.query_count += 1
  close remaining session
```

Sessions capture: `start_time`, `end_time`, `primary_category` (most queried), `categories_seen` (set), `query_count`, `duration_minutes`.

**Time-of-day binning:** Map timestamps to `hour_bucket` (0–23) and `day_period` labels:

| hour_bucket | day_period |
|---|---|
| 0–5 | late_night |
| 6–8 | morning |
| 9–11 | school_morning |
| 12–13 | school_midday |
| 14–16 | school_afternoon |
| 17–20 | after_school |
| 21–23 | evening |

This mapping is guardian-configurable to reflect school schedule context provided during onboarding.

### 2.3 NetworkX-Temporal for Graph Construction (Confidence: HIGH)

`networkx-temporal` v1.3.0 (December 2025) is the recommended Python package for the temporal graph layer. It extends NetworkX with `TemporalDiGraph` and snapshot-based slicing.

```bash
pip install networkx-temporal  # requires Python 3.7+
```

Key APIs:
- `TemporalDiGraph` — directed temporal graph, appropriate for `Device → ACCESSED → ActivityCategory` relationships
- `slice(attr="time", bins=n)` — partition graph into time snapshots (daily, weekly)
- `temporal_degree()` — how active a node is across time slices (signals engagement level)
- `to_snapshots()` / `from_snapshots()` — convert between representations for LLM serialization

For a PoC with a single device and ~weeks of data, `networkx-temporal` running in-memory is appropriate. **Do not use Neo4j for PoC** — it adds operational complexity (Java runtime, daemon process) with no benefit at this scale.

Source: https://networkx-temporal.readthedocs.io/

### 2.4 Temporal Pattern Features for Baseline (Confidence: MEDIUM)

Extract these features per device per day for baseline construction and anomaly comparison:

```
Daily feature vector:
  - category_distribution: {category: query_count} (normalized to fractions)
  - active_hours: [hour_buckets with activity]
  - session_count: int
  - avg_session_duration_minutes: float
  - dominant_category: str (highest query_count)
  - new_categories_seen: [categories not in rolling 7-day window]
  - night_activity_ratio: queries in late_night / total queries
  - unknown_domain_ratio: unknown_new count / total queries
```

Store daily vectors in SQLite. The baseline is the rolling median of each feature over the onboarding week (7 days). The LLM receives a structured comparison of today's vector vs. baseline vector — not raw domains.

---

## 3. Privacy-Preserving Design Patterns

### 3.1 Data Separation Architecture (Confidence: HIGH)

Use a strict two-layer data model with explicit privacy tier labels:

```
Layer 1: Raw Event Store (PRIVATE — never exposed to guardian)
  Table: dns_raw_events
    id INTEGER PRIMARY KEY
    timestamp TEXT        -- ISO 8601
    device_id TEXT
    domain_hash TEXT      -- SHA-256(salt + domain) — see 3.2
    domain_tld TEXT       -- only TLD retained in queryable form, e.g. ".com"
    category TEXT         -- resolved category
    bytes_transferred INTEGER

Layer 2: Graph / Behavioral Store (GUARDIAN-VISIBLE)
  Table: activity_sessions
    session_id TEXT PRIMARY KEY
    device_id TEXT
    category TEXT
    start_ts TEXT
    end_ts TEXT
    query_count INTEGER
    duration_minutes REAL
    day_period TEXT

  Graph nodes/edges: ActivityCategory, TimeSlot, Session — no domain references
```

The pipeline flows in one direction: `dns_raw_events` → categorization → `activity_sessions` → graph. Raw events are read-only inputs; they are never read back from the application layer once graph construction is complete.

**Data retention:** Raw DNS event logs should be purged on a rolling window (recommended: 30 days for PoC, configurable). After purge, the behavioral graph and session aggregates remain. The guardian dashboard, LLM context, and email notifications draw exclusively from Layer 2.

### 3.2 Domain Hashing (Confidence: HIGH)

Per recent research (arxiv 2507.21904, 2025), salt-based hashing with per-record salts provides non-reversibility while preserving correlation for the same domain across sessions. For OpenGuardian:

```python
import hashlib
import os

# Generate once at install, store in config (never log to guardian surfaces)
DOMAIN_SALT = os.environ.get("OPENGUARDIAN_DOMAIN_SALT") or os.urandom(32).hex()

def hash_domain(domain: str) -> str:
    """One-way hash of domain for internal correlation without exposure."""
    normalized = domain.lower().strip().rstrip(".")
    return hashlib.sha256(f"{DOMAIN_SALT}:{normalized}".encode()).hexdigest()[:16]
```

The hash is used only in `dns_raw_events.domain_hash` for internal deduplication and correlation. It is never surfaced in outputs, reports, or LLM prompts.

**What the LLM receives (example):**
```
Device D01 activity summary for 2026-03-10:
  - 4.2 hours gaming (62% of active time) — baseline: 1.1 hours (455% above baseline)
  - 0.8 hours social media — baseline: 0.9 hours (normal)
  - 0.2 hours education — baseline: 1.5 hours (87% below baseline, school hours)
  - 3 queries to unknown_new domains (baseline: 0)
  - Night activity ratio: 0.34 (baseline: 0.02)
```

No domain names, no hashes, no IP addresses appear in LLM context.

### 3.3 Connector Privacy Classification (Confidence: MEDIUM)

Each connector manifest (`connector.json`) must declare a `privacy_class` for each field:

```json
{
  "connector": "network",
  "fields": {
    "domain": {"privacy_class": "raw_private", "retained": "hash_only"},
    "category": {"privacy_class": "derived_ok", "retained": "full"},
    "bytes_transferred": {"privacy_class": "aggregate_ok", "retained": "sum_per_session"},
    "device_id": {"privacy_class": "pseudonymous", "retained": "full"}
  }
}
```

`raw_private` fields are hashed or dropped before any data leaves the raw event store. This classification gates what can appear in the guardian dashboard and LLM prompts.

---

## 4. Baseline Anomaly Detection Patterns

### 4.1 Signal Taxonomy (Confidence: HIGH)

Five anomaly signal types from the requirements map to concrete feature comparisons:

**Signal 1: New category appearance**
- Detection: `category NOT IN baseline.categories_seen`
- Threshold: any first-ever appearance of `adult`, `vpn_proxy`, `darkweb`, `violence` → critical flag
- First appearance of `gambling`, `crypto` → warning flag
- First appearance of any other new category → informational

**Signal 2: Time-of-day shift**
- Detection: activity in a `day_period` with zero baseline activity
- Key signal: `night_activity_ratio > baseline.night_activity_ratio + 3 * stdev`
- School-hours absence: if `education` queries drop to zero during configured school hours → informational/warning

**Signal 3: Frequency spike**
- Detection: `today.session_duration[category] > baseline.session_duration[category] * multiplier`
- Recommended multipliers for LLM context: include ratio and z-score
- Do not hardcode thresholds in PoC — pass the numbers to the LLM for interpretation

**Signal 4: Duration anomaly**
- Detection: `today.avg_session_duration_minutes` vs `baseline.avg_session_duration_minutes` per category
- Unusually short sessions may indicate app-hopping / concealment behavior

**Signal 5: Unknown domain spike**
- Detection: `today.unknown_domain_ratio > baseline.unknown_domain_ratio * 5`
- Unknown domains during night hours is a compounding signal

### 4.2 Anomaly Scoring Architecture (Confidence: MEDIUM)

Since the PoC uses LLM-driven assessment (not hardcoded thresholds), the anomaly pipeline should:

1. Compute the daily feature vector
2. Compare to baseline vector, compute delta and z-score for each feature
3. Serialize comparison as structured text or JSON
4. Include relevant Known Risk files from `/known-risks/` directory as context
5. Pass to LLM with a role prompt: "You are a child safety analyst reviewing behavioral data..."

```python
# Example LLM context structure (no raw domains, no hashes)
context = {
    "user_profile": {
        "age_group": "child_10_13",
        "school_days": ["mon", "tue", "wed", "thu", "fri"],
        "school_hours": "08:00-15:00"
    },
    "baseline_period": "2026-03-01 to 2026-03-07",
    "analysis_date": "2026-03-10",
    "feature_comparison": [
        {
            "feature": "gaming_duration_hours",
            "today": 4.2,
            "baseline_median": 1.1,
            "z_score": 3.8,
            "delta_pct": 282
        },
        {
            "feature": "night_activity_ratio",
            "today": 0.34,
            "baseline_median": 0.02,
            "z_score": 5.1,
            "delta_pct": 1600
        }
    ],
    "new_categories_today": ["vpn_proxy"],
    "loaded_risk_files": ["risk_grooming_roblox.md", "risk_grooming_discord.md"]
}
```

### 4.3 Cross-Connector Signal Composition (Confidence: MEDIUM)

When multiple connectors are active, the LLM context should include a unified event timeline per day (category-level only, no raw content):

```
Timeline 2026-03-10:
  18:02 — gaming session started (device D01)
  18:45 — Discord: joined new server
  19:30 — messaging: DM sent to new contact (Discord connector)
  19:31 — cloud_storage: first-ever access
  19:32 — Discord: media sent in DM
  22:15 — gaming session ended
```

This timeline (category events + Discord structural events + no message content) matches the Known Risk progression pattern format defined in `risk_grooming_roblox.md`.

---

## 5. Email Notification Patterns

### 5.1 Scheduler Recommendation: APScheduler 4.x (Confidence: HIGH)

For OpenGuardian — a single-process, local-first application — **APScheduler 4.x** is the correct choice. Celery Beat requires an external message broker (Redis or RabbitMQ), which adds operational complexity unacceptable for a self-hosted home tool.

APScheduler 4.x (released 2024, stable in 2025) key changes from 3.x:
- `BlockingScheduler` + `BackgroundScheduler` merged into `Scheduler`
- Asyncio support via `AsyncScheduler` (backed by AnyIO, supports Trio too)
- `add_schedule()` replaces `add_job()` for recurring tasks
- `add_job()` now means "run once, immediately"
- Configurable data stores (SQLite, memory) for schedule persistence across restarts

```bash
pip install apscheduler>=4.0
```

**Two notification schedules:**

```python
from apscheduler import Scheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

scheduler = Scheduler()

# Weekly digest — every Monday 08:00
scheduler.add_schedule(
    send_weekly_digest,
    CronTrigger(day_of_week="mon", hour=8, minute=0),
    id="weekly_digest"
)

# Real-time critical alert check — every 5 minutes
scheduler.add_schedule(
    check_and_send_critical_alerts,
    IntervalTrigger(minutes=5),
    id="critical_alert_check"
)
```

Source: https://github.com/agronholm/apscheduler

### 5.2 Email Templating with Jinja2 (Confidence: HIGH)

Use Jinja2 for HTML email templates. Python's `smtplib` + `email.mime` handles delivery. No external email library needed for a local SMTP relay (e.g., Gmail SMTP, local Postfix).

**Pattern for dual-format (HTML + plain text fallback):**

```python
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader
import smtplib

def send_templated_email(
    to: str,
    subject: str,
    template_name: str,
    context: dict,
    smtp_config: dict
) -> None:
    env = Environment(loader=FileSystemLoader("templates/email"))
    html_template = env.get_template(f"{template_name}.html")
    text_template = env.get_template(f"{template_name}.txt")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_config["from_addr"]
    msg["To"] = to

    # Plain text first (fallback)
    msg.attach(MIMEText(text_template.render(**context), "plain"))
    # HTML second (preferred by clients)
    msg.attach(MIMEText(html_template.render(**context), "html"))

    with smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"]) as server:
        server.login(smtp_config["user"], smtp_config["password"])
        server.sendmail(smtp_config["from_addr"], to, msg.as_string())
```

### 5.3 Template Directory Structure

```
templates/email/
  weekly_digest.html       # full-width digest with category charts
  weekly_digest.txt        # plain text version
  critical_alert.html      # high-contrast alert layout
  critical_alert.txt
  _base.html               # shared header/footer layout
  _alert_item.html         # reusable anomaly item partial
```

Jinja2 template inheritance (`{% extends "_base.html" %}`) keeps the templates maintainable.

### 5.4 Email Content: Privacy Rules

Apply the same privacy rules to email content as to the dashboard:

- **Weekly digest:** Category names, session durations, trend charts — no domain names
- **Critical alert:** Anomaly type, plain-English LLM explanation, severity label — no domain names
- **Never include** raw domains, domain hashes, or IP addresses in any email output

```
Example critical alert subject: "OpenGuardian: Critical behavior flag — [child name], Monday 22:14"
Example body excerpt: "A significant deviation from [child name]'s baseline was detected.
  New activity category appeared for the first time: VPN/Proxy services.
  This occurred during late-night hours (10:14pm), outside baseline active periods.
  [LLM explanation paragraph]"
```

---

## 6. DNS Capture Implementation

### 6.1 Capture Method Options (Confidence: HIGH)

Three approaches for capturing DNS traffic on a local network, in order of recommendation for OpenGuardian PoC:

**Option A: Pi-hole / AdGuard Home Log API (recommended for PoC)**
If the household already runs Pi-hole or AdGuard Home as a DNS server, poll its query log API. No packet sniffing required; no root privileges needed at runtime.

- Pi-hole API: `GET /api/queries` — returns timestamped query log
- AdGuard Home API: `GET /control/querylog` — JSON with domain, client IP, answer
- Parse the response, normalize to Graph Event format

This is the lowest-friction integration for real households. Pi-hole is the dominant home DNS filter as of 2025–2026.

**Option B: Scapy packet sniffer (for direct capture)**
Requires root/administrator privileges. Filter on UDP port 53. Captures DNS queries before they reach any upstream resolver.

```python
from scapy.all import sniff, DNS, DNSQR, IP

def dns_packet_handler(packet):
    if packet.haslayer(DNS) and packet.getlayer(DNS).qr == 0:  # query only
        domain = packet[DNSQR].qname.decode().rstrip(".")
        src_ip = packet[IP].src
        yield {"timestamp": packet.time, "domain": domain, "device_ip": src_ip}

sniff(filter="udp port 53", prn=dns_packet_handler, store=False)
```

Requires `scapy` and root. Run as a dedicated capture process that writes to the raw event queue. The main application does not require root.

**Option C: dnspython resolver intercept**
`dnspython >= 2.7` supports resolver customization but does not passively capture traffic from other devices. Only useful for monitoring the local machine's own DNS queries. Not suitable for network-wide monitoring.

Source: https://medium.com/@aneess437/network-monitoring-with-python-and-scapy-arp-scanning-and-dns-sniffing-explained-8b4eb1c3ff58

### 6.2 VPN Evasion and Limitations

DNS monitoring has a fundamental limitation: if a device uses an encrypted DNS resolver (DNS-over-HTTPS, DNS-over-TLS) or a VPN that tunnels DNS, queries do not appear on the local network. The requirement document correctly identifies this as an open question.

Detection heuristic: if `unknown_domain_ratio` drops to near-zero AND overall query volume drops significantly compared to baseline, this may indicate VPN activation (queries are going elsewhere). Surface this as a warning, not a category hit.

---

## 7. Data Storage Recommendations

### 7.1 SQLite Schema (Confidence: HIGH)

SQLite is the correct database for a local, single-user PoC. No daemon, no configuration, portable, excellent Python support via `sqlite3` stdlib.

Use WAL mode for concurrent read/write performance:

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Raw event log (Layer 1, private)
CREATE TABLE dns_raw_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,        -- ISO 8601
    device_id   TEXT NOT NULL,
    domain_hash TEXT NOT NULL,        -- SHA-256 prefix, internal only
    domain_tld  TEXT,                 -- ".com", ".io" etc — low sensitivity
    category    TEXT NOT NULL,
    bytes_in    INTEGER DEFAULT 0
);
CREATE INDEX idx_raw_ts ON dns_raw_events(timestamp);
CREATE INDEX idx_raw_device ON dns_raw_events(device_id, timestamp);

-- Category map
CREATE TABLE dns_category_map (
    domain      TEXT PRIMARY KEY,
    category    TEXT NOT NULL,
    source      TEXT NOT NULL,        -- 'stevenblack'|'hagezi'|'manual'|'llm'
    confidence  REAL DEFAULT 1.0,
    updated_at  TEXT NOT NULL
);

-- Sessions (Layer 2, guardian-visible)
CREATE TABLE activity_sessions (
    session_id       TEXT PRIMARY KEY,
    device_id        TEXT NOT NULL,
    category         TEXT NOT NULL,
    start_ts         TEXT NOT NULL,
    end_ts           TEXT NOT NULL,
    query_count      INTEGER NOT NULL,
    duration_minutes REAL NOT NULL,
    day_period       TEXT NOT NULL,
    date             TEXT NOT NULL    -- YYYY-MM-DD for easy daily aggregation
);
CREATE INDEX idx_session_device_date ON activity_sessions(device_id, date);

-- Daily feature vectors for baseline comparison
CREATE TABLE daily_features (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT NOT NULL,
    date            TEXT NOT NULL,
    feature_json    TEXT NOT NULL,    -- serialized feature vector
    is_baseline     INTEGER DEFAULT 0,
    UNIQUE(device_id, date)
);

-- Anomaly flags
CREATE TABLE anomaly_flags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT NOT NULL,
    detected_at     TEXT NOT NULL,
    severity        TEXT NOT NULL,    -- 'informational'|'warning'|'critical'
    anomaly_type    TEXT NOT NULL,
    llm_explanation TEXT NOT NULL,
    notified        INTEGER DEFAULT 0,
    date            TEXT NOT NULL
);
```

---

## 8. Python Library Recommendations

| Library | Version | Purpose | Why |
|---|---|---|---|
| `dnspython` | >=2.7 | DNS protocol parsing | Standard, well-maintained |
| `scapy` | >=2.6 | Passive DNS packet capture | Only option for raw capture |
| `networkx` | >=3.3 | Graph construction and analysis | De-facto Python graph library |
| `networkx-temporal` | >=1.3.0 | Temporal graph snapshots | Published Dec 2025, active |
| `apscheduler` | >=4.0 | Task scheduling (alerts, digests) | Best fit for local single-process |
| `jinja2` | >=3.1 | Email template rendering | Standard templating engine |
| `sqlite3` | stdlib | Local data store | No external dependency |
| `hashlib` | stdlib | Domain hashing | No external dependency |
| `pydantic` | >=2.0 | Graph Event schema validation | Type-safe connector contracts |
| `httpx` | >=0.27 | LLM API calls (Ollama, OpenAI) | Async-capable, modern |

**Explicitly avoid:**
- Neo4j (Java runtime, operational overhead, overkill for PoC scale)
- Celery (requires Redis/RabbitMQ broker, not local-first)
- PyOD (ML anomaly detection library — unnecessary since LLM handles interpretation)
- Any cloud-only DNS categorization API as a hard dependency (offline-first requirement)

---

## 9. Known Gaps and Open Questions

1. **DNS-over-HTTPS evasion** — No reliable detection method via passive DNS monitoring alone. The VPN/DoH detection heuristic (query volume drop) is a proxy, not a solution. Future work: network-layer monitoring or firewall integration.

2. **Domain categorization freshness** — Static blocklists become stale. The `unknown_new` category is a partial mitigation. Refreshing the map requires scheduled re-download of blocklist files. Consider weekly refresh job via APScheduler.

3. **LLM context size limits** — If a device has a very active day (thousands of DNS queries → hundreds of sessions), the feature vector may exceed LLM context limits. Mitigation: aggregate to top-10 categories by duration, not full session list.

4. **Baseline robustness** — 7 days is a short baseline window. School holidays, sick days, or atypical weeks will corrupt the baseline. The requirement document notes this as an open question. Recommended mitigation: allow guardian to flag baseline days as "atypical" to exclude from baseline calculation.

5. **Multi-category sessions** — A session where gaming and social queries interleave (e.g., Discord while playing Roblox) needs a primary category assignment policy. Recommend: primary = category with most queries; secondary categories stored in session metadata.

6. **Private/incognito DNS** — Some browsers (Chrome, Firefox) use their own DoH resolvers even when configured to use local DNS. This bypasses Pi-hole and Scapy capture alike. No solution within DNS-only monitoring scope.

---

## Sources

- Cloudflare Domain Categories (official): https://developers.cloudflare.com/cloudflare-one/traffic-policies/domain-categories/
- Cloudflare Domain Category Improvements (Oct 2025): https://developers.cloudflare.com/changelog/2025-10-10-new-domain-categories/
- StevenBlack Unified Hosts: https://github.com/StevenBlack/hosts
- hagezi/dns-blocklists: https://github.com/hagezi/dns-blocklists
- networkx-temporal documentation (Dec 2025): https://networkx-temporal.readthedocs.io/
- networkx-temporal ScienceDirect paper (2025): https://www.sciencedirect.com/science/article/pii/S2352711025002444
- APScheduler GitHub (4.x): https://github.com/agronholm/apscheduler
- APScheduler vs Celery Beat comparison: https://leapcell.io/blog/scheduling-tasks-in-python-apscheduler-vs-celery-beat
- Privacy-Preserving Anonymization via Salt Hashing (arxiv 2507.21904, 2025): https://arxiv.org/abs/2507.21904
- DNS Packet Sniffing with Scapy: https://medium.com/@aneess437/network-monitoring-with-python-and-scapy-arp-scanning-and-dns-sniffing-explained-8b4eb1c3ff58
- DNS as Knowledge Graph (HAL, 2025): https://hal.science/hal-04887392v1/document
- Jinja2 HTML Email Templates: https://frankcorso.dev/email-html-templates-jinja-python.html
- Machine Learning for DNS Anomaly Detection (Medium, 2025): https://medium.com/@myth7672/machine-learning-for-suspicious-dns-query-detection-5566f3aa9a52
- Ollama Privacy-First Local LLM: https://www.cohorte.co/blog/run-llms-locally-with-ollama-privacy-first-ai-for-developers-in-2025
- Online Child Grooming Detection (Springer, 2025): https://link.springer.com/chapter/10.1007/978-3-031-62083-6_19
