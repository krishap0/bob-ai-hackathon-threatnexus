"""
FLEETIQ Phase 2 — Smoke tests.
Starts the FastAPI app in-process using httpx.AsyncClient + ASGITransport.
Verifies all endpoints return HTTP 200 with expected data.
"""

import sys
import os

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient, ASGITransport

# Import the app (triggers table creation + seed via lifespan)
from main import app


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="module")
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.anyio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "FLEETIQ"


@pytest.mark.anyio
async def test_list_disruptions(client):
    r = await client.get("/api/disruptions")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5


@pytest.mark.anyio
async def test_filter_disruptions_by_status(client):
    r = await client.get("/api/disruptions?status=active")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3  # dis-001, dis-002, dis-003 are active


@pytest.mark.anyio
async def test_get_disruption_by_id(client):
    r = await client.get("/api/disruptions/dis-001")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "dis-001"
    assert data["type"] == "port_congestion"
    assert data["severity"] == "critical"


@pytest.mark.anyio
async def test_get_disruption_affected_shipments(client):
    r = await client.get("/api/disruptions/dis-001/affected")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3  # shp-001, shp-002, shp-003


@pytest.mark.anyio
async def test_disruption_not_found(client):
    r = await client.get("/api/disruptions/nonexistent-id")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_shipments(client):
    r = await client.get("/api/shipments")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 15


@pytest.mark.anyio
async def test_filter_shipments_by_status(client):
    r = await client.get("/api/shipments?status=at_risk")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5  # shp-001,002,004,006,007


@pytest.mark.anyio
async def test_filter_shipments_by_cargo_type(client):
    r = await client.get("/api/shipments?cargo_type=cold_chain")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5  # shp-001,004,006,012,015


@pytest.mark.anyio
async def test_get_shipment_by_id(client):
    r = await client.get("/api/shipments/shp-004")
    assert r.status_code == 200
    data = r.json()
    assert data["tracking_number"] == "FQ-2026-00004"
    assert data["cargo_type"] == "cold_chain"


@pytest.mark.anyio
async def test_shipment_not_found(client):
    r = await client.get("/api/shipments/bad-id")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_fleet(client):
    r = await client.get("/api/fleet")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 10


@pytest.mark.anyio
async def test_list_idle_fleet(client):
    r = await client.get("/api/fleet/idle")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 4  # flt-002, flt-003, flt-004, flt-007


@pytest.mark.anyio
async def test_fleet_not_found(client):
    r = await client.get("/api/fleet/bad-id")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_cold_chain(client):
    r = await client.get("/api/cold-chain")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 11


@pytest.mark.anyio
async def test_list_cold_chain_excursions_only(client):
    r = await client.get("/api/cold-chain?excursion_only=true")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 6


@pytest.mark.anyio
async def test_cold_chain_ranked(client):
    r = await client.get("/api/cold-chain/ranked")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 6
    # All items must have excursion=True
    assert all(item["excursion"] for item in data["items"])


@pytest.mark.anyio
async def test_list_carriers(client):
    r = await client.get("/api/carriers")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5


@pytest.mark.anyio
async def test_summary_stats(client):
    r = await client.get("/api/summary/stats")
    assert r.status_code == 200
    data = r.json()
    assert "active_disruptions" in data
    assert data["active_disruptions"] == 3
    assert data["idle_fleet"] == 4
    assert data["cold_chain_excursions"] == 6


@pytest.mark.anyio
async def test_summary(client):
    r = await client.get("/api/summary")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert "stats" in data
    assert data["ai_generated"] is False
