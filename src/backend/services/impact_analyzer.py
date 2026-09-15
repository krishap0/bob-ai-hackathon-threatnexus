"""
FLEETIQ — Shipment Impact Analyzer (Phase 3)
=============================================
Computes a deterministic, explainable impact_score (0–100) for every shipment
that is linked to an active disruption.

Scoring formula
---------------
impact_score = min(
    severity_base
    + proximity_factor
    + cargo_modifier
    + value_modifier,
    100.0
)

Factor breakdown
----------------
1. severity_base  (max 50)
   Derived from the disruption severity.
   critical → 50 | high → 37.5 | medium → 25 | low → 12.5

2. proximity_factor  (max 20)
   How soon the estimated arrival is, relative to "now" (seed reference = 2026-01-13).
   ≤ 1 day away → 20   (urgent)
   ≤ 3 days     → 15
   ≤ 7 days     → 10
   > 7 days     →  5

3. cargo_modifier  (max 20)
   cold_chain → +20  (temperature-sensitive, highest risk)
   hazmat     → +15
   fragile    → +10
   standard   →  +0

4. value_modifier  (max 10)
   log10(value_usd) × 1.5, capped at 10.
   $1 → 0  |  $10 k → ~6  |  $1 M → ~9

All factors are deterministic — no random values, no external API calls.
The score is persisted back to shipment.impact_score in the database.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Reference "now" for proximity calculations
# Using a fixed seed reference date so scores are fully deterministic.
# ---------------------------------------------------------------------------
_SEED_REFERENCE_DATE = datetime(2026, 1, 13, 12, 0, 0)  # noon on seed day

# ---------------------------------------------------------------------------
# Severity weights
# ---------------------------------------------------------------------------
_SEVERITY_BASE: dict[str, float] = {
    "critical": 50.0,
    "high":     37.5,
    "medium":   25.0,
    "low":      12.5,
}

# ---------------------------------------------------------------------------
# Cargo type modifier
# ---------------------------------------------------------------------------
_CARGO_MODIFIER: dict[str, float] = {
    "cold_chain": 20.0,
    "hazmat":     15.0,
    "fragile":    10.0,
    "standard":    0.0,
}


def _proximity_factor(estimated_arrival: datetime | None) -> tuple[float, str]:
    """
    Return (factor, explanation) based on days until estimated arrival.
    Uses _SEED_REFERENCE_DATE as 'now' for determinism.
    """
    if estimated_arrival is None:
        return 5.0, "No ETA available → minimal proximity factor (5)"

    # Normalise: strip timezone if present so subtraction works
    if estimated_arrival.tzinfo is not None:
        eta = estimated_arrival.replace(tzinfo=None)
    else:
        eta = estimated_arrival

    days_until = (eta - _SEED_REFERENCE_DATE).total_seconds() / 86400.0

    if days_until <= 1:
        return 20.0, f"ETA in {days_until:.1f} day(s) — arriving very soon → max proximity factor (20)"
    if days_until <= 3:
        return 15.0, f"ETA in {days_until:.1f} day(s) — arriving within 3 days → proximity factor (15)"
    if days_until <= 7:
        return 10.0, f"ETA in {days_until:.1f} day(s) — arriving within a week → proximity factor (10)"
    return 5.0, f"ETA in {days_until:.1f} day(s) — more than a week away → low proximity factor (5)"


def _value_modifier(value_usd: float) -> tuple[float, str]:
    """
    Return (modifier, explanation).
    log10(value_usd) × 1.5, capped at 10.
    Handles zero/negative values safely.
    """
    if value_usd <= 0:
        return 0.0, "No cargo value recorded → value modifier (0)"
    raw = math.log10(max(value_usd, 1.0)) * 1.5
    capped = min(round(raw, 2), 10.0)
    return capped, f"value_usd=${value_usd:,.0f} → log10({value_usd:.0f})×1.5 = {raw:.2f}, capped at {capped}"


def compute_impact_score(shipment, disruption) -> dict[str, Any]:
    """
    Compute the impact_score for a single shipment under a single disruption.

    Returns a dict with:
      impact_score   float  0–100
      risk_label     str    "critical" | "high" | "medium" | "low"
      breakdown      dict   per-factor values
      explanation    list[str]
    """
    explanation: list[str] = []

    # Factor 1 — severity base
    sev_base = _SEVERITY_BASE.get(disruption.severity, 25.0)
    explanation.append(
        f"Disruption severity={disruption.severity!r} → severity_base={sev_base}"
    )

    # Factor 2 — proximity
    prox, prox_exp = _proximity_factor(shipment.estimated_arrival)
    explanation.append(prox_exp)

    # Factor 3 — cargo modifier
    cargo_mod = _CARGO_MODIFIER.get(shipment.cargo_type, 0.0)
    explanation.append(
        f"Cargo type={shipment.cargo_type!r} → cargo_modifier={cargo_mod}"
    )

    # Factor 4 — value modifier
    val_mod, val_exp = _value_modifier(shipment.value_usd)
    explanation.append(val_exp)

    raw = sev_base + prox + cargo_mod + val_mod
    score = round(min(raw, 100.0), 2)

    # Determine risk label from final score
    if score >= 75:
        risk_label = "critical"
    elif score >= 55:
        risk_label = "high"
    elif score >= 35:
        risk_label = "medium"
    else:
        risk_label = "low"

    return {
        "impact_score": score,
        "risk_label": risk_label,
        "breakdown": {
            "severity_base": sev_base,
            "proximity_factor": prox,
            "cargo_modifier": cargo_mod,
            "value_modifier": val_mod,
            "raw_sum": round(raw, 2),
        },
        "explanation": explanation,
    }


def compute_impact_scores(db: Session) -> int:
    """
    Compute and persist impact_score for all shipments that have a disruption_id.
    Returns the number of shipments updated.
    Safe to call multiple times (idempotent update).
    """
    from models import Shipment, Disruption

    updated = 0
    shipments = db.query(Shipment).filter(Shipment.disruption_id.isnot(None)).all()
    for shipment in shipments:
        disruption = db.query(Disruption).filter(
            Disruption.id == shipment.disruption_id
        ).first()
        if disruption is None:
            continue
        result = compute_impact_score(shipment, disruption)
        shipment.impact_score = result["impact_score"]
        updated += 1

    db.commit()
    return updated


def get_shipment_impact_detail(shipment_id: str, db: Session) -> dict[str, Any] | None:
    """
    Return full impact scoring detail for a single shipment.
    Returns None if the shipment has no disruption link.
    """
    from models import Shipment, Disruption

    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if shipment is None:
        return None
    if shipment.disruption_id is None:
        return {
            "shipment_id": shipment_id,
            "tracking_number": shipment.tracking_number,
            "impact_score": 0.0,
            "risk_label": "low",
            "breakdown": {},
            "explanation": ["Shipment is not linked to any active disruption."],
        }

    disruption = db.query(Disruption).filter(
        Disruption.id == shipment.disruption_id
    ).first()
    if disruption is None:
        return None

    result = compute_impact_score(shipment, disruption)
    return {
        "shipment_id": shipment_id,
        "tracking_number": shipment.tracking_number,
        "disruption_id": disruption.id,
        "disruption_title": disruption.title,
        **result,
    }


def get_all_impacted_shipments(db: Session) -> list[dict[str, Any]]:
    """
    Return all shipments with a disruption link, scored and sorted by impact_score desc.
    """
    from models import Shipment, Disruption

    shipments = db.query(Shipment).filter(Shipment.disruption_id.isnot(None)).all()
    results = []
    for s in shipments:
        d = db.query(Disruption).filter(Disruption.id == s.disruption_id).first()
        if d is None:
            continue
        scored = compute_impact_score(s, d)
        results.append({
            "shipment_id": s.id,
            "tracking_number": s.tracking_number,
            "status": s.status,
            "cargo_type": s.cargo_type,
            "origin": s.origin,
            "destination": s.destination,
            "carrier_code": s.carrier_code,
            "disruption_id": d.id,
            "disruption_severity": d.severity,
            **scored,
        })

    results.sort(key=lambda r: r["impact_score"], reverse=True)
    return results
