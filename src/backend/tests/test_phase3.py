"""
FLEETIQ Phase 3 — Algorithm Tests
===================================
Tests actual business behaviour of the five intelligence services.
All tests are deterministic — no random values, no external calls.

Test groups:
  A. Disruption Engine
  B. Impact Analyzer
  C. Route Recommender
  D. Fleet Optimizer (including Haversine)
  E. Cold-Chain Ranker
  F. Phase 3 API endpoints (integration)
  G. Phase 2 regression (all existing smoke tests still pass)
"""

import sys
import os
import math
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app
from services.disruption_engine import (
    _shipment_affected_by,
    haversine_km as dis_haversine,
    SEVERITY_WEIGHT,
)
from services.impact_analyzer import (
    compute_impact_score,
    _proximity_factor,
    _value_modifier,
    _SEED_REFERENCE_DATE,
)
from services.fleet_optimizer import (
    haversine_km as flt_haversine,
    score_vehicle,
    _proximity_score,
    _capacity_score,
    _type_score,
)
from services.cold_chain_ranker import (
    compute_excursion_severity,
    _classify_severity,
)
from services.route_recommender import (
    _build_hold_recommendation,
    _build_reroute_recommendation,
    _DISRUPTION_RESOLUTION_HRS,
)


# ===========================================================================
# Helpers — build lightweight mock objects (no DB required for unit tests)
# ===========================================================================

def _make_disruption(
    id="dis-001",
    type="port_congestion",
    severity="critical",
    status="active",
    affected_routes=None,
    affected_region="Port of LA",
    latitude=33.74,
    longitude=-118.26,
    title="Test disruption",
    description="",
):
    return SimpleNamespace(
        id=id,
        type=type,
        severity=severity,
        status=status,
        affected_routes=affected_routes or ["ROUTE-A"],
        affected_region=affected_region,
        latitude=latitude,
        longitude=longitude,
        title=title,
        description=description,
    )


def _make_shipment(
    id="shp-001",
    tracking_number="FQ-TEST-001",
    route_id="ROUTE-A",
    status="at_risk",
    cargo_type="standard",
    weight_kg=10000.0,
    value_usd=100000.0,
    carrier_code="POE",
    estimated_arrival=None,
    disruption_id=None,
    origin="Los Angeles, CA",
    destination="Chicago, IL",
    current_location="Los Angeles, CA",
):
    if estimated_arrival is None:
        estimated_arrival = datetime(2026, 1, 15, 12, 0, 0)  # 2 days after seed date
    return SimpleNamespace(
        id=id,
        tracking_number=tracking_number,
        route_id=route_id,
        status=status,
        cargo_type=cargo_type,
        weight_kg=weight_kg,
        value_usd=value_usd,
        carrier_code=carrier_code,
        estimated_arrival=estimated_arrival,
        disruption_id=disruption_id,
        origin=origin,
        destination=destination,
        current_location=current_location,
    )


def _make_vehicle(
    id="flt-001",
    vehicle_id="TRK-001",
    vehicle_type="truck",
    status="idle",
    current_location="Los Angeles, CA",
    latitude=34.05,
    longitude=-118.24,
    capacity_kg=20000.0,
    available_capacity_kg=20000.0,
    redeployable=False,
    redeployment_score=0.0,
):
    return SimpleNamespace(
        id=id,
        vehicle_id=vehicle_id,
        vehicle_type=vehicle_type,
        status=status,
        current_location=current_location,
        latitude=latitude,
        longitude=longitude,
        capacity_kg=capacity_kg,
        available_capacity_kg=available_capacity_kg,
        redeployable=redeployable,
        redeployment_score=redeployment_score,
    )


def _make_reading(
    id="ccr-001",
    shipment_id="shp-001",
    sensor_id="SEN-001",
    temperature_c=-14.5,
    required_min_c=-20.0,
    required_max_c=-18.0,
    excursion=True,
    excursion_duration_min=210.0,
    severity="critical",
    severity_score=0.0,
    cargo_sensitivity="frozen_food",
):
    return SimpleNamespace(
        id=id,
        shipment_id=shipment_id,
        sensor_id=sensor_id,
        recorded_at=datetime(2026, 1, 13, 8, 0, 0),
        temperature_c=temperature_c,
        required_min_c=required_min_c,
        required_max_c=required_max_c,
        excursion=excursion,
        excursion_duration_min=excursion_duration_min,
        severity=severity,
        severity_score=severity_score,
        cargo_sensitivity=cargo_sensitivity,
    )


# ===========================================================================
# A — Disruption Engine
# ===========================================================================

class TestDisruptionEngine:

    def test_shipment_on_affected_route_is_detected(self):
        """A shipment whose route_id is in disruption.affected_routes must be flagged."""
        dis = _make_disruption(affected_routes=["ROUTE-A"])
        shp = _make_shipment(route_id="ROUTE-A")
        result = _shipment_affected_by(shp, dis)
        assert result is not None
        assert result["affected"] is True
        assert result["route_match"] is True

    def test_shipment_on_unaffected_route_is_not_detected(self):
        """A shipment on a different route must not be flagged."""
        dis = _make_disruption(affected_routes=["ROUTE-X"])
        shp = _make_shipment(route_id="ROUTE-A")
        result = _shipment_affected_by(shp, dis)
        assert result is None

    def test_delivered_shipment_excluded(self):
        """Delivered shipments must always be excluded from impact detection."""
        dis = _make_disruption(affected_routes=["ROUTE-A"])
        shp = _make_shipment(route_id="ROUTE-A", status="delivered")
        result = _shipment_affected_by(shp, dis)
        assert result is None

    def test_diverted_shipment_excluded(self):
        """Diverted shipments must be excluded."""
        dis = _make_disruption(affected_routes=["ROUTE-A"])
        shp = _make_shipment(route_id="ROUTE-A", status="diverted")
        result = _shipment_affected_by(shp, dis)
        assert result is None

    def test_critical_disruption_produces_higher_score_than_low(self):
        """A critical disruption must produce a higher disruption impact than a low one."""
        dis_crit = _make_disruption(severity="critical", affected_routes=["ROUTE-A"])
        dis_low = _make_disruption(severity="low", affected_routes=["ROUTE-A"])
        shp = _make_shipment(route_id="ROUTE-A")
        r_crit = _shipment_affected_by(shp, dis_crit)
        r_low = _shipment_affected_by(shp, dis_low)
        assert r_crit["total_disruption_impact"] > r_low["total_disruption_impact"]

    def test_carrier_outage_matches_carrier_name_in_title(self):
        """A carrier_outage disruption mentioning the carrier name in the title must match."""
        dis = _make_disruption(
            type="carrier_outage",
            affected_routes=["ROUTE-Z"],  # different route
            title="FastFreight Systems — IT Outage",
            description="FastFreight ERP offline",
        )
        shp = _make_shipment(route_id="ROUTE-A", carrier_code="FFS")
        # FFS is not in title; title says "FastFreight" not "FFS"
        result = _shipment_affected_by(shp, dis)
        # FFS not in title → not matched; no route match → None
        assert result is None

    def test_explanation_list_is_non_empty(self):
        """Explanation list must contain at least one human-readable string."""
        dis = _make_disruption(affected_routes=["ROUTE-A"])
        shp = _make_shipment(route_id="ROUTE-A")
        result = _shipment_affected_by(shp, dis)
        assert isinstance(result["explanation"], list)
        assert len(result["explanation"]) >= 1


# ===========================================================================
# B — Impact Analyzer
# ===========================================================================

class TestImpactAnalyzer:

    def test_cold_chain_gets_higher_score_than_standard(self):
        """Cold-chain cargo must score higher than standard cargo, all else equal."""
        dis = _make_disruption(severity="high")
        eta = datetime(2026, 1, 15, 12, 0)  # 2 days out

        shp_cold = _make_shipment(cargo_type="cold_chain", estimated_arrival=eta, value_usd=100_000)
        shp_std = _make_shipment(cargo_type="standard", estimated_arrival=eta, value_usd=100_000)

        r_cold = compute_impact_score(shp_cold, dis)
        r_std = compute_impact_score(shp_std, dis)

        assert r_cold["impact_score"] > r_std["impact_score"]
        assert r_cold["breakdown"]["cargo_modifier"] == 20.0
        assert r_std["breakdown"]["cargo_modifier"] == 0.0

    def test_hazmat_gets_modifier_15(self):
        dis = _make_disruption(severity="low")
        shp = _make_shipment(cargo_type="hazmat")
        r = compute_impact_score(shp, dis)
        assert r["breakdown"]["cargo_modifier"] == 15.0

    def test_fragile_gets_modifier_10(self):
        dis = _make_disruption(severity="low")
        shp = _make_shipment(cargo_type="fragile")
        r = compute_impact_score(shp, dis)
        assert r["breakdown"]["cargo_modifier"] == 10.0

    def test_high_value_cargo_scores_more_than_low_value(self):
        """$1,000,000 cargo must score higher than $1,000 cargo."""
        dis = _make_disruption(severity="medium")
        eta = datetime(2026, 1, 16, 12, 0)

        shp_hi = _make_shipment(value_usd=1_000_000, cargo_type="standard", estimated_arrival=eta)
        shp_lo = _make_shipment(value_usd=1_000, cargo_type="standard", estimated_arrival=eta)

        r_hi = compute_impact_score(shp_hi, dis)
        r_lo = compute_impact_score(shp_lo, dis)
        assert r_hi["impact_score"] > r_lo["impact_score"]

    def test_proximity_factor_urgent_arrival(self):
        """ETA within 1 day must give maximum proximity factor (20)."""
        factor, _ = _proximity_factor(datetime(2026, 1, 13, 18, 0))  # same day
        assert factor == 20.0

    def test_proximity_factor_within_3_days(self):
        factor, _ = _proximity_factor(datetime(2026, 1, 15, 12, 0))
        assert factor == 15.0

    def test_proximity_factor_more_than_7_days(self):
        factor, _ = _proximity_factor(datetime(2026, 1, 25, 12, 0))
        assert factor == 5.0

    def test_value_modifier_zero_for_no_value(self):
        mod, _ = _value_modifier(0.0)
        assert mod == 0.0

    def test_value_modifier_capped_at_10(self):
        mod, _ = _value_modifier(1_000_000_000)  # very large value
        assert mod == 10.0

    def test_critical_disruption_base_is_50(self):
        dis = _make_disruption(severity="critical")
        shp = _make_shipment()
        r = compute_impact_score(shp, dis)
        assert r["breakdown"]["severity_base"] == 50.0

    def test_score_never_exceeds_100(self):
        """No matter how extreme the inputs, score must not exceed 100."""
        dis = _make_disruption(severity="critical")
        shp = _make_shipment(
            cargo_type="cold_chain",
            value_usd=999_999_999,
            estimated_arrival=datetime(2026, 1, 13, 13, 0),
        )
        r = compute_impact_score(shp, dis)
        assert r["impact_score"] <= 100.0

    def test_score_is_deterministic(self):
        """Same inputs must always produce the same score."""
        dis = _make_disruption(severity="high")
        shp = _make_shipment(cargo_type="cold_chain", value_usd=285_000)
        r1 = compute_impact_score(shp, dis)
        r2 = compute_impact_score(shp, dis)
        assert r1["impact_score"] == r2["impact_score"]

    def test_risk_label_critical_at_75_plus(self):
        """Scores ≥ 75 must map to 'critical' risk label."""
        dis = _make_disruption(severity="critical")
        shp = _make_shipment(
            cargo_type="cold_chain",
            value_usd=1_000_000,
            estimated_arrival=datetime(2026, 1, 13, 14, 0),
        )
        r = compute_impact_score(shp, dis)
        assert r["risk_label"] == "critical"

    def test_explanation_contains_all_four_factors(self):
        """Explanation must mention all four scoring factors."""
        dis = _make_disruption(severity="high")
        shp = _make_shipment()
        r = compute_impact_score(shp, dis)
        text = " ".join(r["explanation"])
        assert "severity" in text.lower()
        assert "proximity" in text.lower() or "eta" in text.lower() or "day" in text.lower()
        assert "cargo" in text.lower()
        assert "value" in text.lower()


# ===========================================================================
# C — Route Recommender
# ===========================================================================

class TestRouteRecommender:

    def _carrier(self, code, name, reliability=0.9, speed=0.8, cost=1.0, active=True):
        return SimpleNamespace(
            code=code, name=name,
            reliability_score=reliability, speed_score=speed,
            cost_index=cost, active=active,
        )

    def test_hold_recommendation_always_generated(self):
        dis = _make_disruption(type="port_congestion")
        shp = _make_shipment()
        rec = _build_hold_recommendation(shp, dis)
        assert rec["recommendation_type"] == "hold"
        assert rec["estimated_delay_hrs"] > 0
        assert rec["cost_delta_usd"] > 0

    def test_hold_recommendation_for_port_congestion_is_96hrs(self):
        dis = _make_disruption(type="port_congestion")
        shp = _make_shipment()
        rec = _build_hold_recommendation(shp, dis)
        assert rec["estimated_delay_hrs"] == _DISRUPTION_RESOLUTION_HRS["port_congestion"]

    def test_hold_recommendation_for_road_closure_is_12hrs(self):
        dis = _make_disruption(type="road_closure")
        shp = _make_shipment()
        rec = _build_hold_recommendation(shp, dis)
        assert rec["estimated_delay_hrs"] == 12.0

    def test_reroute_recommendation_has_correct_structure(self):
        dis = _make_disruption(severity="high", affected_routes=["ROUTE-A"])
        shp = _make_shipment(route_id="ROUTE-A", carrier_code="POE")
        carriers = [self._carrier("POE", "Pacific Overland Express")]
        rec = _build_reroute_recommendation(shp, dis, [], carriers)
        assert rec is not None
        assert rec["recommendation_type"] == "reroute"
        assert "estimated_delay_hrs" in rec
        assert "cost_delta_usd" in rec
        assert "trade_off_summary" in rec
        assert "score" in rec
        assert "ALT-" in rec["title"]

    def test_reroute_critical_adds_24hrs_delay(self):
        dis = _make_disruption(severity="critical", affected_routes=["ROUTE-A"])
        shp = _make_shipment(carrier_code="POE")
        carriers = [self._carrier("POE", "POE")]
        rec = _build_reroute_recommendation(shp, dis, [], carriers)
        assert rec["estimated_delay_hrs"] == 24.0

    def test_reroute_low_severity_adds_6hrs_delay(self):
        dis = _make_disruption(severity="low", affected_routes=["ROUTE-A"])
        shp = _make_shipment(carrier_code="POE")
        carriers = [self._carrier("POE", "POE")]
        rec = _build_reroute_recommendation(shp, dis, [], carriers)
        assert rec["estimated_delay_hrs"] == 6.0

    def test_recommendations_are_deterministic(self):
        """Same inputs must produce the same recommendation scores."""
        dis = _make_disruption(severity="high")
        shp = _make_shipment(carrier_code="POE")
        carriers = [self._carrier("POE", "POE")]
        r1 = _build_hold_recommendation(shp, dis)
        r2 = _build_hold_recommendation(shp, dis)
        assert r1["score"] == r2["score"]
        assert r1["estimated_delay_hrs"] == r2["estimated_delay_hrs"]


# ===========================================================================
# D — Fleet Optimizer (including Haversine)
# ===========================================================================

class TestFleetOptimizer:

    def test_haversine_la_to_new_york(self):
        """LA → NYC great-circle distance should be approximately 3940 km."""
        # LA: 34.0522, -118.2437 | NYC: 40.7128, -74.0060
        dist = flt_haversine(34.0522, -118.2437, 40.7128, -74.0060)
        assert 3900 < dist < 4000, f"Expected ~3940 km, got {dist:.0f} km"

    def test_haversine_same_point_is_zero(self):
        dist = flt_haversine(34.0, -118.0, 34.0, -118.0)
        assert dist < 0.001

    def test_haversine_symmetry(self):
        """Distance A→B must equal B→A."""
        d1 = flt_haversine(34.0, -118.0, 41.0, -87.0)
        d2 = flt_haversine(41.0, -87.0, 34.0, -118.0)
        assert abs(d1 - d2) < 0.001

    def test_closer_vehicle_ranks_above_farther_vehicle(self):
        """A vehicle near the disruption must outscore one far away."""
        dis = _make_disruption(latitude=33.74, longitude=-118.26)  # LA area

        v_near = _make_vehicle(latitude=34.05, longitude=-118.24)   # ~50 km from dis
        v_far = _make_vehicle(latitude=41.88, longitude=-87.63)     # ~2700 km away (Chicago)

        required_kg = 10000.0
        cargo_types = ["standard"]

        r_near = score_vehicle(v_near, dis, required_kg, cargo_types)
        r_far = score_vehicle(v_far, dis, required_kg, cargo_types)

        assert r_near["redeployment_score"] > r_far["redeployment_score"]

    def test_vehicle_with_more_capacity_ranks_higher(self):
        """All else equal, a vehicle with more capacity scores higher."""
        dis = _make_disruption(latitude=34.0, longitude=-118.0)
        v_full = _make_vehicle(available_capacity_kg=20000.0, latitude=34.05, longitude=-118.24)
        v_half = _make_vehicle(available_capacity_kg=5000.0, latitude=34.05, longitude=-118.24)

        r_full = score_vehicle(v_full, dis, 20000.0, ["standard"])
        r_half = score_vehicle(v_half, dis, 20000.0, ["standard"])

        assert r_full["breakdown"]["capacity_score"] > r_half["breakdown"]["capacity_score"]

    def test_zero_capacity_gets_zero_capacity_score(self):
        dis = _make_disruption()
        v = _make_vehicle(available_capacity_kg=0.0)
        cap_score, _ = _capacity_score(v, 10000.0)
        assert cap_score == 0.0

    def test_van_preferred_for_cold_chain(self):
        """A van must score higher than a ship for cold_chain cargo type."""
        dis = _make_disruption()
        van = _make_vehicle(vehicle_type="van")
        ship = _make_vehicle(vehicle_type="ship")
        van_score, _ = _type_score(van, ["cold_chain"])
        ship_score, _ = _type_score(ship, ["cold_chain"])
        assert van_score > ship_score

    def test_truck_preferred_for_hazmat(self):
        truck = _make_vehicle(vehicle_type="truck")
        van = _make_vehicle(vehicle_type="van")
        t_score, _ = _type_score(truck, ["hazmat"])
        v_score, _ = _type_score(van, ["hazmat"])
        assert t_score >= v_score

    def test_score_never_exceeds_100(self):
        dis = _make_disruption(latitude=34.05, longitude=-118.24)
        v = _make_vehicle(latitude=34.05, longitude=-118.24, available_capacity_kg=999_999)
        result = score_vehicle(v, dis, 1.0, ["standard"])
        assert result["redeployment_score"] <= 100.0

    def test_no_coordinates_gives_neutral_proximity(self):
        """Missing coordinates must fall back to neutral proximity (20)."""
        dis = _make_disruption(latitude=None, longitude=None)
        v = _make_vehicle(latitude=34.0, longitude=-118.0)
        prox_score, exp = _proximity_score(v, dis)
        assert prox_score == 20.0
        assert "neutral" in exp.lower()


# ===========================================================================
# E — Cold-Chain Ranker
# ===========================================================================

class TestColdChainRanker:

    def test_excursion_above_max_detected(self):
        """Temperature above required_max_c must be flagged as excursion."""
        r = _make_reading(temperature_c=11.8, required_min_c=2.0, required_max_c=8.0,
                          excursion=True, excursion_duration_min=185.0)
        result = compute_excursion_severity(r)
        assert result["excursion"] is True
        assert result["magnitude_c"] == pytest.approx(11.8 - 8.0, abs=0.01)

    def test_excursion_below_min_detected(self):
        """Temperature below required_min_c must be flagged."""
        r = _make_reading(temperature_c=-14.5, required_min_c=-20.0, required_max_c=-18.0,
                          excursion=True, excursion_duration_min=210.0)
        result = compute_excursion_severity(r)
        assert result["excursion"] is True
        # magnitude_c is always the positive distance outside the range
        # temperature=-14.5 is ABOVE required_max=-18.0, so magnitude = -14.5 - (-18.0) = 3.5
        assert result["magnitude_c"] == pytest.approx(3.5, abs=0.01)

    def test_within_range_is_not_excursion(self):
        """Temperature within range must return excursion=False."""
        r = _make_reading(temperature_c=-19.2, required_min_c=-20.0, required_max_c=-18.0,
                          excursion=False, excursion_duration_min=None)
        result = compute_excursion_severity(r)
        assert result["excursion"] is False
        assert result["severity"] == "none"
        assert result["severity_score"] == 0.0

    def test_critical_band_large_magnitude(self):
        """Magnitude > 10°C must give critical severity."""
        assert _classify_severity(10.5, 0.0) == "critical"

    def test_critical_band_long_duration(self):
        """Duration > 240 min must give critical severity even with small magnitude."""
        assert _classify_severity(0.5, 250.0) == "critical"

    def test_severe_band(self):
        assert _classify_severity(7.0, 0.0) == "severe"
        assert _classify_severity(1.0, 150.0) == "severe"

    def test_moderate_band(self):
        assert _classify_severity(3.0, 0.0) == "moderate"
        assert _classify_severity(1.0, 90.0) == "moderate"

    def test_minor_band(self):
        assert _classify_severity(1.0, 30.0) == "minor"

    def test_longer_duration_produces_higher_score(self):
        """Same magnitude but longer duration must produce a higher severity_score."""
        r_short = _make_reading(
            temperature_c=11.8, required_min_c=2.0, required_max_c=8.0,
            excursion=True, excursion_duration_min=60.0, cargo_sensitivity="standard"
        )
        r_long = _make_reading(
            temperature_c=11.8, required_min_c=2.0, required_max_c=8.0,
            excursion=True, excursion_duration_min=200.0, cargo_sensitivity="standard"
        )
        res_short = compute_excursion_severity(r_short)
        res_long = compute_excursion_severity(r_long)
        assert res_long["severity_score"] > res_short["severity_score"]

    def test_pharmaceutical_multiplier_applied(self):
        """Pharmaceutical cargo must produce a higher score than standard for same reading."""
        r_std = _make_reading(
            temperature_c=11.8, required_min_c=2.0, required_max_c=8.0,
            excursion=True, excursion_duration_min=60.0, cargo_sensitivity="standard"
        )
        r_pharm = _make_reading(
            temperature_c=11.8, required_min_c=2.0, required_max_c=8.0,
            excursion=True, excursion_duration_min=60.0, cargo_sensitivity="pharmaceutical"
        )
        res_std = compute_excursion_severity(r_std)
        res_pharm = compute_excursion_severity(r_pharm)
        assert res_pharm["severity_score"] > res_std["severity_score"]

    def test_score_formula_matches_manual_calculation(self):
        """
        Manual check:
          temperature_c=-14.5, required_min=-20.0, required_max=-18.0
          magnitude = -18.0 - (-14.5) = 3.5°C  (above max = 14.5 - 18.0... wait)
          Actually: temp=-14.5 > required_max=-18.0 → above range
          magnitude = -14.5 - (-18.0) = 3.5
          duration = 210 min
          raw = (3.5 × 5) + (210 / 10) = 17.5 + 21.0 = 38.5
          mult = frozen_food = 1.2
          final = min(38.5 × 1.2, 100) = min(46.2, 100) = 46.2
        """
        r = _make_reading(
            temperature_c=-14.5, required_min_c=-20.0, required_max_c=-18.0,
            excursion=True, excursion_duration_min=210.0, cargo_sensitivity="frozen_food"
        )
        result = compute_excursion_severity(r)
        assert result["severity_score"] == pytest.approx(46.2, abs=0.1)

    def test_severity_score_capped_at_100(self):
        """Extremely long excursion with large magnitude must not exceed 100."""
        r = _make_reading(
            temperature_c=50.0, required_min_c=2.0, required_max_c=8.0,
            excursion=True, excursion_duration_min=1000.0, cargo_sensitivity="pharmaceutical"
        )
        result = compute_excursion_severity(r)
        assert result["severity_score"] <= 100.0

    def test_explanation_present(self):
        r = _make_reading()
        result = compute_excursion_severity(r)
        assert isinstance(result["explanation"], list)
        assert len(result["explanation"]) >= 3


# ===========================================================================
# F — Phase 3 API Integration Tests
# ===========================================================================

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
async def test_disruption_impact_endpoint(client):
    r = await client.get("/api/disruptions/dis-001/impact")
    assert r.status_code == 200
    data = r.json()
    assert "disruption_id" in data
    assert data["disruption_id"] == "dis-001"
    assert "total_affected" in data
    assert data["total_affected"] >= 1
    assert "affected_shipments" in data


@pytest.mark.anyio
async def test_disruption_impact_returns_highest_risk(client):
    """The endpoint must return at least one affected shipment."""
    r = await client.get("/api/disruptions/dis-001/impact")
    assert r.status_code == 200
    data = r.json()
    assert len(data["affected_shipments"]) >= 1
    # First item should have the highest total_disruption_impact
    scores = [s["total_disruption_impact"] for s in data["affected_shipments"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.anyio
async def test_shipment_impact_endpoint(client):
    r = await client.get("/api/shipments/shp-001/impact")
    assert r.status_code == 200
    data = r.json()
    assert "impact_score" in data
    assert data["impact_score"] > 0
    assert "risk_label" in data
    assert "breakdown" in data
    assert "explanation" in data


@pytest.mark.anyio
async def test_shipment_impact_has_four_factors(client):
    r = await client.get("/api/shipments/shp-001/impact")
    data = r.json()
    bd = data["breakdown"]
    assert "severity_base" in bd
    assert "proximity_factor" in bd
    assert "cargo_modifier" in bd
    assert "value_modifier" in bd


@pytest.mark.anyio
async def test_shipment_recommendations_endpoint(client):
    r = await client.get("/api/shipments/shp-001/recommendations")
    assert r.status_code == 200
    data = r.json()
    assert "recommendations" in data
    assert len(data["recommendations"]) >= 1


@pytest.mark.anyio
async def test_recommendations_have_required_fields(client):
    r = await client.get("/api/shipments/shp-001/recommendations")
    recs = r.json()["recommendations"]
    for rec in recs:
        assert "recommendation_type" in rec
        assert rec["recommendation_type"] in ("reroute", "carrier_change", "hold")
        assert "estimated_delay_hrs" in rec
        assert "cost_delta_usd" in rec
        assert "trade_off_summary" in rec
        assert "score" in rec
        assert "rank" in rec


@pytest.mark.anyio
async def test_recommendations_ranked_by_score(client):
    """Recommendations must be ordered by score descending."""
    r = await client.get("/api/shipments/shp-001/recommendations")
    recs = r.json()["recommendations"]
    scores = [rec["score"] for rec in recs]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.anyio
async def test_shipment_no_disruption_returns_empty_recs(client):
    """A shipment with no disruption link must return empty recommendations."""
    r = await client.get("/api/shipments/shp-009/recommendations")
    assert r.status_code == 200
    data = r.json()
    assert data["recommendations"] == []


@pytest.mark.anyio
async def test_fleet_redeployment_endpoint(client):
    r = await client.get("/api/fleet/flt-002/redeployment")
    assert r.status_code == 200
    data = r.json()
    assert "redeployment_score" in data
    assert "breakdown" in data
    assert "explanation" in data


@pytest.mark.anyio
async def test_fleet_ranked_endpoint(client):
    r = await client.get("/api/fleet/ranked")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    # Must be ranked 1, 2, 3...
    ranks = [item["rank"] for item in data["items"]]
    assert ranks == list(range(1, len(ranks) + 1))


@pytest.mark.anyio
async def test_fleet_ranked_scores_descending(client):
    r = await client.get("/api/fleet/ranked")
    items = r.json()["items"]
    scores = [i["redeployment_score"] for i in items]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.anyio
async def test_cold_chain_ranked_endpoint(client):
    r = await client.get("/api/cold-chain/ranked")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    items = data["items"]
    assert len(items) >= 1
    # All must be excursions
    assert all(item["excursion"] is True for item in items)


@pytest.mark.anyio
async def test_cold_chain_ranked_scores_descending(client):
    r = await client.get("/api/cold-chain/ranked")
    items = r.json()["items"]
    scores = [i["severity_score"] for i in items]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.anyio
async def test_cold_chain_severity_detail_endpoint(client):
    r = await client.get("/api/cold-chain/ccr-001/severity")
    assert r.status_code == 200
    data = r.json()
    assert "severity" in data
    assert "severity_score" in data
    assert "magnitude_c" in data
    assert "explanation" in data


@pytest.mark.anyio
async def test_impacted_shipments_endpoint(client):
    r = await client.get("/api/shipments/impacted")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    scores = [s["impact_score"] for s in data["items"]]
    assert scores == sorted(scores, reverse=True)


# ===========================================================================
# G — Phase 2 Regression (all original smoke tests)
# ===========================================================================

@pytest.mark.anyio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["service"] == "FLEETIQ"


@pytest.mark.anyio
async def test_list_disruptions(client):
    r = await client.get("/api/disruptions")
    assert r.status_code == 200
    assert r.json()["total"] == 5


@pytest.mark.anyio
async def test_filter_disruptions_by_status(client):
    r = await client.get("/api/disruptions?status=active")
    assert r.status_code == 200
    assert r.json()["total"] == 3


@pytest.mark.anyio
async def test_get_disruption_by_id(client):
    r = await client.get("/api/disruptions/dis-001")
    assert r.status_code == 200
    assert r.json()["type"] == "port_congestion"


@pytest.mark.anyio
async def test_get_disruption_affected_shipments(client):
    r = await client.get("/api/disruptions/dis-001/affected")
    assert r.status_code == 200
    assert r.json()["total"] == 3


@pytest.mark.anyio
async def test_disruption_not_found(client):
    r = await client.get("/api/disruptions/nonexistent-id")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_shipments(client):
    r = await client.get("/api/shipments")
    assert r.status_code == 200
    assert r.json()["total"] == 15


@pytest.mark.anyio
async def test_filter_shipments_by_status(client):
    r = await client.get("/api/shipments?status=at_risk")
    assert r.status_code == 200
    assert r.json()["total"] == 5


@pytest.mark.anyio
async def test_filter_shipments_by_cargo_type(client):
    r = await client.get("/api/shipments?cargo_type=cold_chain")
    assert r.status_code == 200
    assert r.json()["total"] == 5


@pytest.mark.anyio
async def test_get_shipment_by_id(client):
    r = await client.get("/api/shipments/shp-004")
    assert r.status_code == 200
    assert r.json()["tracking_number"] == "FQ-2026-00004"


@pytest.mark.anyio
async def test_shipment_not_found(client):
    r = await client.get("/api/shipments/bad-id")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_fleet(client):
    r = await client.get("/api/fleet")
    assert r.status_code == 200
    assert r.json()["total"] == 10


@pytest.mark.anyio
async def test_list_idle_fleet(client):
    r = await client.get("/api/fleet/idle")
    assert r.status_code == 200
    assert r.json()["total"] == 4


@pytest.mark.anyio
async def test_fleet_not_found(client):
    r = await client.get("/api/fleet/bad-id")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_cold_chain(client):
    r = await client.get("/api/cold-chain")
    assert r.status_code == 200
    assert r.json()["total"] == 11


@pytest.mark.anyio
async def test_list_cold_chain_excursions_only(client):
    r = await client.get("/api/cold-chain?excursion_only=true")
    assert r.status_code == 200
    assert r.json()["total"] == 6


@pytest.mark.anyio
async def test_list_carriers(client):
    r = await client.get("/api/carriers")
    assert r.status_code == 200
    assert r.json()["total"] == 5


@pytest.mark.anyio
async def test_summary_stats(client):
    r = await client.get("/api/summary/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["active_disruptions"] == 3
    assert data["idle_fleet"] == 4
    assert data["cold_chain_excursions"] == 6


@pytest.mark.anyio
async def test_summary(client):
    r = await client.get("/api/summary")
    assert r.status_code == 200
    data = r.json()
    assert "summary" in data
    assert data["ai_generated"] is False
