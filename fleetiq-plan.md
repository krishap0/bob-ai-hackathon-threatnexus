# FLEETIQ — Implementation Plan
## IBM BoB AI Innovation Hackathon 2026 | Team ThreatNexus | Track: AI

---

## Top-Level Overview

**Goal:** Build FLEETIQ, an AI-powered supply chain disruption and fleet utilisation
assistant that satisfies the L2 official problem: identify shipments affected by
disruptions, suggest rerouting/carrier alternatives, detect idle fleet, and severity-rank
cold-chain temperature excursions — all surfaced in a single AI-generated operational
summary.

**Scope:** A working, locally-runnable full-stack web application with seeded mock data,
a Python/FastAPI backend, a React frontend, and genuine IBM watsonx.ai + IBM Bob
integration for the AI summary layer. No real external data feeds are required; the demo
runs entirely on deterministic seed data plus watsonx inference calls.

**Non-goals (MVP):** Real-time GPS telemetry ingestion, live carrier APIs, live port
congestion feeds, user authentication/RBAC, multi-tenancy, production database clustering.

---

## Scoring Alignment

| Criterion | Points | How FLEETIQ targets it |
|---|---|---|
| Technical Implementation Quality | 25 | Full-stack working app, real algorithms, watsonx SDK calls |
| Innovation & Differentiation | 25 | Multi-domain AI fusion — disruption + fleet + cold-chain in one assistant |
| Problem Depth & Vision | 15 | Detailed docs aligned to L2 problem spec |
| Working Demo & Functionality | 15 | Deterministic seed data guarantees reliable demo every run |
| IBM Bob Integration | 10 | Bob used as the conversational query interface over the disruption data |
| Documentation & Reproducibility | 10 | Complete setup-guide, architecture, env.example |

---

## Recommended Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend API | Python 3.11 + FastAPI | Fast to build, excellent async support, auto OpenAPI docs |
| Data Store | SQLite (via SQLAlchemy) | Zero-infrastructure, file-based, ships inside the repo as seed.db |
| Frontend | React 18 + Vite + TailwindCSS | Modern, fast build, widely known |
| Charts | Recharts | React-native, zero config |
| AI Summary | IBM watsonx.ai (configurable Granite model via `WATSONX_MODEL_ID`) via Python SDK | Official IBM AI, satisfies IBM Bob Integration criterion |
| Bob Integration | IBM Bob MCP server (Python) | Satisfies the load-bearing Bob criterion — query disruptions by natural language |
| Seed/Demo data | Python seed script (deterministic, no external calls) | Reliable demo, reproducible |
| Package management | pip + requirements.txt (backend), npm (frontend) | Beginner-friendly, standard |
| Containerisation | docker-compose.yml (optional, for judges) | One-command startup |
| CI | Existing .github/workflows/validate.yml | Do NOT modify |

---

## Recommended Folder Structure inside `src/`

```
src/
├── .env.example                   ← All env vars documented
├── README.md                      ← Layout explanation
│
├── backend/
│   ├── main.py                    ← FastAPI app entry point
│   ├── requirements.txt
│   ├── database.py                ← SQLAlchemy engine + session
│   ├── models/
│   │   ├── __init__.py
│   │   ├── disruption.py          ← Disruption ORM model
│   │   ├── shipment.py            ← Shipment ORM model
│   │   ├── fleet.py               ← Fleet/vehicle ORM model
│   │   └── cold_chain.py          ← Temperature reading ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── disruption.py          ← Pydantic response schemas
│   │   ├── shipment.py
│   │   ├── fleet.py
│   │   └── cold_chain.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── disruptions.py         ← /api/disruptions endpoints
│   │   ├── shipments.py           ← /api/shipments endpoints
│   │   ├── fleet.py               ← /api/fleet endpoints
│   │   ├── cold_chain.py          ← /api/cold-chain endpoints
│   │   └── summary.py             ← /api/summary (watsonx call)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── disruption_engine.py   ← Disruption detection algorithm
│   │   ├── impact_analyzer.py     ← Which shipments are affected
│   │   ├── route_recommender.py   ← Rerouting/carrier suggestions
│   │   ├── fleet_optimizer.py     ← Idle fleet detection
│   │   ├── cold_chain_ranker.py   ← Temperature severity ranking
│   │   └── watsonx_client.py      ← watsonx.ai SDK wrapper
│   ├── seed/
│   │   ├── seed_data.py           ← Deterministic demo seed script
│   │   └── data/
│   │       ├── disruptions.json
│   │       ├── shipments.json
│   │       ├── fleet.json
│   │       └── cold_chain.json
│   └── bob_mcp/
│       ├── server.py              ← IBM Bob MCP server
│       └── tools.py               ← Bob tool definitions
│
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── components/
        │   ├── layout/
        │   │   ├── Sidebar.jsx
        │   │   └── Header.jsx
        │   ├── dashboard/
        │   │   ├── KpiCard.jsx
        │   │   └── AISummaryPanel.jsx
        │   ├── disruptions/
        │   │   ├── DisruptionTable.jsx    ← filterable disruption list
        │   │   ├── DisruptionCard.jsx     ← detail expand/modal
        │   │   ├── AffectedShipmentsList.jsx ← shipments per disruption
        │   │   └── RecommendationsPanel.jsx  ← rerouting + carrier options
        │   ├── fleet/
        │   │   ├── FleetStatusChart.jsx   ← donut chart (active/idle/maint)
        │   │   └── IdleFleetGrid.jsx      ← redeployable vehicle cards
        │   └── cold_chain/
        │       ├── ExcursionTable.jsx     ← severity-ranked table
        │       └── SeverityBadge.jsx      ← color-coded badge component
        ├── pages/
        │   ├── Dashboard.jsx              ← Page 1: KPI cards + AI Summary
        │   ├── DisruptionsShipments.jsx   ← Page 2: disruptions + affected shipments + recommendations
        │   └── FleetColdChain.jsx         ← Page 3: idle fleet + cold-chain excursions
        ├── api/
        │   └── client.js                 ← Axios API client
        └── store/
            └── useAppStore.js            ← Zustand state store
```

---

## Data Models

### 1. Disruption

```
Disruption
  id               UUID PK
  type             ENUM (port_congestion, road_closure, severe_weather,
                         carrier_outage, geopolitical)
  title            String  — short human label
  description      String  — detail narrative
  severity         ENUM (low, medium, high, critical)
  status           ENUM (active, monitoring, resolved)
  affected_region  String  — e.g. "Port of Los Angeles"
  affected_routes  JSON    — list of route IDs affected
  started_at       DateTime
  resolved_at      DateTime (nullable)
  latitude         Float (nullable) — for map pin
  longitude        Float (nullable)
  source           String  — e.g. "Weather API", "Manual", "Sensor"
  created_at       DateTime
```

### 2. Shipment

```
Shipment
  id               UUID PK
  tracking_number  String UNIQUE
  origin           String
  destination      String
  current_location String
  carrier          String
  route_id         String  — joins to disruption.affected_routes
  status           ENUM (on_time, delayed, at_risk, diverted, delivered)
  cargo_type       ENUM (standard, cold_chain, hazmat, fragile)
  estimated_arrival DateTime
  actual_arrival   DateTime (nullable)
  weight_kg        Float
  value_usd        Float
  disruption_id    UUID FK → Disruption (nullable)
  impact_score     Float   — 0-100, computed by impact_analyzer
  created_at       DateTime
```

### 3. Fleet (Vehicle)

```
Fleet
  id               UUID PK
  vehicle_id       String UNIQUE — e.g. "TRK-042"
  vehicle_type     ENUM (truck, van, ship, rail_car, air_freight)
  status           ENUM (active, idle, maintenance, decommissioned)
  current_location String
  capacity_kg      Float
  available_capacity_kg Float
  last_active_at   DateTime
  idle_since       DateTime (nullable)
  assigned_route   String (nullable)
  redeployable     Boolean — computed: status=idle AND available_capacity > 0
  latitude         Float (nullable)
  longitude        Float (nullable)
```

### 4. ColdChainReading

```
ColdChainReading
  id               UUID PK
  shipment_id      UUID FK → Shipment
  sensor_id        String
  recorded_at      DateTime
  temperature_c    Float
  humidity_pct     Float (nullable)
  required_min_c   Float  — e.g. -20 for frozen
  required_max_c   Float  — e.g. -18 for frozen
  excursion        Boolean — computed: temp outside [min, max]
  excursion_duration_min Float (nullable)
  severity         ENUM (none, minor, moderate, severe, critical)
  severity_score   Float  — 0-100, used for ranking
```

---

## Algorithms and AI

### A. Disruption Detection (disruption_engine.py)

**Rule-based engine** — no ML needed; all disruptions are seeded with deterministic
status. Engine evaluates:
- Severity threshold: critical/high disruptions → trigger affected-shipment scan
- Geographic overlap: disruption.affected_region matched against shipment.current_location
  and shipment.route_id
- Temporal window: disruptions within ±72h of estimated_arrival are "in window"
- Output: a scored list of (disruption, affected_shipments) tuples

### B. Affected Shipment Identification (impact_analyzer.py)

For each active disruption:
1. Filter shipments where route_id ∈ disruption.affected_routes
2. Filter shipments where status NOT IN (delivered, diverted)
3. Compute impact_score:
   - Base: severity weight (critical=100, high=75, medium=50, low=25)
   - Multiplier: days_until_arrival proximity (closer = higher risk)
   - Cargo type modifier: cold_chain +20, hazmat +15, fragile +10
   - Value modifier: log10(value_usd) * 5
4. Sort by impact_score descending
5. Persist updated impact_score to DB

### C. Route/Carrier Recommendation (route_recommender.py)

For each affected shipment, generate 2-3 recommendations:
- **Same carrier, alternate route:** swap route_id to a non-disrupted route to
  same destination, estimate +N hours delay
- **Alternate carrier:** pick next-best carrier from a static carrier scoring table
  (cost_index, reliability_score, speed_score), explain trade-offs
- **Hold and wait:** estimated disruption resolution time vs. delay cost trade-off

Output per recommendation:
- recommendation_type (reroute | carrier_change | hold)
- description (human-readable)
- estimated_additional_hours
- estimated_cost_delta_usd
- trade_off_summary (string: "Faster by 12h but costs $400 more")

### D. Idle Fleet Detection (fleet_optimizer.py)

1. Query all Fleet where status = idle
2. Score each idle vehicle for redeployment suitability:
   - proximity_score: distance from idle location to disrupted route origin
     (use Haversine formula with static lat/lon from seed data)
   - capacity_match_score: available_capacity_kg vs. stranded shipment weight
   - type_match_score: vehicle_type matches cargo requirements
3. Rank idle fleet by composite redeployment_score
4. Tag top-N vehicles as `redeployable=True`

### E. Cold-Chain Severity Ranking (cold_chain_ranker.py)

For each ColdChainReading where excursion=True:
1. Compute severity based on:
   - magnitude: abs(temperature_c - nearest_bound) → degrees outside range
   - duration: excursion_duration_min
   - cargo sensitivity: lookup table (frozen food, pharmaceuticals, fresh produce)
2. Severity bands:
   - critical: magnitude > 10°C OR duration > 240 min
   - severe: magnitude 5-10°C OR duration 120-240 min
   - moderate: magnitude 2-5°C OR duration 60-120 min
   - minor: magnitude < 2°C AND duration < 60 min
3. severity_score = (magnitude * 5) + (duration_min / 10) — capped at 100
4. Output ranked list, sorted by severity_score descending

### F. AI Operational Summary (watsonx_client.py)

Uses **IBM watsonx.ai** with the model specified by the `WATSONX_MODEL_ID`
environment variable. Default value (if not set): `ibm/granite-3-8b-instruct`
— a current, supported IBM Granite model as of 2025. The model ID is never
hardcoded anywhere in application code; it is always read from env.

**Supported model IDs (examples — all configurable via env):**
- `ibm/granite-3-8b-instruct` (recommended default — current, supported)
- `ibm/granite-3-2b-instruct` (faster, lower cost)
- `ibm/granite-13b-chat-v2` (if available in your project region)

**Prompt construction:**
Gather current statistics from DB:
- Active disruption count + breakdown by type
- Affected shipment count + top 3 highest impact_score shipments
- Idle fleet count + top redeployable vehicles
- Cold-chain excursion count + critical/severe count

Build a structured prompt:
```
You are FLEETIQ, an expert supply chain operations assistant.
Summarise the current operational status and provide prioritised action items.

Current Data:
- Active disruptions: {n} ({breakdown})
- Shipments at risk: {n} (top risk: {tracking_number}, impact score {score})
- Idle fleet available: {n} vehicles
- Cold-chain excursions: {n} active, {critical_count} critical
- Top recommendation: {top_reco}

Provide:
1. One-paragraph operational summary (3-4 sentences, executive tone)
2. Top 3 prioritised action items (numbered list)
3. One risk the team should watch in the next 24 hours
```

**SDK call:** `ibm-watsonx-ai` Python package, `ModelInference` class,
`generate_text()` method. Parameters: `max_new_tokens=400`, `temperature=0.3`.

**Model ID loading pattern (in watsonx_client.py):**
```python
model_id = os.getenv("WATSONX_MODEL_ID", "ibm/granite-3-8b-instruct")
```

### G. IBM Bob MCP Integration (bob_mcp/server.py)

Bob is the **conversational query interface** — judges can type natural-language
questions to Bob and Bob retrieves live data from the FLEETIQ database.

Bob MCP tools exposed:
- `get_active_disruptions` — lists current active disruptions with severity
- `get_affected_shipments` — returns shipments at risk, filterable by severity
- `get_idle_fleet` — returns redeployable vehicles near a given region
- `get_cold_chain_alerts` — returns temperature excursions ranked by severity
- `get_ai_summary` — triggers the watsonx summary generation and returns it
- `get_shipment_recommendations` — returns rerouting options for a given tracking number

This makes Bob load-bearing: Bob users can manage disruptions entirely through
natural language without touching the UI.

---

## API Endpoints

```
GET  /api/disruptions                    — list all disruptions (filter: status, type)
GET  /api/disruptions/{id}               — single disruption detail
GET  /api/disruptions/{id}/affected      — shipments affected by this disruption

GET  /api/shipments                      — list shipments (filter: status, cargo_type)
GET  /api/shipments/{id}                 — single shipment detail
GET  /api/shipments/{id}/recommendations — rerouting/carrier options

GET  /api/fleet                          — list all fleet (filter: status)
GET  /api/fleet/idle                     — idle + redeployable vehicles only

GET  /api/cold-chain                     — all readings with excursion=True
GET  /api/cold-chain/ranked              — excursions sorted by severity_score

GET  /api/summary                        — generates and returns watsonx AI summary
GET  /api/summary/stats                  — raw stats object used to build summary

POST /api/seed                           — re-run seed (dev only, guarded by APP_ENV)
GET  /health                             — liveness probe
```

---

## UI/Dashboard Pages

Three pages cover all four L2 requirements.

### Page 1 — Operations Dashboard (/)
**Covers:** Overview + AI summary
- 4 KPI cards: Active Disruptions, Shipments at Risk, Idle Fleet Vehicles, Cold-Chain Alerts
- Recent disruptions mini-list (top 5 active, severity-badged)
- "Generate AI Summary" button + AI Operational Summary panel (calls `/api/summary`,
  displays result with typewriter animation, shows raw stats in collapsible panel)

### Page 2 — Disruptions & Shipments (/disruptions)
**Covers:** L2 requirements 1 (affected shipments) and 2 (rerouting/carrier recommendations)
- Top section: Filterable disruption table (by type, severity, status)
- Disruption row expands to show: affected routes, timeline, status
- Bottom section (linked): clicking a disruption loads its affected shipments in a
  side panel — sortable by impact score
- Selecting a shipment from the panel opens the Recommendations drawer:
  - 3 options: Alternate Route / Alternate Carrier / Hold & Wait
  - Each option shows: estimated additional hours, cost delta, trade-off summary string

### Page 3 — Fleet & Cold Chain (/fleet-coldchain)
**Covers:** L2 requirements 3 (idle fleet redeployment) and 4 (cold-chain severity)
- Top section — Fleet Utilisation:
  - Donut chart: active vs idle vs maintenance count
  - Idle fleet grid cards: vehicle ID, type, location, redeployment score
  - "Deploy" button on each card (simulated — updates status to active)
- Bottom section — Cold-Chain Monitor:
  - Severity-ranked excursion table: shipment, cargo type, temp reading, deviation, duration, severity badge
  - Severity badge color: critical=red, severe=orange, moderate=yellow, minor=blue
  - Row expansion: temperature vs threshold mini-chart, linked shipment detail

---

## End-to-End Data Flow

```
Seed Script
  → writes Disruptions, Shipments, Fleet, ColdChainReadings to SQLite

FastAPI App Start
  → runs impact_analyzer, cold_chain_ranker, fleet_optimizer on all seeded data
  → persists impact_score, severity_score, redeployable flags back to DB

React Frontend
  → fetches /api/disruptions, /api/shipments, /api/fleet, /api/cold-chain on load
  → renders dashboards, tables, charts

User clicks "Generate AI Summary"
  → GET /api/summary
  → backend collects stats
  → watsonx_client.py sends prompt to watsonx.ai
  → returns generated text
  → frontend displays with typewriter animation

Bob CLI User types "What are the active disruptions?"
  → Bob calls MCP tool get_active_disruptions
  → MCP server queries SQLite via SQLAlchemy
  → returns structured result to Bob
  → Bob formats and displays to user
```

---

## IBM Technology Integration

### IBM watsonx.ai
- **Where:** `/api/summary` endpoint — `watsonx_client.py`
- **Model:** Configured via `WATSONX_MODEL_ID` env var. Default: `ibm/granite-3-8b-instruct`
  (current, supported IBM Granite model). Never hardcoded.
- **SDK:** `ibm-watsonx-ai` Python package (pip installable)
- **Credentials needed:** `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`, `WATSONX_MODEL_ID` (optional, has default)
- **Genuineness:** The entire AI Operational Summary is LLM-generated at runtime
  from live DB stats — not hardcoded strings

### IBM Bob
- **Where:** `src/backend/bob_mcp/server.py` — a registered MCP server
- **Role:** Conversational query interface for all FLEETIQ data
- **Tools:** 6 MCP tools covering every data domain
- **Genuineness:** Bob tools call real DB queries and real watsonx endpoint;
  judges can interact with Bob during the demo

---

## Security Considerations

1. All secrets via environment variables — never committed (`.gitignore` covers `.env`)
2. `src/.env.example` documents every variable with dummy values
3. `/api/seed` endpoint is guarded by `APP_ENV != production` check
4. SQLite database file (`fleetiq.db`) is added to `.gitignore`
5. CORS restricted to `localhost:5173` (Vite dev) in `main.py`
6. No user authentication needed for MVP (demo tool, not production)

---

## Testing Strategy

**Minimal but sufficient for hackathon:**

1. **Backend unit tests** (`pytest`) — 5-8 tests covering:
   - `impact_analyzer.compute_impact_score()` — verify scoring formula
   - `cold_chain_ranker.rank_excursions()` — verify severity band assignment
   - `fleet_optimizer.find_redeployable()` — verify idle filter
   - `route_recommender.get_recommendations()` — verify output structure
2. **API smoke tests** (`pytest` + `httpx`) — verify all GET endpoints return 200
3. **Frontend** — manual verification (no automated tests for MVP)

Run with: `cd src/backend && pytest tests/ -v`

---

## Demo Scenario (3-5 minute video)

**Narrative:** "A perfect storm hits our supply chain. Three simultaneous disruptions.
FLEETIQ identifies every at-risk shipment, finds unused trucks, catches a cold-chain
failure, and generates an AI briefing — in seconds."

**Scene 1 (30s) — Dashboard:**
Open the app. Show 4 KPI cards: 3 active disruptions, 8 shipments at risk,
4 idle trucks, 2 cold-chain alerts. Briefly narrate each number.

**Scene 2 (60s) — Disruptions & Shipments page:**
Filter disruptions by "critical". Click the Port of Los Angeles congestion card.
Affected shipments panel loads — highlight the top impact-score shipment.
Click it → Recommendations drawer opens. Walk through the 3 options (Alternate
Route, Alternate Carrier, Hold & Wait). Read the trade-off string for Alternate
Carrier aloud.

**Scene 3 (60s) — Fleet & Cold Chain page:**
Top section: Fleet donut chart. Click into Idle Fleet grid — 4 trucks shown.
Click "Deploy" on the highest redeployment-score truck. Card updates to "Active".
Scroll to Cold-Chain section: show 2 excursions. Critical pharma shipment highlighted
in red — 8°C above max, 3h duration. Expand row to show temperature mini-chart.

**Scene 4 (60s) — AI Summary (back to Dashboard):**
Click "Generate AI Summary". Loading spinner appears. Typewriter animation runs as
Granite model generates the operational briefing. Read the 3 action items aloud.
Point out that these are generated from real live data — not hardcoded.

**Scene 5 (45s) — IBM Bob terminal:**
Type "What are the active disruptions?" — Bob calls MCP tool, returns ranked list.
Type "Which shipments need rerouting?" — Bob returns affected shipments with impact scores.
Type "Generate an operational summary" — Bob calls watsonx, displays result.

---

## Required Screenshots (minimum 3, recommended 5)

```
01-dashboard-kpi.png              ← Dashboard with all 4 KPI cards lit up
02-disruptions-shipments.png      ← Disruption table with affected shipments panel open
03-shipment-recommendations.png   ← Rerouting recommendations drawer for a high-risk shipment
04-fleet-coldchain.png            ← Fleet donut chart + idle grid + cold-chain excursion table
05-ai-summary.png                 ← watsonx AI summary displayed with typewriter animation
```

---

## Documentation to Create

| File | Content |
|---|---|
| `docs/problem-statement.md` | L2 problem narrative, affected personas (logistics managers, fleet ops), cost of disruptions |
| `docs/solution-overview.md` | FLEETIQ concept, 5-step workflow, IBM tech integration specifics |
| `docs/architecture.md` | Mermaid architecture diagram + component table + data flow steps |
| `docs/setup-guide.md` | Prerequisites, env vars table, install commands, run commands, troubleshooting |
| `src/README.md` | Layout of src/, which folder to start from |
| `src/backend/bob_mcp/README.md` | How to register and use the Bob MCP server |

---

## Presentation Slides to Create

| Slide | Content |
|---|---|
| 1 | Title: FLEETIQ — Team ThreatNexus, Track: AI |
| 2 | Problem: Supply chain disruptions cost $X/day — show pain points per L2 spec |
| 3 | Solution: FLEETIQ architecture overview (simple diagram) |
| 4 | Technical deep-dive: 5 algorithms + watsonx + Bob MCP |
| 5 | Demo screenshot montage (6 screenshots) |
| 6 | IBM Technology: watsonx Granite — where, how, why genuine |
| 7 | IBM Bob: MCP tools — show Bob conversation screenshot |
| 8 | Impact & Vision: production scale-out potential |
| 9 | Team: names, roles |

**Save as:** `presentation/slides.pdf`

---

## GitHub Actions Validation Requirements

The existing `validate.yml` checks these. All must pass before submission:

1. `submission.yaml` filled: team.name="ThreatNexus", track="AI", lead fields, title="FLEETIQ"
2. `problem_statement` and `solution_summary` are non-empty
3. `key_features` has ≥1 entry (plan for 5)
4. `src/` has actual source code files (not just README)
5. `demo/demo-video-link.txt` replaced with real video URL
6. `README.md` has no `[Your Project Title Here]` or `[Your Team Name]` placeholder text

---

## Risks, Dependencies, and Pre-requisites

### Required Credentials / API Keys
| Credential | How to get | Risk if missing |
|---|---|---|
| `WATSONX_API_KEY` | IBM Cloud → watsonx.ai → API Keys | AI Summary fails — implement graceful fallback message |
| `WATSONX_PROJECT_ID` | IBM Cloud → watsonx.ai → Project Settings | Same as above |
| `WATSONX_URL` | Regional endpoint — default `https://us-south.ml.cloud.ibm.com` | Can be hardcoded as default |

**Fallback strategy:** If watsonx credentials are missing, the `/api/summary` endpoint
returns a static template-filled string with real DB stats but no LLM generation.
This ensures the demo works even without credentials, but the AI submission requires
real credentials for genuine IBM integration.

### Technical Risks
| Risk | Mitigation |
|---|---|
| watsonx API rate limits during demo | Cache last summary response, show cached version |
| SQLite file corruption | Seed script is idempotent — re-run to rebuild |
| Vite/npm build issues on judge's machine | Provide pre-built `dist/` OR serve frontend from FastAPI static files |
| Bob MCP server registration complex | Provide copy-paste config snippet in bob_mcp/README.md |
| Demo video upload | Record early, upload to YouTube unlisted, test link from private window |

### Setup Requirements
- Python 3.11+
- Node.js 18+
- pip + npm
- IBM Cloud account with watsonx.ai access
- IBM Bob desktop app installed (for Bob MCP demo)

---

## Phased Implementation Plan

### Phase 1 — Repository Setup & Submission Metadata
**Intent:** Make the GitHub Actions validator go green immediately. Fill all required
fields. No application code beyond the health-check stub.

**Tasks:**
1. Fill `submission.yaml` with team name "ThreatNexus", track "AI", lead/member info,
   title "FLEETIQ", problem_statement, solution_summary, key_features, tech_stack
2. Update `README.md` — replace all placeholders with FLEETIQ content
3. Create `src/backend/main.py` with minimal FastAPI health-check endpoint
   so the "src/ not empty" CI check passes
4. Update `src/.env.example` with all FLEETIQ variables including `WATSONX_MODEL_ID`
5. Update `demo/demo-video-link.txt` — remove blocked placeholder; mark as pending

**Expected outcome:** `✅ Validate Submission` GitHub Action is green.

**Status:** [x] done — all 10 local validation checks pass

---

### Phase 2 — Backend Foundation
**Intent:** Stand up the FastAPI app with SQLAlchemy models, seed script, and all
API endpoints returning real seeded data.

**Tasks:**
1. Create `src/backend/requirements.txt` ✓
2. Create `src/backend/database.py` — SQLAlchemy engine + get_db dependency ✓
3. Create 5 ORM models (Disruption, Carrier, Shipment, Fleet, ColdChainReading) ✓
4. Create 5 Pydantic schemas ✓
5. Create `seed/seed_data.py` with deterministic data: ✓
   - 5 disruptions (port, weather, carrier outage, geopolitical, road closure)
   - 5 carriers
   - 15 shipments (mix of cargo types, statuses, routes)
   - 10 fleet vehicles (4 idle, 4 active, 2 maintenance)
   - 11 cold-chain readings (6 excursions)
6. Create `main.py` with CORS, router includes, lifespan startup seed ✓
7. Create 6 routers (disruptions, shipments, fleet, cold_chain, carriers, summary stub) ✓
8. Create 5 Phase-3-stub service files ✓
9. Create smoke test suite (20 tests, 0 failures) ✓

**Expected outcome:** Backend runs on `localhost:8000`, all GET endpoints return
real seeded data, `/docs` shows full OpenAPI spec.

**Status:** [x] done — 20/20 smoke tests pass

---

### Phase 3 — Business Logic Services
**Intent:** Implement the 5 algorithms that make FLEETIQ intelligent.

**Tasks:**
1. `disruption_engine.py` — active disruption query + trigger logic
2. `impact_analyzer.py` — impact_score computation for all affected shipments
3. `route_recommender.py` — generate 3 recommendation types per shipment
4. `fleet_optimizer.py` — Haversine proximity scoring, redeployable flag
5. `cold_chain_ranker.py` — severity bands + severity_score computation
6. Wire services into FastAPI startup event: run all scoring on boot
7. Add `/api/shipments/{id}/recommendations` endpoint
8. Add `/api/fleet/idle` endpoint
9. Add `/api/cold-chain/ranked` endpoint

**Expected outcome:** API returns scored, ranked data. Recommendations are
meaningful and include trade-off strings.

**Status:** [ ] pending

---

### Phase 4 — IBM watsonx.ai Integration
**Intent:** Implement genuine LLM-powered operational summary with a configurable,
non-deprecated model ID.

**Tasks:**
1. Add `ibm-watsonx-ai` to `requirements.txt`
2. Create `services/watsonx_client.py`:
   - Read `WATSONX_MODEL_ID` from env; default to `ibm/granite-3-8b-instruct`
   - Read `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL` from env
   - Implement `generate_summary(stats_dict) → str`
   - Build structured prompt from stats dict
   - Instantiate `ModelInference(model_id=model_id, credentials=..., project_id=...)`
   - Call `model.generate_text(prompt=prompt, params={...})`
3. Create `/api/summary/stats` endpoint (returns raw stats dict used by the prompt)
4. Create `/api/summary` endpoint (collects stats, calls watsonx, returns generated text)
5. Implement fallback: if credentials missing or call fails, return a template string
   filled with real DB stats and a note that watsonx credentials are required for AI generation
6. Test with real watsonx credentials; verify model_id is read from env, not hardcoded

**Expected outcome:** `GET /api/summary` returns a genuine Granite-generated
operational briefing. Changing `WATSONX_MODEL_ID` in `.env` changes which model
is called — zero code changes required.

**Status:** [ ] pending

---

### Phase 5 — IBM Bob MCP Server
**Intent:** Make Bob a load-bearing interface to FLEETIQ data.

**Tasks:**
1. Create `src/backend/bob_mcp/server.py` using Bob MCP SDK
2. Implement 6 MCP tools (get_active_disruptions, get_affected_shipments,
   get_idle_fleet, get_cold_chain_alerts, get_ai_summary, get_shipment_recommendations)
3. Each tool queries the SQLite DB directly via SQLAlchemy
4. Create `bob_mcp/README.md` with registration instructions and example queries
5. Test each Bob tool with the Bob desktop app
6. Add `bob_mcp/requirements.txt` or fold into backend requirements

**Expected outcome:** Bob can answer "What are the critical disruptions?" and
"Which shipments need rerouting?" with live data from FLEETIQ.

**Status:** [ ] pending

---

### Phase 6 — React Frontend
**Intent:** Build the 3-page dashboard that covers all four L2 requirements.

**Tasks:**
1. Scaffold Vite + React + TailwindCSS project in `src/frontend/`
2. Create API client (`api/client.js`) pointing to `localhost:8000`
3. Create Zustand store for shared state
4. Build layout: Sidebar (3 nav items) + Header with FLEETIQ branding
5. Build Dashboard page (`/`):
   - 4 KPI cards (Active Disruptions, Shipments at Risk, Idle Fleet, Cold-Chain Alerts)
   - Recent disruptions mini-list (top 5)
   - AI Summary panel with "Generate" button + typewriter animation
6. Build Disruptions & Shipments page (`/disruptions`):
   - Filterable disruption table
   - Affected shipments side panel (loads when a disruption is selected)
   - Recommendations drawer (loads when a shipment is selected) — shows 3 options + trade-offs
7. Build Fleet & Cold Chain page (`/fleet-coldchain`):
   - Fleet donut chart + idle fleet grid cards + Deploy button
   - Cold-chain excursion table sorted by severity_score + row expansion
8. Wire all pages to real API data — no hardcoded UI data
9. Verify all pages load with real data; verify AI Summary generates via watsonx

**Expected outcome:** Complete 3-page React app covering all four L2 requirements,
fully connected to backend, with working AI Summary generation.

**Status:** [ ] pending

---

### Phase 7 — Testing
**Intent:** Ensure algorithms are correct and all API endpoints work.

**Tasks:**
1. Create `src/backend/tests/` directory
2. Write 5 unit tests for the 5 service modules
3. Write 1 smoke test per API endpoint (10 tests)
4. Run `pytest tests/ -v` and verify all pass
5. Manual test of frontend in Chrome

**Expected outcome:** `pytest` exits 0 with all tests passing.

**Status:** [ ] pending

---

### Phase 8 — Documentation
**Intent:** Meet the documentation & reproducibility scoring criterion.

**Tasks:**
1. Write `docs/problem-statement.md` — full L2 problem narrative
2. Write `docs/solution-overview.md` — FLEETIQ mechanism + IBM tech explanation
3. Write `docs/architecture.md` — Mermaid diagram + component table + data flow
4. Write `docs/setup-guide.md` — exact tested steps from clone to running app
5. Update `src/README.md` with final folder layout
6. Update `src/.env.example` with all final variables
7. Proof-read all docs — no template placeholder text remaining

**Expected outcome:** A judge can follow `docs/setup-guide.md` from a fresh
terminal and have the app running without asking any questions.

**Status:** [ ] pending

---

### Phase 9 — Demo Preparation
**Intent:** Produce all demo artifacts needed for submission.

**Tasks:**
1. Take 6 screenshots of the running application (follow naming convention)
2. Place in `demo/screenshots/` with names `01-*.png` through `06-*.png`
3. Record 3-5 minute demo video following the Demo Scenario script above
4. Upload video to YouTube (unlisted) or Loom
5. Update `demo/demo-video-link.txt` with real URL
6. If deployed: update `demo/live-demo-url.txt`; otherwise write "NOT DEPLOYED"

**Expected outcome:** All demo artifacts present, video link works from
incognito window, screenshots show running app with real data.

**Status:** [ ] pending

---

### Phase 10 — Presentation
**Intent:** Create the slide deck for submission.

**Tasks:**
1. Create 9-slide deck following the Presentation Slides plan above
2. Include architecture diagram (screenshot from docs/architecture.md)
3. Include 3-4 app screenshots
4. Include Bob MCP conversation screenshot
5. Export as `presentation/slides.pdf`

**Expected outcome:** `presentation/slides.pdf` exists and covers all
evaluation criteria with visual diagrams.

**Status:** [ ] pending

---

### Phase 11 — Final Submission Validation
**Intent:** Ensure everything passes the automated validator and submission checklist.

**Tasks:**
1. Run GitHub Actions validator — verify green
2. Search README.md for `[` — verify no placeholders remain
3. Verify `demo/demo-video-link.txt` contains real working URL
4. Verify `src/` has real code
5. Verify `submission.yaml` all required fields non-empty
6. Verify repository is Public
7. Submit entry form URL

**Expected outcome:** Green GitHub Actions badge, all checklist items ticked.

**Status:** [ ] pending

---

## What Should NOT Be Built (MVP Exclusions)

These are explicitly out of scope to keep the hackathon MVP achievable:

1. **Real-time data feeds** — No live port APIs, weather APIs, or GPS telemetry.
   All data is seeded. This is correct for a hackathon demo.
2. **User authentication / login** — No JWT, OAuth, sessions. Not needed.
3. **Database migrations** — SQLite is created/dropped by the seed script. No Alembic.
4. **Email/SMS alerting** — No Twilio, SendGrid, or push notifications.
5. **Multi-tenant / multi-org** — Single-org tool only.
6. **Production deployment** — Local-only is fine; "NOT DEPLOYED" in live-demo.txt is acceptable.
7. **Mobile-responsive design** — Desktop-only dashboard is sufficient.
8. **Custom ML model training** — Use watsonx hosted model via API; no training.
9. **Docker Compose** — Nice to have, but setup-guide.md covers manual steps.
10. **Frontend automated tests** — Unit tests for backend only.

---

## Final Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│                    IBM Bob (MCP Client)                  │
│         Natural language queries → 6 MCP tools          │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP protocol
┌──────────────────────▼──────────────────────────────────┐
│              FLEETIQ Bob MCP Server                      │
│         (src/backend/bob_mcp/server.py)                  │
└──────────────────────┬──────────────────────────────────┘
                       │ SQLAlchemy
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Backend (port 8000)                 │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────┐  │
│  │ 5 Routers    │  │ 5 Services     │  │ watsonx     │  │
│  │ /disruptions │  │ disruption_eng │  │ client.py   │  │
│  │ /shipments   │  │ impact_analyze │  │             │  │
│  │ /fleet       │  │ route_recom    │  │ Granite LLM │  │
│  │ /cold-chain  │  │ fleet_optim    │  │ (ibm cloud) │  │
│  │ /summary     │  │ cold_chain_rnk │  │             │  │
│  └──────────────┘  └────────────────┘  └─────────────┘  │
│               SQLAlchemy ORM                             │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│            SQLite (fleetiq.db)                          │
│   Disruptions | Shipments | Fleet | ColdChainReadings   │
└─────────────────────────────────────────────────────────┘
                       ▲
┌──────────────────────┴──────────────────────────────────┐
│          React Frontend (Vite, port 5173)               │
│   Dashboard | Disruptions+Shipments | Fleet+ColdChain   │
│   + AI Summary Panel on Dashboard (calls /api/summary)  │
└─────────────────────────────────────────────────────────┘
```

---

## Build Order (What to Build First)

1. **submission.yaml + README** → CI green immediately
2. **SQLAlchemy models + seed script** → all other code depends on data shape
3. **FastAPI routers (stubs)** → unblocks frontend early
4. **Business logic services** → the intelligence layer
5. **watsonx client** → the IBM AI integration
6. **Bob MCP server** → the IBM Bob integration
7. **React frontend** → consumes all APIs
8. **Tests + docs + demo** → submission polish
