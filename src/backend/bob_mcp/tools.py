"""
FLEETIQ Bob MCP Tools — Phase 5
================================
Pure business-logic layer for the 6 Bob MCP tools. No MCP SDK imports here
so these functions can be unit-tested independently of the MCP server.

Each function accepts a SQLAlchemy Session (or None, in which case a new
session is created from the default engine) and returns a plain Python dict
or list that is JSON-serialisable.

Tools
-----
get_active_disruptions        — active/monitoring disruptions with severity
get_affected_shipments        — at-risk shipments (filterable)
get_idle_fleet                — redeployable idle vehicles
get_cold_chain_alerts         — excursions ranked by severity_score
get_ai_summary                — watsonx.ai Granite operational summary
get_shipment_recommendations  — rerouting options for a tracking number
"""

from __future__ import annotations

import os
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Path bootstrap — allow importing backend modules when server.py is run
# directly from the bob_mcp/ directory.
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


# ---------------------------------------------------------------------------
# Lazy DB session helper
# ---------------------------------------------------------------------------

def _get_session():
    """Return a new SQLAlchemy session from the default engine."""
    from database import SessionLocal
    return SessionLocal()


def _with_session(db=None):
    """Context helper — returns (db, owned) where owned=True means caller must close."""
    if db is not None:
        return db, False
    return _get_session(), True


# ---------------------------------------------------------------------------
# Tool 1 — get_active_disruptions
# ---------------------------------------------------------------------------

def get_active_disruptions(
    severity: Optional[str] = None,
    disruption_type: Optional[str] = None,
    limit: int = 20,
    db=None,
) -> dict:
    """
    Return active and monitoring disruptions.

    Parameters
    ----------
    severity        : filter by severity (low | medium | high | critical)
    disruption_type : filter by type (port_congestion | road_closure | …)
    limit           : max rows to return (default 20)
    db              : optional SQLAlchemy session (created if not supplied)
    """
    from models import Disruption

    session, owned = _with_session(db)
    try:
        query = session.query(Disruption).filter(
            Disruption.status.in_(["active", "monitoring"])
        )
        if severity:
            query = query.filter(Disruption.severity == severity)
        if disruption_type:
            query = query.filter(Disruption.type == disruption_type)

        items = query.order_by(Disruption.started_at.desc()).limit(limit).all()

        results = []
        for d in items:
            results.append({
                "id": d.id,
                "title": d.title,
                "type": d.type,
                "severity": d.severity,
                "status": d.status,
                "affected_region": d.affected_region,
                "affected_routes": d.affected_routes,
                "started_at": d.started_at.isoformat() if d.started_at else None,
                "description": d.description,
                "source": d.source,
            })

        return {
            "total": len(results),
            "disruptions": results,
            "message": (
                f"Found {len(results)} active disruption(s)"
                + (f" with severity={severity!r}" if severity else "")
                + (f" of type={disruption_type!r}" if disruption_type else "")
                + "."
            ),
        }
    finally:
        if owned:
            session.close()


# ---------------------------------------------------------------------------
# Tool 2 — get_affected_shipments
# ---------------------------------------------------------------------------

def get_affected_shipments(
    disruption_id: Optional[str] = None,
    severity: Optional[str] = None,
    min_impact_score: float = 0.0,
    limit: int = 20,
    db=None,
) -> dict:
    """
    Return shipments that are at risk or delayed.

    Parameters
    ----------
    disruption_id   : filter to shipments linked to a specific disruption
    severity        : filter by the disruption severity (via JOIN)
    min_impact_score: only return shipments with impact_score >= this value
    limit           : max rows to return (default 20)
    db              : optional SQLAlchemy session
    """
    from models import Shipment, Disruption

    session, owned = _with_session(db)
    try:
        query = session.query(Shipment).filter(
            Shipment.status.in_(["at_risk", "delayed"])
        )
        if disruption_id:
            query = query.filter(Shipment.disruption_id == disruption_id)
        if severity:
            # join to disruption to filter by disruption severity
            query = query.join(Disruption, Shipment.disruption_id == Disruption.id).filter(
                Disruption.severity == severity
            )
        if min_impact_score > 0:
            query = query.filter(Shipment.impact_score >= min_impact_score)

        items = (
            query.order_by(Shipment.impact_score.desc()).limit(limit).all()
        )

        results = []
        for s in items:
            results.append({
                "id": s.id,
                "tracking_number": s.tracking_number,
                "origin": s.origin,
                "destination": s.destination,
                "current_location": s.current_location,
                "carrier_code": s.carrier_code,
                "route_id": s.route_id,
                "status": s.status,
                "cargo_type": s.cargo_type,
                "weight_kg": s.weight_kg,
                "value_usd": s.value_usd,
                "impact_score": round(s.impact_score, 2),
                "disruption_id": s.disruption_id,
                "estimated_arrival": (
                    s.estimated_arrival.isoformat() if s.estimated_arrival else None
                ),
            })

        return {
            "total": len(results),
            "shipments": results,
            "message": (
                f"Found {len(results)} at-risk/delayed shipment(s)"
                + (f" for disruption {disruption_id!r}" if disruption_id else "")
                + "."
            ),
        }
    finally:
        if owned:
            session.close()


# ---------------------------------------------------------------------------
# Tool 3 — get_idle_fleet
# ---------------------------------------------------------------------------

def get_idle_fleet(
    vehicle_type: Optional[str] = None,
    min_capacity_kg: float = 0.0,
    redeployable_only: bool = False,
    limit: int = 20,
    db=None,
) -> dict:
    """
    Return idle fleet vehicles, ranked by redeployment_score.

    Parameters
    ----------
    vehicle_type     : filter by type (truck | van | ship | rail_car | air_freight)
    min_capacity_kg  : only vehicles with available_capacity_kg >= this value
    redeployable_only: only return vehicles flagged as redeployable
    limit            : max rows to return (default 20)
    db               : optional SQLAlchemy session
    """
    from models import Fleet

    session, owned = _with_session(db)
    try:
        query = session.query(Fleet).filter(Fleet.status == "idle")
        if vehicle_type:
            query = query.filter(Fleet.vehicle_type == vehicle_type)
        if min_capacity_kg > 0:
            query = query.filter(Fleet.available_capacity_kg >= min_capacity_kg)
        if redeployable_only:
            query = query.filter(Fleet.redeployable == True)  # noqa: E712

        items = query.order_by(Fleet.redeployment_score.desc()).limit(limit).all()

        results = []
        for v in items:
            results.append({
                "id": v.id,
                "vehicle_id": v.vehicle_id,
                "vehicle_type": v.vehicle_type,
                "status": v.status,
                "current_location": v.current_location,
                "capacity_kg": v.capacity_kg,
                "available_capacity_kg": v.available_capacity_kg,
                "redeployable": v.redeployable,
                "redeployment_score": round(v.redeployment_score or 0.0, 2),
                "idle_since": v.idle_since.isoformat() if v.idle_since else None,
                "assigned_route": v.assigned_route,
            })

        return {
            "total": len(results),
            "vehicles": results,
            "message": (
                f"Found {len(results)} idle vehicle(s)"
                + (f" of type {vehicle_type!r}" if vehicle_type else "")
                + (f" with capacity ≥ {min_capacity_kg} kg" if min_capacity_kg > 0 else "")
                + "."
            ),
        }
    finally:
        if owned:
            session.close()


# ---------------------------------------------------------------------------
# Tool 4 — get_cold_chain_alerts
# ---------------------------------------------------------------------------

def get_cold_chain_alerts(
    severity: Optional[str] = None,
    shipment_id: Optional[str] = None,
    excursion_only: bool = True,
    limit: int = 20,
    db=None,
) -> dict:
    """
    Return cold-chain temperature excursions, ranked by severity_score.

    Parameters
    ----------
    severity     : filter by severity (none | minor | moderate | severe | critical)
    shipment_id  : filter to a specific shipment
    excursion_only: when True (default) only return readings where excursion=True
    limit        : max rows to return (default 20)
    db           : optional SQLAlchemy session
    """
    from models import ColdChainReading

    session, owned = _with_session(db)
    try:
        query = session.query(ColdChainReading)
        if excursion_only:
            query = query.filter(ColdChainReading.excursion == True)  # noqa: E712
        if severity:
            query = query.filter(ColdChainReading.severity == severity)
        if shipment_id:
            query = query.filter(ColdChainReading.shipment_id == shipment_id)

        items = query.order_by(ColdChainReading.severity_score.desc()).limit(limit).all()

        results = []
        for r in items:
            results.append({
                "id": r.id,
                "shipment_id": r.shipment_id,
                "sensor_id": r.sensor_id,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                "temperature_c": r.temperature_c,
                "required_min_c": r.required_min_c,
                "required_max_c": r.required_max_c,
                "excursion": r.excursion,
                "excursion_duration_min": r.excursion_duration_min,
                "severity": r.severity,
                "severity_score": round(r.severity_score or 0.0, 2),
            })

        critical_count = sum(1 for r in results if r["severity"] == "critical")
        severe_count = sum(1 for r in results if r["severity"] == "severe")

        return {
            "total": len(results),
            "critical_count": critical_count,
            "severe_count": severe_count,
            "readings": results,
            "message": (
                f"Found {len(results)} cold-chain excursion(s): "
                f"{critical_count} critical, {severe_count} severe."
            ),
        }
    finally:
        if owned:
            session.close()


# ---------------------------------------------------------------------------
# Tool 5 — get_ai_summary
# ---------------------------------------------------------------------------

def get_ai_summary(db=None) -> dict:
    """
    Generate an AI operational summary using IBM watsonx.ai Granite.

    Collects live DB statistics and passes them to the watsonx_client.
    Falls back gracefully if credentials are missing or the API call fails.
    """
    from models import Disruption, Shipment, Fleet, ColdChainReading
    from services.watsonx_client import generate_summary

    session, owned = _with_session(db)
    try:
        # Gather stats
        active_disruptions = (
            session.query(Disruption).filter(Disruption.status == "active").count()
        )
        shipments_at_risk = (
            session.query(Shipment)
            .filter(Shipment.status.in_(["at_risk", "delayed"]))
            .count()
        )
        idle_fleet = session.query(Fleet).filter(Fleet.status == "idle").count()
        cold_chain_excursions = (
            session.query(ColdChainReading)
            .filter(ColdChainReading.excursion == True)  # noqa: E712
            .count()
        )
        critical_excursions = (
            session.query(ColdChainReading)
            .filter(
                ColdChainReading.excursion == True,  # noqa: E712
                ColdChainReading.severity == "critical",
            )
            .count()
        )

        # Top at-risk shipment
        top_shp = (
            session.query(Shipment)
            .filter(Shipment.status.in_(["at_risk", "delayed"]))
            .order_by(Shipment.impact_score.desc())
            .first()
        )
        top_shipment_str = (
            f"{top_shp.tracking_number} (impact score {top_shp.impact_score:.1f})"
            if top_shp and top_shp.impact_score
            else ""
        )

        # Disruption type breakdown
        type_counts: dict[str, int] = {}
        for row in (
            session.query(Disruption.type)
            .filter(Disruption.status == "active")
            .all()
        ):
            t = row[0]
            type_counts[t] = type_counts.get(t, 0) + 1
        breakdown = ", ".join(f"{v} {k}" for k, v in type_counts.items())

        stats = {
            "active_disruptions": active_disruptions,
            "shipments_at_risk": shipments_at_risk,
            "idle_fleet": idle_fleet,
            "cold_chain_excursions": cold_chain_excursions,
            "critical_excursions": critical_excursions,
            "disruption_breakdown": breakdown,
            "top_shipment": top_shipment_str,
        }

        result = generate_summary(stats)

        return {
            "summary": result["summary"],
            "ai_generated": result["ai_generated"],
            "model_id": result["model_id"],
            "stats": {
                "active_disruptions": active_disruptions,
                "shipments_at_risk": shipments_at_risk,
                "idle_fleet": idle_fleet,
                "cold_chain_excursions": cold_chain_excursions,
                "critical_excursions": critical_excursions,
            },
        }
    finally:
        if owned:
            session.close()


# ---------------------------------------------------------------------------
# Tool 6 — get_shipment_recommendations
# ---------------------------------------------------------------------------

def get_shipment_recommendations(tracking_number: str, db=None) -> dict:
    """
    Return rerouting/carrier-change/hold recommendations for a shipment.

    Parameters
    ----------
    tracking_number : the shipment's tracking number (e.g. "FQ-2026-00001")
    db              : optional SQLAlchemy session
    """
    from models import Shipment
    from services import route_recommender

    session, owned = _with_session(db)
    try:
        shipment = (
            session.query(Shipment)
            .filter(Shipment.tracking_number == tracking_number)
            .first()
        )
        if shipment is None:
            return {
                "error": f"No shipment found with tracking number {tracking_number!r}.",
                "recommendations": [],
            }

        recs = route_recommender.get_recommendations(shipment.id, session)

        return {
            "tracking_number": tracking_number,
            "shipment_id": shipment.id,
            "origin": shipment.origin,
            "destination": shipment.destination,
            "status": shipment.status,
            "disruption_id": shipment.disruption_id,
            "recommendations": recs.get("recommendations", []),
            "message": (
                f"Found {len(recs.get('recommendations', []))} recommendation(s) "
                f"for shipment {tracking_number!r}."
            ),
        }
    finally:
        if owned:
            session.close()
