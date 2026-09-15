"""
FLEETIQ — Idle Fleet Optimizer (Phase 3)
=========================================
Identifies idle fleet vehicles and scores their suitability for redeployment
to support shipments affected by disruptions.

Redeployment score formula (0–100)
------------------------------------
score = (proximity_score × 40) + (capacity_score × 35) + (type_score × 25)

Factor breakdown
----------------
1. proximity_score  (0–40)
   Great-circle distance (Haversine) from the vehicle's current position to the
   disruption's geographic centre. Closer = higher score.
   0 km  → 40 pts  |  500 km → 20 pts  |  ≥2000 km → 0 pts
   Formula: 40 × max(0, 1 − distance_km / 2000)
   Falls back to 20 (neutral) when either party lacks coordinates.

2. capacity_score  (0–35)
   available_capacity_kg relative to the weight of the heaviest stranded shipment.
   ratio = available / required (capped at 1.0)
   score = ratio × 35
   Falls back to 17.5 (50%) when no stranded shipment weight is known.

3. type_score  (0–25)
   Whether the vehicle type is suitable for the cargo type of stranded shipments.
   truck → suitable for standard, hazmat, fragile  → 25
   van   → suitable for cold_chain, fragile        → 25
   truck + cold_chain shipment present             → 20 (truck is less ideal for cold)
   air_freight → fast, suitable for pharmaceutical → 25
   ship / rail_car → bulk cargo                    → 20
   generic / unknown match                         → 15

Vehicles with status != "idle" are excluded.
The top-N redeployable vehicles are flagged Fleet.redeployable = True in the DB.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Haversine (also in disruption_engine; kept here for module independence)
# ---------------------------------------------------------------------------

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two (lat, lon) points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Type compatibility lookup
# cargo_type → suitable vehicle types (in preference order)
# ---------------------------------------------------------------------------
_TYPE_COMPAT: dict[str, list[str]] = {
    "cold_chain":  ["van", "air_freight"],       # refrigerated van or air
    "pharmaceutical": ["van", "air_freight"],
    "hazmat":      ["truck"],                    # specialised truck
    "fragile":     ["van", "truck"],
    "standard":    ["truck", "ship", "rail_car", "van", "air_freight"],
    "frozen_food": ["van"],
}

_MAX_DISTANCE_KM = 2000.0  # Beyond this, proximity score → 0
_TOP_N_REDEPLOYABLE = 3    # Mark this many vehicles as redeployable


def _proximity_score(vehicle, disruption) -> tuple[float, str]:
    """Return (score, explanation) for proximity factor."""
    if (vehicle.latitude is None or vehicle.longitude is None
            or disruption is None
            or disruption.latitude is None or disruption.longitude is None):
        return 20.0, "No coordinates available for one or both parties → neutral proximity score (20)"

    dist_km = haversine_km(
        vehicle.latitude, vehicle.longitude,
        disruption.latitude, disruption.longitude,
    )
    ratio = max(0.0, 1.0 - dist_km / _MAX_DISTANCE_KM)
    score = round(ratio * 40.0, 2)
    return score, f"Distance to disruption: {dist_km:.0f} km → proximity score {score:.1f}/40"


def _capacity_score(vehicle, required_kg: float) -> tuple[float, str]:
    """Return (score, explanation) for capacity factor."""
    if required_kg <= 0:
        return 17.5, "No stranded shipment weight known → neutral capacity score (17.5)"
    if vehicle.available_capacity_kg <= 0:
        return 0.0, f"Vehicle has 0 kg available → capacity score 0"
    ratio = min(vehicle.available_capacity_kg / required_kg, 1.0)
    score = round(ratio * 35.0, 2)
    return score, (
        f"Available {vehicle.available_capacity_kg:,.0f} kg / required {required_kg:,.0f} kg "
        f"= {ratio:.0%} match → capacity score {score:.1f}/35"
    )


def _type_score(vehicle, stranded_cargo_types: list[str]) -> tuple[float, str]:
    """Return (score, explanation) for vehicle type compatibility."""
    if not stranded_cargo_types:
        return 15.0, "No cargo type info → generic type score (15)"

    # Check if vehicle type is in the preferred list for any stranded cargo type
    best_score = 0.0
    matched_cargo = None
    for cargo in stranded_cargo_types:
        preferred = _TYPE_COMPAT.get(cargo, ["truck"])
        if vehicle.vehicle_type in preferred:
            # Bonus for being first preference
            idx = preferred.index(vehicle.vehicle_type)
            s = 25.0 if idx == 0 else 20.0
            if s > best_score:
                best_score = s
                matched_cargo = cargo

    if best_score == 0.0:
        best_score = 15.0  # generic partial match
        return best_score, (
            f"Vehicle type {vehicle.vehicle_type!r} not ideal for "
            f"cargo types {stranded_cargo_types} → partial type score (15)"
        )

    return best_score, (
        f"Vehicle type {vehicle.vehicle_type!r} is suitable for "
        f"{matched_cargo!r} cargo → type score {best_score:.0f}/25"
    )


def score_vehicle(vehicle, disruption, required_kg: float, stranded_cargo_types: list[str]) -> dict[str, Any]:
    """
    Score a single idle vehicle for redeployment suitability.
    Returns a dict with score, breakdown, and explanation.
    """
    prox, prox_exp = _proximity_score(vehicle, disruption)
    cap, cap_exp = _capacity_score(vehicle, required_kg)
    typ, typ_exp = _type_score(vehicle, stranded_cargo_types)

    total = round(min(prox + cap + typ, 100.0), 2)

    return {
        "vehicle_id": vehicle.vehicle_id,
        "vehicle_db_id": vehicle.id,
        "vehicle_type": vehicle.vehicle_type,
        "status": vehicle.status,
        "current_location": vehicle.current_location,
        "available_capacity_kg": vehicle.available_capacity_kg,
        "redeployment_score": total,
        "breakdown": {
            "proximity_score": prox,
            "capacity_score": cap,
            "type_score": typ,
        },
        "explanation": [prox_exp, cap_exp, typ_exp],
    }


def score_idle_fleet(db: Session) -> int:
    """
    Compute redeployment_score for all idle vehicles and persist to DB.
    The scoring is relative to the most active disruption (highest severity active one).
    Returns the number of vehicles updated.
    """
    from models import Fleet, Disruption, Shipment

    idle_vehicles = db.query(Fleet).filter(Fleet.status == "idle").all()
    if not idle_vehicles:
        return 0

    # Find the most critical active disruption to score against
    active_disruption = (
        db.query(Disruption)
        .filter(Disruption.status == "active")
        .order_by(Disruption.severity.desc())  # alphabetical but "critical" sorts high
        .first()
    )

    # Get stranded shipments: at_risk or delayed, linked to any active disruption
    stranded = db.query(Shipment).filter(
        Shipment.status.in_(["at_risk", "delayed"]),
        Shipment.disruption_id.isnot(None),
    ).all()

    required_kg = max((s.weight_kg for s in stranded), default=0.0)
    stranded_cargo_types = list({s.cargo_type for s in stranded})

    # Score each idle vehicle
    scored = []
    for v in idle_vehicles:
        result = score_vehicle(v, active_disruption, required_kg, stranded_cargo_types)
        v.redeployment_score = result["redeployment_score"]
        v.redeployable = False  # will flip top-N below
        scored.append((v, result["redeployment_score"]))

    # Mark top-N as redeployable
    scored.sort(key=lambda x: x[1], reverse=True)
    for v, _ in scored[:_TOP_N_REDEPLOYABLE]:
        v.redeployable = True

    db.commit()
    return len(idle_vehicles)


def get_vehicle_redeployment_detail(vehicle_id: str, db: Session) -> dict[str, Any] | None:
    """
    Return full redeployment scoring detail for a single fleet vehicle.
    """
    from models import Fleet, Disruption, Shipment

    vehicle = db.query(Fleet).filter(Fleet.id == vehicle_id).first()
    if vehicle is None:
        return None

    if vehicle.status != "idle":
        return {
            "vehicle_id": vehicle.id,
            "vehicle_vehicle_id": vehicle.vehicle_id,
            "status": vehicle.status,
            "redeployable": False,
            "note": f"Vehicle is {vehicle.status!r}, not idle — redeployment not applicable.",
        }

    active_disruption = (
        db.query(Disruption)
        .filter(Disruption.status == "active")
        .order_by(Disruption.severity.desc())
        .first()
    )

    stranded = db.query(Shipment).filter(
        Shipment.status.in_(["at_risk", "delayed"]),
        Shipment.disruption_id.isnot(None),
    ).all()

    required_kg = max((s.weight_kg for s in stranded), default=0.0)
    stranded_cargo_types = list({s.cargo_type for s in stranded})

    result = score_vehicle(vehicle, active_disruption, required_kg, stranded_cargo_types)
    result["redeployable"] = vehicle.redeployable
    return result


def get_ranked_idle_fleet(db: Session) -> list[dict[str, Any]]:
    """
    Return all idle vehicles scored and ranked by redeployment_score descending.
    """
    from models import Fleet, Disruption, Shipment

    idle_vehicles = db.query(Fleet).filter(Fleet.status == "idle").all()

    active_disruption = (
        db.query(Disruption)
        .filter(Disruption.status == "active")
        .order_by(Disruption.severity.desc())
        .first()
    )

    stranded = db.query(Shipment).filter(
        Shipment.status.in_(["at_risk", "delayed"]),
        Shipment.disruption_id.isnot(None),
    ).all()

    required_kg = max((s.weight_kg for s in stranded), default=0.0)
    stranded_cargo_types = list({s.cargo_type for s in stranded})

    results = []
    for v in idle_vehicles:
        scored = score_vehicle(v, active_disruption, required_kg, stranded_cargo_types)
        scored["redeployable"] = v.redeployable
        results.append(scored)

    results.sort(key=lambda r: r["redeployment_score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results
