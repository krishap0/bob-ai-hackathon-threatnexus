"""
FLEETIQ Bob MCP Server — Phase 5
==================================
IBM Bob integration via Model Context Protocol (MCP).

This server is registered with IBM Bob as a STDIO transport MCP server.
When Bob calls a tool, this process receives the JSON-RPC request on stdin
and writes the response to stdout.

Registration (Bob settings.json / mcp.json):
---------------------------------------------
{
  "mcpServers": {
    "fleetiq": {
      "command": "python",
      "args": ["<absolute-path-to>/src/backend/bob_mcp/server.py"],
      "cwd": "<absolute-path-to>/src/backend",
      "env": {
        "DATABASE_URL": "sqlite:////<absolute-path-to>/src/backend/fleetiq.db",
        "WATSONX_API_KEY": "<your-key>",
        "WATSONX_PROJECT_ID": "<your-project-id>",
        "WATSONX_URL": "https://us-south.ml.cloud.ibm.com",
        "WATSONX_MODEL_ID": "ibm/granite-3-8b-instruct"
      }
    }
  }
}

Environment variables (all optional — app works with safe fallbacks):
  DATABASE_URL      — SQLite URL (default: fleetiq.db next to server.py)
  WATSONX_API_KEY   — IBM Cloud API key (required for AI summary)
  WATSONX_PROJECT_ID— watsonx.ai project ID (required for AI summary)
  WATSONX_URL       — watsonx regional endpoint (default: us-south)
  WATSONX_MODEL_ID  — Granite model (default: ibm/granite-3-8b-instruct)

Tools exposed (6)
-----------------
  get_active_disruptions        list active/monitoring disruptions
  get_affected_shipments        list at-risk/delayed shipments
  get_idle_fleet                list idle redeployable fleet vehicles
  get_cold_chain_alerts         list temperature excursions ranked by severity
  get_ai_summary                generate watsonx.ai operational briefing
  get_shipment_recommendations  rerouting options for a tracking number
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# ---------------------------------------------------------------------------
# Path bootstrap — ensure the backend package is importable regardless of cwd
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# ---------------------------------------------------------------------------
# MCP SDK imports
# ---------------------------------------------------------------------------
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ---------------------------------------------------------------------------
# Local tool implementations (no MCP imports — independently testable)
# ---------------------------------------------------------------------------
from bob_mcp.tools import (
    get_active_disruptions,
    get_affected_shipments,
    get_idle_fleet,
    get_cold_chain_alerts,
    get_ai_summary,
    get_shipment_recommendations,
)

# ---------------------------------------------------------------------------
# Logging — MUST use stderr only; stdout is the MCP protocol channel
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] fleetiq-mcp: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server definition
# ---------------------------------------------------------------------------
server = Server("fleetiq-mcp")

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Advertise the 6 FLEETIQ tools to Bob."""
    return [
        types.Tool(
            name="get_active_disruptions",
            description=(
                "List active and monitoring supply-chain disruptions. "
                "Optionally filter by severity (low|medium|high|critical) "
                "or type (port_congestion|road_closure|severe_weather|"
                "carrier_outage|geopolitical). Returns id, title, type, "
                "severity, status, affected_region, and affected_routes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "description": "Filter by severity: low, medium, high, or critical",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "disruption_type": {
                        "type": "string",
                        "description": (
                            "Filter by type: port_congestion, road_closure, "
                            "severe_weather, carrier_outage, or geopolitical"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of disruptions to return (default 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_affected_shipments",
            description=(
                "List at-risk and delayed shipments. Optionally filter by "
                "disruption_id, disruption severity, or minimum impact_score. "
                "Results are ranked by impact_score descending."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "disruption_id": {
                        "type": "string",
                        "description": "Filter to shipments affected by a specific disruption ID",
                    },
                    "severity": {
                        "type": "string",
                        "description": "Filter by linked disruption severity",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "min_impact_score": {
                        "type": "number",
                        "description": "Minimum impact_score threshold (0–100)",
                        "default": 0.0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of shipments to return (default 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_idle_fleet",
            description=(
                "List idle fleet vehicles available for redeployment, ranked by "
                "redeployment_score. Optionally filter by vehicle_type, minimum "
                "available capacity, or redeployable flag."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "vehicle_type": {
                        "type": "string",
                        "description": (
                            "Filter by type: truck, van, ship, rail_car, or air_freight"
                        ),
                    },
                    "min_capacity_kg": {
                        "type": "number",
                        "description": "Minimum available capacity in kg",
                        "default": 0.0,
                    },
                    "redeployable_only": {
                        "type": "boolean",
                        "description": "When true, only return vehicles flagged redeployable=True",
                        "default": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of vehicles to return (default 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_cold_chain_alerts",
            description=(
                "List cold-chain temperature excursions ranked by severity_score. "
                "Optionally filter by severity band or a specific shipment_id. "
                "Returns temperature, required range, excursion duration, and severity."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "description": "Filter by severity: none, minor, moderate, severe, or critical",
                        "enum": ["none", "minor", "moderate", "severe", "critical"],
                    },
                    "shipment_id": {
                        "type": "string",
                        "description": "Filter to a specific shipment ID",
                    },
                    "excursion_only": {
                        "type": "boolean",
                        "description": "When true (default), only return excursion readings",
                        "default": True,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of readings to return (default 20)",
                        "default": 20,
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_ai_summary",
            description=(
                "Generate an AI-powered operational summary using IBM watsonx.ai "
                "Granite. Collects live statistics from the FLEETIQ database and "
                "calls the configured Granite model to produce an executive briefing "
                "with prioritised action items. Falls back to a template summary when "
                "watsonx credentials are not configured."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="get_shipment_recommendations",
            description=(
                "Get rerouting, carrier-change, and hold recommendations for a "
                "specific shipment identified by its tracking number. Returns up to "
                "3 ranked options with estimated delay hours, cost delta, and a "
                "plain-language trade-off summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tracking_number": {
                        "type": "string",
                        "description": "The shipment tracking number (e.g. 'FQ-2026-00001')",
                    },
                },
                "required": ["tracking_number"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Dispatch a tool call to the appropriate implementation."""
    try:
        if name == "get_active_disruptions":
            result = get_active_disruptions(
                severity=arguments.get("severity"),
                disruption_type=arguments.get("disruption_type"),
                limit=int(arguments.get("limit", 20)),
            )

        elif name == "get_affected_shipments":
            result = get_affected_shipments(
                disruption_id=arguments.get("disruption_id"),
                severity=arguments.get("severity"),
                min_impact_score=float(arguments.get("min_impact_score", 0.0)),
                limit=int(arguments.get("limit", 20)),
            )

        elif name == "get_idle_fleet":
            result = get_idle_fleet(
                vehicle_type=arguments.get("vehicle_type"),
                min_capacity_kg=float(arguments.get("min_capacity_kg", 0.0)),
                redeployable_only=bool(arguments.get("redeployable_only", False)),
                limit=int(arguments.get("limit", 20)),
            )

        elif name == "get_cold_chain_alerts":
            result = get_cold_chain_alerts(
                severity=arguments.get("severity"),
                shipment_id=arguments.get("shipment_id"),
                excursion_only=bool(arguments.get("excursion_only", True)),
                limit=int(arguments.get("limit", 20)),
            )

        elif name == "get_ai_summary":
            result = get_ai_summary()

        elif name == "get_shipment_recommendations":
            tracking_number = arguments.get("tracking_number", "")
            if not tracking_number:
                result = {
                    "error": "tracking_number is required.",
                    "recommendations": [],
                }
            else:
                result = get_shipment_recommendations(tracking_number=tracking_number)

        else:
            result = {"error": f"Unknown tool: {name!r}"}

        return [
            types.TextContent(
                type="text",
                text=json.dumps(result, indent=2, default=str),
            )
        ]

    except Exception as exc:  # noqa: BLE001
        logger.error("Tool %r failed: %s", name, exc, exc_info=True)
        return [
            types.TextContent(
                type="text",
                text=json.dumps(
                    {"error": f"Tool {name!r} failed: {exc}", "tool": name},
                    default=str,
                ),
            )
        ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """Run the FLEETIQ MCP server over stdio."""
    logger.info("FLEETIQ MCP server starting (stdio transport).")
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
