"""
FLEETIQ — Route & Carrier Recommender (Phase 3)
================================================
Generates up to 3 deterministic recommendations for an affected shipment.

Recommendation types
--------------------
1. reroute       — Use the same carrier but take an alternate (non-disrupted) route.
2. carrier_change — Switch to a different carrier while keeping the destination.
3. hold          — Hold the shipment at its current location until the disruption resolves.

Each recommendation includes:
  recommendation_type  str
  title                str   short human label
  description          str   full explanation
  estimated_delay_hrs  float additional hours expected
  cost_delta_usd       float estimated extra cost (positive = more expensive)
  trade_off_summary    str   plain-language trade-off
  score                float 0–100 (higher = better choice)
  rank                 int   1 = best recommendation

Scoring (determines rank):
  score = (speed_contribution × 40) + (reliability_contribution × 40) + (cost_contribution × 20)

All calculations are deterministic and based on seeded carrier data.
No external APIs are called. Estimates are clearly labelled as demo calculations.
"""

from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Base cost rate used for delay penalty calculations
# ---------------------------------------------------------------------------
_BASE_COST_PER_HOUR_USD = 120.0   # representative demo value

# Estimated hours saved by switching to air freight (premium option)
_AIR_SPEED_PREMIUM_HRS = 48.0

# Hold cost estimate: storage + demurrage per hour
_HOLD_COST_PER_HOUR_USD = 85.0

# Disruption resolution estimates by type (hours until expected resolution)
_DISRUPTION_RESOLUTION_HRS: dict[str, float] = {
    "port_congestion": 96.0,
    "severe_weather":  36.0,
    "carrier_outage":  48.0,
    "geopolitical":    120.0,
    "road_closure":    12.0,
}

# ---------------------------------------------------------------------------
# Recommendation builders
# ---------------------------------------------------------------------------

def _build_reroute_recommendation(
    shipment, disruption, carriers: list, all_carriers: list
) -> dict[str, Any] | None:
    """
    Suggest using an alternate route with the same carrier.
    Applies when there is at least one non-disrupted route available for the destination.
    """
    disrupted_routes: set = set(disruption.affected_routes or [])
    shipment_route = shipment.route_id

    # Build a plausible alternate route ID (deterministic: prefix + destination token)
    dest_token = shipment.destination.split(",")[0].strip().upper().replace(" ", "")[:3]
    origin_token = shipment.origin.split(",")[0].strip().upper().replace(" ", "")[:3]
    alt_route = f"ALT-{origin_token}-{dest_token}"

    # Delay estimate: rerouting adds 12–24 h depending on disruption severity
    sev_delay = {"critical": 24.0, "high": 18.0, "medium": 12.0, "low": 6.0}
    delay_hrs = sev_delay.get(disruption.severity, 12.0)
    cost_delta = delay_hrs * _BASE_COST_PER_HOUR_USD

    # Current carrier reliability
    current_carrier = next((c for c in all_carriers if c.code == shipment.carrier_code), None)
    carrier_name = current_carrier.name if current_carrier else shipment.carrier_code
    carrier_reliability = current_carrier.reliability_score if current_carrier else 0.8

    # Score: prefer rerouting when disruption severity is moderate/high and carrier reliable
    speed_contribution = max(0.0, 1.0 - (delay_hrs / 48.0))  # less delay → higher score
    reliability_contribution = carrier_reliability
    cost_contribution = max(0.0, 1.0 - (cost_delta / 5000.0))
    score = round(
        (speed_contribution * 40) + (reliability_contribution * 40) + (cost_contribution * 20),
        2,
    )

    return {
        "recommendation_type": "reroute",
        "title": f"Alternate Route via {alt_route}",
        "description": (
            f"Redirect shipment {shipment.tracking_number} from route {shipment_route!r} "
            f"to alternate route {alt_route!r} using current carrier {carrier_name}. "
            f"This avoids the {disruption.type.replace('_', ' ')} affecting {disruption.affected_region}. "
            f"[Demo estimate — based on {disruption.severity} severity disruption]"
        ),
        "estimated_delay_hrs": delay_hrs,
        "cost_delta_usd": round(cost_delta, 2),
        "trade_off_summary": (
            f"Adds ~{delay_hrs:.0f} hrs delay (+${cost_delta:,.0f}) but keeps existing carrier "
            f"relationship and avoids disruption zone."
        ),
        "score": score,
    }


def _build_carrier_change_recommendation(
    shipment, disruption, all_carriers: list
) -> dict[str, Any] | None:
    """
    Suggest switching to a better-scored alternate carrier.
    Picks the highest (reliability + speed - cost_index) carrier that is not the current one.
    """
    current_code = shipment.carrier_code
    candidates = [
        c for c in all_carriers
        if c.code != current_code and c.active
    ]
    if not candidates:
        return None

    # Rank by combined carrier score: reliability 50%, speed 30%, cost 20%
    def _carrier_score(c):
        return (c.reliability_score * 0.5) + (c.speed_score * 0.3) + ((2.0 - c.cost_index) * 0.2)

    best = max(candidates, key=_carrier_score)
    current = next((c for c in all_carriers if c.code == current_code), None)

    # Delay estimate: carrier change takes 6–12 h for re-booking + handover
    handover_hrs = 8.0
    # If new carrier is faster, it may recover some time
    speed_diff = (best.speed_score - (current.speed_score if current else 0.7))
    time_saved = speed_diff * 24.0  # up to 24 h faster if max speed difference
    net_delay = max(handover_hrs - time_saved, 0.0)

    # Cost delta: new carrier cost index vs current
    current_cost_index = current.cost_index if current else 1.0
    cost_delta = (best.cost_index - current_cost_index) * shipment.value_usd * 0.002

    # Score
    speed_contribution = best.speed_score
    reliability_contribution = best.reliability_score
    cost_contribution = max(0.0, 1.0 - (abs(cost_delta) / 3000.0))
    score = round(
        (speed_contribution * 40) + (reliability_contribution * 40) + (cost_contribution * 20),
        2,
    )

    trade_off_parts = []
    if net_delay > 0:
        trade_off_parts.append(f"~{net_delay:.0f} hrs extra for carrier handover")
    else:
        trade_off_parts.append("potentially faster delivery due to higher speed score")
    if cost_delta > 0:
        trade_off_parts.append(f"costs ~${cost_delta:,.0f} more")
    elif cost_delta < 0:
        trade_off_parts.append(f"saves ~${abs(cost_delta):,.0f}")
    trade_off_parts.append(
        f"reliability improves from {current.reliability_score:.0%} to {best.reliability_score:.0%}"
        if current else f"carrier reliability {best.reliability_score:.0%}"
    )

    return {
        "recommendation_type": "carrier_change",
        "title": f"Switch to {best.name} ({best.code})",
        "description": (
            f"Transfer shipment {shipment.tracking_number} from {current_code} to "
            f"{best.name} ({best.code}). {best.name} has reliability score {best.reliability_score:.0%} "
            f"and speed score {best.speed_score:.0%}. "
            f"[Demo estimate — carrier scores from seeded data]"
        ),
        "estimated_delay_hrs": round(net_delay, 1),
        "cost_delta_usd": round(cost_delta, 2),
        "trade_off_summary": "; ".join(trade_off_parts),
        "score": score,
    }


def _build_hold_recommendation(
    shipment, disruption
) -> dict[str, Any]:
    """
    Suggest holding the shipment at its current location until the disruption resolves.
    """
    hold_hrs = _DISRUPTION_RESOLUTION_HRS.get(disruption.type, 48.0)
    hold_cost = hold_hrs * _HOLD_COST_PER_HOUR_USD

    # Score: holding is better the faster the disruption resolves
    speed_contribution = max(0.0, 1.0 - (hold_hrs / 120.0))
    reliability_contribution = 0.9  # holding is very reliable operationally
    cost_contribution = max(0.0, 1.0 - (hold_cost / 10000.0))
    score = round(
        (speed_contribution * 40) + (reliability_contribution * 40) + (cost_contribution * 20),
        2,
    )

    return {
        "recommendation_type": "hold",
        "title": f"Hold at {shipment.current_location}",
        "description": (
            f"Hold shipment {shipment.tracking_number} at {shipment.current_location!r} "
            f"until the {disruption.type.replace('_', ' ')} disruption resolves. "
            f"Estimated disruption duration: ~{hold_hrs:.0f} hrs. "
            f"[Demo estimate — typical resolution time for {disruption.type}]"
        ),
        "estimated_delay_hrs": hold_hrs,
        "cost_delta_usd": round(hold_cost, 2),
        "trade_off_summary": (
            f"No rerouting complexity, but adds ~{hold_hrs:.0f} hrs delay and "
            f"~${hold_cost:,.0f} in holding costs. Best when disruption will resolve quickly."
        ),
        "score": score,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_recommendations(shipment_id: str, db: Session) -> dict[str, Any]:
    """
    Generate up to 3 ranked recommendations for a shipment.
    Returns an empty list if the shipment has no disruption link.
    """
    from models import Shipment, Disruption, Carrier

    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if shipment is None:
        return {"shipment_id": shipment_id, "recommendations": [], "error": "Shipment not found"}

    if shipment.disruption_id is None:
        return {
            "shipment_id": shipment_id,
            "tracking_number": shipment.tracking_number,
            "recommendations": [],
            "note": "Shipment is not linked to an active disruption. No recommendations generated.",
        }

    disruption = db.query(Disruption).filter(
        Disruption.id == shipment.disruption_id
    ).first()
    if disruption is None:
        return {"shipment_id": shipment_id, "recommendations": []}

    all_carriers = db.query(Carrier).all()

    recs = []

    # 1. Reroute recommendation
    reroute = _build_reroute_recommendation(shipment, disruption, [], all_carriers)
    if reroute:
        recs.append(reroute)

    # 2. Carrier change recommendation
    cc = _build_carrier_change_recommendation(shipment, disruption, all_carriers)
    if cc:
        recs.append(cc)

    # 3. Hold recommendation (always applicable)
    hold = _build_hold_recommendation(shipment, disruption)
    recs.append(hold)

    # Sort by score descending and assign ranks
    recs.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(recs):
        r["rank"] = i + 1

    return {
        "shipment_id": shipment_id,
        "tracking_number": shipment.tracking_number,
        "disruption_id": disruption.id,
        "disruption_title": disruption.title,
        "disruption_severity": disruption.severity,
        "recommendation_count": len(recs),
        "recommendations": recs,
    }
