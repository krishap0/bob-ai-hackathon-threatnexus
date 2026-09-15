"""
FLEETIQ Phase 5 — Bob MCP Integration Tests
============================================
Tests are split into two layers:

  A. Tool unit tests (bob_mcp/tools.py)
       All DB calls are made via a live in-process ASGI client that seeds the
       database on startup. No mocking of SQLAlchemy — real data, real queries.
       The MCP SDK is NOT imported in these tests.

  B. Server unit tests (bob_mcp/server.py)
       The call_tool and list_tools handlers are tested by calling the async
       handler functions directly after mocking the tool layer to avoid DB
       dependency. The MCP types are used for assertion but the stdio transport
       is never started.

  C. Regression — Phase 2–4 smoke pass
       A subset of existing tests re-run to confirm nothing broke.

Groups
------
  A1  get_active_disruptions — no filters
  A2  get_active_disruptions — filter by severity
  A3  get_active_disruptions — filter by type
  A4  get_active_disruptions — limit parameter
  A5  get_affected_shipments — no filters
  A6  get_affected_shipments — filter by disruption_id
  A7  get_affected_shipments — filter by min_impact_score
  A8  get_idle_fleet — no filters
  A9  get_idle_fleet — filter by vehicle_type
  A10 get_idle_fleet — redeployable_only
  A11 get_cold_chain_alerts — no filters (excursion_only default)
  A12 get_cold_chain_alerts — filter by severity
  A13 get_cold_chain_alerts — all readings (excursion_only=False)
  A14 get_ai_summary — fallback without credentials
  A15 get_ai_summary — mocked watsonx success
  A16 get_shipment_recommendations — valid tracking number
  A17 get_shipment_recommendations — unknown tracking number
  A18 get_shipment_recommendations — no disruption → empty recs

  B1  list_tools returns 6 tools
  B2  list_tools tool names are correct
  B3  call_tool get_active_disruptions
  B4  call_tool get_affected_shipments
  B5  call_tool get_idle_fleet
  B6  call_tool get_cold_chain_alerts
  B7  call_tool get_ai_summary
  B8  call_tool get_shipment_recommendations — valid
  B9  call_tool get_shipment_recommendations — missing tracking_number
  B10 call_tool unknown tool name returns error JSON

  C1  /health regression
  C2  /api/summary regression
  C3  /api/disruptions regression
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import the FastAPI app (triggers DB seed via lifespan when used as ASGI)
from main import app

# Import tools directly (no MCP SDK dependency)
from bob_mcp.tools import (
    get_active_disruptions,
    get_affected_shipments,
    get_idle_fleet,
    get_cold_chain_alerts,
    get_ai_summary,
    get_shipment_recommendations,
)


# ===========================================================================
# Shared DB fixture — seeds once per module using the FastAPI lifespan
# ===========================================================================

@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def http_client():
    """HTTP client that triggers lifespan (seeds DB)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture(scope="module")
async def db_session(http_client):
    """
    Yield a live SQLAlchemy session using the same DB that the lifespan seeded.
    The http_client fixture is included to guarantee the lifespan has run.
    """
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===========================================================================
# A — Tool unit tests (real DB, no MCP imports)
# ===========================================================================

class TestGetActiveDisruptions:

    def test_A1_returns_all_active(self, db_session):
        """With no filters, returns all active/monitoring disruptions."""
        result = get_active_disruptions(db=db_session)
        assert "disruptions" in result
        assert result["total"] >= 1
        # All seed disruptions that are active/monitoring
        assert result["total"] == len(result["disruptions"])
        for d in result["disruptions"]:
            assert d["status"] in ("active", "monitoring")

    def test_A2_filter_by_severity(self, db_session):
        """Filter severity=critical returns only critical disruptions."""
        result = get_active_disruptions(severity="critical", db=db_session)
        for d in result["disruptions"]:
            assert d["severity"] == "critical"

    def test_A3_filter_by_type(self, db_session):
        """Filter by disruption_type returns only that type."""
        result = get_active_disruptions(disruption_type="port_congestion", db=db_session)
        for d in result["disruptions"]:
            assert d["type"] == "port_congestion"

    def test_A4_limit_parameter(self, db_session):
        """Limit=1 returns at most 1 disruption."""
        result = get_active_disruptions(limit=1, db=db_session)
        assert len(result["disruptions"]) <= 1

    def test_A_response_structure(self, db_session):
        """Each disruption dict has all required keys."""
        result = get_active_disruptions(db=db_session)
        for d in result["disruptions"]:
            for key in ("id", "title", "type", "severity", "status",
                        "affected_region", "affected_routes"):
                assert key in d, f"Missing key {key!r} in disruption"

    def test_A_message_field_present(self, db_session):
        result = get_active_disruptions(db=db_session)
        assert "message" in result
        assert isinstance(result["message"], str)

    def test_A_nonexistent_severity_returns_empty(self, db_session):
        """An invalid / unused severity filter returns zero results (no crash)."""
        result = get_active_disruptions(severity="nonexistent_xyz", db=db_session)
        assert result["total"] == 0
        assert result["disruptions"] == []


class TestGetAffectedShipments:

    def test_A5_returns_at_risk_shipments(self, db_session):
        """With no filters, all at_risk/delayed shipments are returned."""
        result = get_affected_shipments(db=db_session)
        assert "shipments" in result
        assert result["total"] >= 1
        for s in result["shipments"]:
            assert s["status"] in ("at_risk", "delayed")

    def test_A6_filter_by_disruption_id(self, db_session):
        """Filter by disruption_id=dis-001 only returns linked shipments."""
        result = get_affected_shipments(disruption_id="dis-001", db=db_session)
        for s in result["shipments"]:
            assert s["disruption_id"] == "dis-001"

    def test_A7_filter_by_min_impact_score(self, db_session):
        """min_impact_score filter excludes lower-scored shipments."""
        result_all = get_affected_shipments(db=db_session)
        result_high = get_affected_shipments(min_impact_score=50.0, db=db_session)
        for s in result_high["shipments"]:
            assert s["impact_score"] >= 50.0
        # high filter must return <= all
        assert result_high["total"] <= result_all["total"]

    def test_A_shipment_sorted_by_impact_desc(self, db_session):
        """Shipments must be returned in descending impact_score order."""
        result = get_affected_shipments(db=db_session)
        scores = [s["impact_score"] for s in result["shipments"]]
        assert scores == sorted(scores, reverse=True)

    def test_A_response_structure(self, db_session):
        result = get_affected_shipments(db=db_session)
        for s in result["shipments"]:
            for key in ("id", "tracking_number", "origin", "destination",
                        "status", "cargo_type", "impact_score"):
                assert key in s, f"Missing key {key!r} in shipment"


class TestGetIdleFleet:

    def test_A8_returns_idle_vehicles(self, db_session):
        """With no filters, returns all idle vehicles."""
        result = get_idle_fleet(db=db_session)
        assert "vehicles" in result
        assert result["total"] == 4  # seed: 4 idle vehicles
        for v in result["vehicles"]:
            assert v["status"] == "idle"

    def test_A9_filter_by_vehicle_type(self, db_session):
        """Filter by vehicle_type returns only that type."""
        result = get_idle_fleet(vehicle_type="truck", db=db_session)
        for v in result["vehicles"]:
            assert v["vehicle_type"] == "truck"

    def test_A10_redeployable_only(self, db_session):
        """redeployable_only=True returns only redeployable vehicles."""
        result = get_idle_fleet(redeployable_only=True, db=db_session)
        for v in result["vehicles"]:
            assert v["redeployable"] is True

    def test_A_vehicles_sorted_by_score_desc(self, db_session):
        """Vehicles must be in descending redeployment_score order."""
        result = get_idle_fleet(db=db_session)
        scores = [v["redeployment_score"] for v in result["vehicles"]]
        assert scores == sorted(scores, reverse=True)

    def test_A_response_structure(self, db_session):
        result = get_idle_fleet(db=db_session)
        for v in result["vehicles"]:
            for key in ("id", "vehicle_id", "vehicle_type", "status",
                        "current_location", "capacity_kg",
                        "available_capacity_kg", "redeployable",
                        "redeployment_score"):
                assert key in v, f"Missing key {key!r} in vehicle"

    def test_A_min_capacity_filter(self, db_session):
        """min_capacity_kg filter excludes vehicles below threshold."""
        result_all = get_idle_fleet(db=db_session)
        result_filtered = get_idle_fleet(min_capacity_kg=50000.0, db=db_session)
        for v in result_filtered["vehicles"]:
            assert v["available_capacity_kg"] >= 50000.0
        assert result_filtered["total"] <= result_all["total"]


class TestGetColdChainAlerts:

    def test_A11_excursion_only_default(self, db_session):
        """Default call returns only excursion readings."""
        result = get_cold_chain_alerts(db=db_session)
        assert result["total"] == 6  # seed: 6 excursions
        for r in result["readings"]:
            assert r["excursion"] is True

    def test_A12_filter_by_severity(self, db_session):
        """Filter by severity returns only that severity band."""
        result = get_cold_chain_alerts(severity="critical", db=db_session)
        for r in result["readings"]:
            assert r["severity"] == "critical"

    def test_A13_all_readings(self, db_session):
        """excursion_only=False returns all 11 seeded readings."""
        result = get_cold_chain_alerts(excursion_only=False, db=db_session)
        assert result["total"] == 11

    def test_A_sorted_by_severity_score_desc(self, db_session):
        result = get_cold_chain_alerts(db=db_session)
        scores = [r["severity_score"] for r in result["readings"]]
        assert scores == sorted(scores, reverse=True)

    def test_A_critical_and_severe_counts(self, db_session):
        """critical_count and severe_count fields must be accurate."""
        result = get_cold_chain_alerts(db=db_session)
        expected_critical = sum(1 for r in result["readings"] if r["severity"] == "critical")
        expected_severe = sum(1 for r in result["readings"] if r["severity"] == "severe")
        assert result["critical_count"] == expected_critical
        assert result["severe_count"] == expected_severe

    def test_A_response_structure(self, db_session):
        result = get_cold_chain_alerts(db=db_session)
        for r in result["readings"]:
            for key in ("id", "shipment_id", "sensor_id", "temperature_c",
                        "required_min_c", "required_max_c", "excursion",
                        "severity", "severity_score"):
                assert key in r, f"Missing key {key!r} in reading"


class TestGetAiSummary:

    def test_A14_fallback_without_credentials(self, db_session, monkeypatch):
        """Without watsonx credentials, ai_generated=False and summary is non-empty."""
        for var in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
            os.environ.pop(var, None)

        result = get_ai_summary(db=db_session)
        assert "summary" in result
        assert result["ai_generated"] is False
        assert result["model_id"] is None
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 20

    def test_A14_stats_sub_dict_present(self, db_session):
        """stats dict must be present with all five keys."""
        for var in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
            os.environ.pop(var, None)

        result = get_ai_summary(db=db_session)
        for key in ("active_disruptions", "shipments_at_risk", "idle_fleet",
                    "cold_chain_excursions", "critical_excursions"):
            assert key in result["stats"], f"Missing stats key {key!r}"

    def test_A14_stats_match_seeded_values(self, db_session):
        """Stats values must match the deterministic seed data."""
        for var in ("WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
            os.environ.pop(var, None)

        result = get_ai_summary(db=db_session)
        assert result["stats"]["active_disruptions"] == 3
        assert result["stats"]["idle_fleet"] == 4
        assert result["stats"]["cold_chain_excursions"] == 6

    def test_A15_mocked_watsonx_success(self, db_session, monkeypatch):
        """With mocked credentials and SDK, ai_generated=True."""
        monkeypatch.setenv("WATSONX_API_KEY", "test-key")
        monkeypatch.setenv("WATSONX_PROJECT_ID", "test-project")

        sentinel = "SENTINEL_AI_SUMMARY_PHASE5"
        with (
            patch("services.watsonx_client.Credentials"),
            patch("services.watsonx_client.ModelInference") as mock_mi,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_text.return_value = sentinel
            mock_mi.return_value = mock_instance
            result = get_ai_summary(db=db_session)

        assert result["ai_generated"] is True
        assert result["summary"] == sentinel
        assert result["model_id"] == "ibm/granite-3-8b-instruct"


class TestGetShipmentRecommendations:

    def test_A16_valid_tracking_number(self, db_session):
        """A valid tracking number returns shipment details + recommendations."""
        result = get_shipment_recommendations("FQ-2026-00001", db=db_session)
        assert "error" not in result
        assert result["tracking_number"] == "FQ-2026-00001"
        assert "recommendations" in result
        assert "message" in result

    def test_A16_shipment_fields_present(self, db_session):
        result = get_shipment_recommendations("FQ-2026-00001", db=db_session)
        for key in ("tracking_number", "shipment_id", "origin", "destination",
                    "status", "disruption_id"):
            assert key in result, f"Missing key {key!r}"

    def test_A17_unknown_tracking_number(self, db_session):
        """Unknown tracking number returns error key and empty recommendations."""
        result = get_shipment_recommendations("FQ-DOES-NOT-EXIST", db=db_session)
        assert "error" in result
        assert result["recommendations"] == []

    def test_A18_shipment_without_disruption_empty_recs(self, db_session):
        """Shipment with no disruption link returns empty recommendations."""
        result = get_shipment_recommendations("FQ-2026-00009", db=db_session)
        assert "error" not in result
        assert result["recommendations"] == []

    def test_A_at_risk_shipment_has_recommendations(self, db_session):
        """An at-risk shipment with a disruption link should have >= 1 recommendation."""
        result = get_shipment_recommendations("FQ-2026-00001", db=db_session)
        assert len(result["recommendations"]) >= 1

    def test_A_recommendations_have_required_fields(self, db_session):
        result = get_shipment_recommendations("FQ-2026-00001", db=db_session)
        for rec in result["recommendations"]:
            for key in ("recommendation_type", "estimated_delay_hrs",
                        "cost_delta_usd", "trade_off_summary", "score"):
                assert key in rec, f"Missing key {key!r} in recommendation"


# ===========================================================================
# B — Server handler tests (mock the tool functions, no stdio transport)
# ===========================================================================

class TestMcpServer:
    """
    Import server.py handlers and call them directly.
    The MCP Server object is imported — the stdio transport is never started.
    """

    def _import_handlers(self):
        """Import the server module and return the registered handler callables."""
        # We need to access the decorated functions. In mcp 1.x, the decorators
        # register handlers on the Server instance via request_handlers.
        # We call the handlers directly via the server's dispatch.
        import bob_mcp.server as srv
        return srv

    @pytest.mark.anyio
    async def test_B1_list_tools_returns_six(self):
        """list_tools handler must return exactly 6 Tool objects."""
        import bob_mcp.server as srv
        # The @server.list_tools() decorator registers the async callable.
        # We invoke it directly from the request_handlers dict.
        from mcp.types import ListToolsRequest
        handler = srv.server.request_handlers.get(ListToolsRequest)
        assert handler is not None, "list_tools handler not registered"
        # Create a minimal request object
        req = MagicMock()
        req.params = None
        response = await handler(req)
        tools = response.root.tools
        assert len(tools) == 6

    @pytest.mark.anyio
    async def test_B2_list_tools_names_correct(self):
        """Tool names must match the six expected names exactly."""
        import bob_mcp.server as srv
        from mcp.types import ListToolsRequest
        handler = srv.server.request_handlers.get(ListToolsRequest)
        req = MagicMock()
        req.params = None
        response = await handler(req)
        names = {t.name for t in response.root.tools}
        expected = {
            "get_active_disruptions",
            "get_affected_shipments",
            "get_idle_fleet",
            "get_cold_chain_alerts",
            "get_ai_summary",
            "get_shipment_recommendations",
        }
        assert names == expected

    @pytest.mark.anyio
    async def test_B3_call_tool_active_disruptions(self):
        """call_tool dispatches get_active_disruptions and returns JSON TextContent."""
        import bob_mcp.server as srv
        from mcp.types import CallToolRequest

        mock_result = {"total": 2, "disruptions": [], "message": "Found 2."}
        with patch("bob_mcp.server.get_active_disruptions", return_value=mock_result):
            handler = srv.server.request_handlers.get(CallToolRequest)
            req = MagicMock()
            req.params.name = "get_active_disruptions"
            req.params.arguments = {}
            response = await handler(req)

        content = response.root.content
        assert len(content) == 1
        assert content[0].type == "text"
        parsed = json.loads(content[0].text)
        assert parsed["total"] == 2

    @pytest.mark.anyio
    async def test_B4_call_tool_affected_shipments(self):
        import bob_mcp.server as srv
        from mcp.types import CallToolRequest

        mock_result = {"total": 3, "shipments": [], "message": "3 shipments."}
        with patch("bob_mcp.server.get_affected_shipments", return_value=mock_result):
            handler = srv.server.request_handlers.get(CallToolRequest)
            req = MagicMock()
            req.params.name = "get_affected_shipments"
            req.params.arguments = {"disruption_id": "dis-001"}
            response = await handler(req)

        parsed = json.loads(response.root.content[0].text)
        assert parsed["total"] == 3

    @pytest.mark.anyio
    async def test_B5_call_tool_idle_fleet(self):
        import bob_mcp.server as srv
        from mcp.types import CallToolRequest

        mock_result = {"total": 4, "vehicles": [], "message": "4 vehicles."}
        with patch("bob_mcp.server.get_idle_fleet", return_value=mock_result):
            handler = srv.server.request_handlers.get(CallToolRequest)
            req = MagicMock()
            req.params.name = "get_idle_fleet"
            req.params.arguments = {}
            response = await handler(req)

        parsed = json.loads(response.root.content[0].text)
        assert parsed["total"] == 4

    @pytest.mark.anyio
    async def test_B6_call_tool_cold_chain_alerts(self):
        import bob_mcp.server as srv
        from mcp.types import CallToolRequest

        mock_result = {"total": 6, "critical_count": 2, "severe_count": 1,
                       "readings": [], "message": "6 excursions."}
        with patch("bob_mcp.server.get_cold_chain_alerts", return_value=mock_result):
            handler = srv.server.request_handlers.get(CallToolRequest)
            req = MagicMock()
            req.params.name = "get_cold_chain_alerts"
            req.params.arguments = {"severity": "critical"}
            response = await handler(req)

        parsed = json.loads(response.root.content[0].text)
        assert parsed["critical_count"] == 2

    @pytest.mark.anyio
    async def test_B7_call_tool_ai_summary(self):
        import bob_mcp.server as srv
        from mcp.types import CallToolRequest

        mock_result = {
            "summary": "AI briefing.",
            "ai_generated": True,
            "model_id": "ibm/granite-3-8b-instruct",
            "stats": {"active_disruptions": 3},
        }
        with patch("bob_mcp.server.get_ai_summary", return_value=mock_result):
            handler = srv.server.request_handlers.get(CallToolRequest)
            req = MagicMock()
            req.params.name = "get_ai_summary"
            req.params.arguments = {}
            response = await handler(req)

        parsed = json.loads(response.root.content[0].text)
        assert parsed["ai_generated"] is True
        assert parsed["summary"] == "AI briefing."

    @pytest.mark.anyio
    async def test_B8_call_tool_recommendations_valid(self):
        import bob_mcp.server as srv
        from mcp.types import CallToolRequest

        mock_result = {
            "tracking_number": "FQ-2026-00001",
            "recommendations": [{"recommendation_type": "reroute"}],
            "message": "1 recommendation.",
        }
        with patch("bob_mcp.server.get_shipment_recommendations",
                   return_value=mock_result):
            handler = srv.server.request_handlers.get(CallToolRequest)
            req = MagicMock()
            req.params.name = "get_shipment_recommendations"
            req.params.arguments = {"tracking_number": "FQ-2026-00001"}
            response = await handler(req)

        parsed = json.loads(response.root.content[0].text)
        assert parsed["tracking_number"] == "FQ-2026-00001"
        assert len(parsed["recommendations"]) == 1

    @pytest.mark.anyio
    async def test_B9_call_tool_recommendations_missing_tracking(self):
        """Missing tracking_number returns error JSON without raising."""
        import bob_mcp.server as srv
        from mcp.types import CallToolRequest

        handler = srv.server.request_handlers.get(CallToolRequest)
        req = MagicMock()
        req.params.name = "get_shipment_recommendations"
        req.params.arguments = {}  # no tracking_number
        response = await handler(req)

        parsed = json.loads(response.root.content[0].text)
        assert "error" in parsed
        assert parsed["recommendations"] == []

    @pytest.mark.anyio
    async def test_B10_unknown_tool_returns_error_json(self):
        """An unknown tool name must return error JSON without raising."""
        import bob_mcp.server as srv
        from mcp.types import CallToolRequest

        handler = srv.server.request_handlers.get(CallToolRequest)
        req = MagicMock()
        req.params.name = "nonexistent_tool_xyz"
        req.params.arguments = {}
        response = await handler(req)

        parsed = json.loads(response.root.content[0].text)
        assert "error" in parsed

    @pytest.mark.anyio
    async def test_B_tool_exception_handled_gracefully(self):
        """If a tool function raises, call_tool must still return valid JSON."""
        import bob_mcp.server as srv
        from mcp.types import CallToolRequest

        with patch("bob_mcp.server.get_idle_fleet",
                   side_effect=RuntimeError("DB exploded")):
            handler = srv.server.request_handlers.get(CallToolRequest)
            req = MagicMock()
            req.params.name = "get_idle_fleet"
            req.params.arguments = {}
            response = await handler(req)

        parsed = json.loads(response.root.content[0].text)
        assert "error" in parsed

    def test_B_server_has_name(self):
        """Server instance must have the correct name."""
        import bob_mcp.server as srv
        assert srv.server.name == "fleetiq-mcp"

    def test_B_all_tools_have_descriptions(self):
        """Every tool must have a non-empty description."""
        # We verify this by checking the list_tools result synchronously via
        # inspection of the expected tools list (defined in server.py).
        import bob_mcp.server as srv
        # Run the coroutine to get the tools list
        from mcp.types import ListToolsRequest
        handler = srv.server.request_handlers.get(ListToolsRequest)

        async def _run():
            req = MagicMock()
            req.params = None
            response = await handler(req)
            return response.root.tools

        tools = asyncio.get_event_loop().run_until_complete(_run())
        for tool in tools:
            assert tool.description, f"Tool {tool.name!r} has no description"

    def test_B_required_fields_in_inputSchema(self):
        """Every tool's inputSchema must be a valid dict with type='object'."""
        import bob_mcp.server as srv
        from mcp.types import ListToolsRequest
        handler = srv.server.request_handlers.get(ListToolsRequest)

        async def _run():
            req = MagicMock()
            req.params = None
            response = await handler(req)
            return response.root.tools

        tools = asyncio.get_event_loop().run_until_complete(_run())
        for tool in tools:
            schema = tool.inputSchema
            assert isinstance(schema, dict), f"Tool {tool.name!r} inputSchema not dict"
            assert schema.get("type") == "object", f"Tool {tool.name!r} inputSchema type != object"


# ===========================================================================
# C — Phase 2–4 regression
# ===========================================================================

@pytest.mark.anyio
async def test_C1_health_still_ok(http_client):
    r = await http_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.anyio
async def test_C2_summary_still_works(http_client):
    r = await http_client.get("/api/summary")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "ai_generated" in data
    assert "model_id" in data


@pytest.mark.anyio
async def test_C3_disruptions_still_five(http_client):
    r = await http_client.get("/api/disruptions")
    assert r.status_code == 200
    assert r.json()["total"] == 5


@pytest.mark.anyio
async def test_C4_shipments_still_fifteen(http_client):
    r = await http_client.get("/api/shipments")
    assert r.status_code == 200
    assert r.json()["total"] == 15


@pytest.mark.anyio
async def test_C5_fleet_still_ten(http_client):
    r = await http_client.get("/api/fleet")
    assert r.status_code == 200
    assert r.json()["total"] == 10


@pytest.mark.anyio
async def test_C6_cold_chain_still_eleven(http_client):
    r = await http_client.get("/api/cold-chain")
    assert r.status_code == 200
    assert r.json()["total"] == 11
