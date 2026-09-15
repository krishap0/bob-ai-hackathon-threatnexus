# FLEETIQ

> AI-Powered Supply Chain Disruption & Fleet Utilisation Assistant

---

## 👥 Team

| Field | Value |
|---|---|
| **Team Name** | ThreatNexus |
| **Track** | AI |
| **Team Lead** | Krisha Prajapati — d25dcs162@charusat.edu.in |
| **Members** | Diya Joshi, Dhruvi Raval, Shrey Raval |

---

## 🎯 Problem Statement

Logistics and supply chain operations teams face cascading disruptions — port
congestion, severe weather, road closures, carrier outages, and geopolitical events
— that delay shipments, strand idle fleet assets, and trigger undetected cold-chain
temperature excursions. There is no unified tool to identify impact, recommend
alternatives, and prioritise response in real time.

---

## 💡 Solution

FLEETIQ is an AI-powered supply chain disruption and fleet utilisation assistant
being built for the IBM BoB AI Innovation Hackathon 2026. When complete, it will
identify affected shipments, recommend rerouting and alternative carriers with
trade-off analysis, detect idle fleet vehicles for redeployment, and severity-rank
cold-chain temperature excursions. An IBM Granite-generated operational briefing
will summarise the current situation and prioritise action items — and every data
domain will be queryable through IBM Bob via natural language.

> **Implementation status:** Under active development. See the Known Limitations
> section for current state.

---

## ✨ Key Features *(planned for full implementation)*

- **Disruption Impact Scoring:** Detect active disruptions (port congestion, severe weather, road closures, carrier outages, geopolitical events) and score every affected shipment by risk.
- **Rerouting & Carrier Recommendations:** Generate three alternatives per at-risk shipment — alternate route, alternate carrier, or hold — each with estimated delay, cost delta, and trade-off explanation.
- **Idle Fleet Detection:** Score idle vehicles for redeployment suitability using Haversine proximity, available capacity, and vehicle-type matching.
- **Cold-Chain Severity Ranking:** Classify temperature excursions as critical / severe / moderate / minor based on deviation magnitude and duration.
- **AI Operational Summary:** IBM watsonx.ai Granite model generates a live operational briefing and prioritised action items from real database statistics, fully queryable through IBM Bob MCP tools.

---

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| **Languages** | Python, JavaScript |
| **Frameworks** | FastAPI, React, SQLAlchemy, Vite, TailwindCSS |
| **IBM Technologies** | watsonx.ai, IBM Bob, IBM Granite |
| **Databases** | SQLite |
| **Other** | Recharts, Zustand, Axios, pytest, GitHub Actions |

---

## 📁 Repository Structure

```
├── src/
│   ├── backend/          # FastAPI API, business logic, IBM Bob MCP server
│   └── frontend/         # React dashboard (3 pages)
├── docs/
│   ├── problem-statement.md
│   ├── solution-overview.md
│   ├── architecture.md
│   └── setup-guide.md
├── demo/
│   ├── screenshots/      # App screenshots (added in Phase 9)
│   └── demo-video-link.txt
├── presentation/         # Slide deck (added in Phase 10)
└── submission.yaml
```

---

## ⚡ How to Run

> Full instructions: [`docs/setup-guide.md`](docs/setup-guide.md)
> *(Setup guide will be completed in Phase 8 once the full application is built.)*

```bash
# 1. Clone the repo
git clone https://github.com/your-org/bob-ai-hackathon-threatnexus.git
cd bob-ai-hackathon-threatnexus

# 2. Install backend dependencies
cd src/backend
pip install -r requirements.txt

# 3. Configure environment
cp src/.env.example src/.env
# Edit src/.env — add your WATSONX_API_KEY and WATSONX_PROJECT_ID

# 4. Start the backend
uvicorn main:app --reload --port 8000

# 5. Install and start the frontend (separate terminal)
cd src/frontend
npm install
npm run dev
```

Application: `http://localhost:5173` | API docs: `http://localhost:8000/docs`

---

## 🖥️ Demo

| Artifact | Status |
|---|---|
| 📹 Demo Video | To be recorded — see [demo/demo-video-link.txt](demo/demo-video-link.txt) |
| 🌐 Live Demo | Not deployed — run locally using the setup guide |
| 🖼️ Screenshots | To be added in Phase 9 — see [demo/screenshots/](demo/screenshots/) |
| 📊 Presentation | To be added in Phase 10 — see [presentation/](presentation/) |

---

## ⚠️ Known Limitations

- **Implementation in progress** — full application is being developed in phases; only the API health-check stub exists at this stage
- Demo will use deterministic seeded data, not live external feeds (port APIs, weather APIs, GPS telemetry)
- IBM watsonx.ai API key and Project ID will be required for the AI summary feature; a graceful fallback is planned if credentials are absent
- Application will run locally only — not deployed to a public URL
- Authentication and multi-tenancy are out of scope for the MVP

---

## 🏅 What We're Most Proud Of

The multi-domain AI fusion — five independent scoring algorithms (disruption detection,
shipment impact, rerouting, fleet optimisation, cold-chain ranking) all feeding a single
IBM Granite-powered operational briefing, with every data domain queryable through
natural language via the IBM Bob MCP server integration.
