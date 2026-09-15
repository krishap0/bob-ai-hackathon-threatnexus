# FLEETIQ Bob MCP Server

IBM Bob integration for FLEETIQ — a Model Context Protocol (MCP) server that
lets IBM Bob query live supply-chain data using natural language.

---

## Overview

The FLEETIQ MCP server runs as a **local stdio process** registered with IBM Bob.
Once registered, Bob can answer questions like:

- *"What are the active disruptions?"*
- *"Which shipments need rerouting?"*
- *"Show me the critical cold-chain alerts."*
- *"Which idle trucks are available for redeployment?"*
- *"Generate an operational summary."*
- *"What are the rerouting options for FQ-2026-00001?"*

All answers are drawn from the live FLEETIQ SQLite database — not hardcoded text.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Must be on PATH |
| FLEETIQ backend set up | `cd src/backend && pip install -r requirements.txt` |
| FLEETIQ database seeded | Start the FastAPI server once to trigger auto-seed |
| IBM Bob desktop app | Download from IBM |
| `DATABASE_URL` | Optional — defaults to `fleetiq.db` next to `server.py` |

---

## Installation

```bash
# 1. From the repository root, install backend requirements
cd src/backend
pip install -r requirements.txt

# 2. Seed the database (run the FastAPI server once, then stop it)
uvicorn main:app --reload
# Ctrl-C after seeing "Seed complete."

# 3. Verify the MCP server starts without errors (Ctrl-C to exit)
python bob_mcp/server.py
```

---

## Registration in IBM Bob

### Step 1 — Find your settings file

Open the Bob settings and navigate to the **MCP** tab, or locate the
`settings.json` file directly:

| Platform | Path |
|---|---|
| Windows | `%APPDATA%\IBM\Bob\settings.json` |
| macOS | `~/Library/Application Support/IBM/Bob/settings.json` |
| Linux | `~/.config/IBM/Bob/settings.json` |

### Step 2 — Add the FLEETIQ server block

Add the following entry inside the `"mcpServers"` object. Replace every
`<...>` placeholder with your actual absolute paths and credentials.

```json
{
  "mcpServers": {
    "fleetiq": {
      "command": "python",
      "args": ["<absolute-path-to>/src/backend/bob_mcp/server.py"],
      "cwd": "<absolute-path-to>/src/backend",
      "env": {
        "DATABASE_URL": "sqlite:///<absolute-path-to>/src/backend/fleetiq.db",
        "WATSONX_API_KEY": "<your-ibm-cloud-api-key>",
        "WATSONX_PROJECT_ID": "<your-watsonx-project-id>",
        "WATSONX_URL": "https://us-south.ml.cloud.ibm.com",
        "WATSONX_MODEL_ID": "ibm/granite-3-8b-instruct"
      }
    }
  }
}
```

> **Windows path note:** Use forward slashes or escaped backslashes in JSON:
> `"C:/Users/yourname/repos/fleetiq-repo/src/backend/bob_mcp/server.py"`

### Step 3 — Restart Bob

Save the settings file and restart the IBM Bob desktop app. The FLEETIQ
server should appear as **connected** in the MCP panel.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | No | `sqlite:///fleetiq.db` (next to server.py) | SQLAlchemy database URL |
| `WATSONX_API_KEY` | No* | — | IBM Cloud API key |
| `WATSONX_PROJECT_ID` | No* | — | watsonx.ai project ID |
| `WATSONX_URL` | No | `https://us-south.ml.cloud.ibm.com` | Regional endpoint |
| `WATSONX_MODEL_ID` | No | `ibm/granite-3-8b-instruct` | Granite model ID |

\* Required for `get_ai_summary` to return a genuinely AI-generated response.
Without credentials the tool still returns a template-filled fallback summary.

---

## Available Tools

### `get_active_disruptions`

Lists active and monitoring supply-chain disruptions.

**Parameters (all optional):**

| Parameter | Type | Description |
|---|---|---|
| `severity` | string | Filter: `low`, `medium`, `high`, `critical` |
| `disruption_type` | string | Filter: `port_congestion`, `road_closure`, `severe_weather`, `carrier_outage`, `geopolitical` |
| `limit` | integer | Max rows (default 20) |

**Example Bob queries:**
- *"What are the critical disruptions?"*
- *"Show me all port congestion events."*
- *"List active weather-related disruptions."*

---

### `get_affected_shipments`

Lists at-risk and delayed shipments, ranked by impact score.

**Parameters (all optional):**

| Parameter | Type | Description |
|---|---|---|
| `disruption_id` | string | Filter to a specific disruption (e.g. `dis-001`) |
| `severity` | string | Filter by linked disruption severity |
| `min_impact_score` | number | Only shipments with score ≥ this value |
| `limit` | integer | Max rows (default 20) |

**Example Bob queries:**
- *"Which shipments need rerouting?"*
- *"Show me high-impact at-risk shipments."*
- *"Which shipments are affected by disruption dis-001?"*

---

### `get_idle_fleet`

Lists idle fleet vehicles available for redeployment, ranked by redeployment score.

**Parameters (all optional):**

| Parameter | Type | Description |
|---|---|---|
| `vehicle_type` | string | Filter: `truck`, `van`, `ship`, `rail_car`, `air_freight` |
| `min_capacity_kg` | number | Minimum available capacity in kg |
| `redeployable_only` | boolean | Only flagged-redeployable vehicles (default false) |
| `limit` | integer | Max rows (default 20) |

**Example Bob queries:**
- *"Which trucks are idle and available?"*
- *"Find redeployable vehicles with capacity over 10,000 kg."*
- *"Show me all idle fleet vehicles."*

---

### `get_cold_chain_alerts`

Lists temperature excursions ranked by severity score.

**Parameters (all optional):**

| Parameter | Type | Description |
|---|---|---|
| `severity` | string | Filter: `none`, `minor`, `moderate`, `severe`, `critical` |
| `shipment_id` | string | Filter to a specific shipment |
| `excursion_only` | boolean | Only excursion readings (default true) |
| `limit` | integer | Max rows (default 20) |

**Example Bob queries:**
- *"What are the critical cold-chain alerts?"*
- *"Show me all temperature excursions."*
- *"Are there any pharmaceutical cold-chain violations?"*

---

### `get_ai_summary`

Generates an AI operational summary using IBM watsonx.ai Granite.

**Parameters:** none

**Example Bob queries:**
- *"Generate an operational summary."*
- *"Give me the FLEETIQ briefing."*
- *"What's the current supply chain status?"*

---

### `get_shipment_recommendations`

Returns rerouting, carrier-change, and hold recommendations for a shipment.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tracking_number` | string | ✅ | e.g. `FQ-2026-00001` |

**Example Bob queries:**
- *"What are the options for shipment FQ-2026-00001?"*
- *"How should we reroute FQ-2026-00003?"*
- *"Show me carrier alternatives for tracking number FQ-2026-00005."*

---

## Troubleshooting

| Symptom | Solution |
|---|---|
| Server not appearing in Bob MCP panel | Check that `python` is on PATH in the shell Bob uses; try absolute Python path |
| `no such table: disruptions` | Run the FastAPI server once to seed: `uvicorn main:app` |
| `ModuleNotFoundError: database` | Ensure `cwd` in the config is set to `src/backend` |
| `get_ai_summary` returns fallback | Set `WATSONX_API_KEY` and `WATSONX_PROJECT_ID` in the server `env` block |
| Bob shows tool call errors | Check Bob's MCP log panel; server stderr is shown there |

---

## Running Tests

```bash
cd src/backend
pytest tests/test_phase5.py -v
```

All Phase 5 tests mock the MCP SDK and SQLAlchemy — no live Bob connection or
database is required for the test suite.
