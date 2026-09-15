"""
FLEETIQ — Cold-Chain Severity Ranker (Phase 3)
===============================================
Classifies and scores temperature excursions for cold-chain shipments.

Severity score formula
-----------------------
severity_score = min((magnitude × 5) + (duration_min / 10), 100.0)

Where:
  magnitude    = degrees outside the acceptable temperature range
                 = max(required_min_c − temperature_c, 0)    if below range
                   max(temperature_c − required_max_c, 0)    if above range
  duration_min = excursion_duration_min (if known)

Severity classification bands
------------------------------
  critical  magnitude > 10°C  OR  duration > 240 min
  severe    magnitude 5–10°C  OR  duration 120–240 min
  moderate  magnitude 2–5°C   OR  duration 60–120 min
  minor     otherwise (excursion exists but mild)
  none      no excursion detected

Cargo sensitivity multiplier (applied to severity_score, not to band decision)
---------------------------------------
  pharmaceutical  × 1.3  (very sensitive — small excursion = high risk)
  frozen_food     × 1.2
  fresh_produce   × 1.15
  standard        × 1.0

The final score is capped at 100 after applying the multiplier.

Results are stored back to ColdChainReading.severity and .severity_score in the DB.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Sensitivity multipliers per cargo_sensitivity field
# ---------------------------------------------------------------------------
_SENSITIVITY_MULTIPLIER: dict[str, float] = {
    "pharmaceutical": 1.3,
    "frozen_food":    1.2,
    "fresh_produce":  1.15,
    "standard":       1.0,
}

# ---------------------------------------------------------------------------
# Severity band thresholds
# ---------------------------------------------------------------------------

def _classify_severity(magnitude: float, duration_min: float | None) -> str:
    """
    Return the severity band string based on magnitude (°C) and duration (min).
    Applies the plan's OR logic: either magnitude OR duration can trigger a band.
    """
    dur = duration_min or 0.0

    if magnitude > 10.0 or dur > 240.0:
        return "critical"
    if magnitude >= 5.0 or dur >= 120.0:
        return "severe"
    if magnitude >= 2.0 or dur >= 60.0:
        return "moderate"
    if magnitude > 0.0 or dur > 0.0:
        return "minor"
    return "none"


def compute_excursion_severity(reading) -> dict[str, Any]:
    """
    Compute severity classification and score for a single ColdChainReading.

    Returns:
      excursion        bool
      magnitude_c      float  degrees outside acceptable range (0 if within range)
      severity         str    none | minor | moderate | severe | critical
      severity_score   float  0–100
      sensitivity_mult float  cargo sensitivity multiplier applied
      explanation      list[str]
    """
    explanation: list[str] = []

    # --- Guard: invalid temperature values ---
    try:
        temp = float(reading.temperature_c)
        req_min = float(reading.required_min_c)
        req_max = float(reading.required_max_c)
    except (TypeError, ValueError):
        return {
            "excursion": False,
            "magnitude_c": 0.0,
            "severity": "none",
            "severity_score": 0.0,
            "sensitivity_mult": 1.0,
            "explanation": ["Invalid temperature data — cannot assess excursion."],
        }

    # --- Compute magnitude ---
    if temp < req_min:
        magnitude = round(req_min - temp, 3)
        explanation.append(
            f"Temperature {temp}°C is {magnitude:.2f}°C BELOW minimum {req_min}°C"
        )
    elif temp > req_max:
        magnitude = round(temp - req_max, 3)
        explanation.append(
            f"Temperature {temp}°C is {magnitude:.2f}°C ABOVE maximum {req_max}°C"
        )
    else:
        magnitude = 0.0
        explanation.append(
            f"Temperature {temp}°C is within acceptable range [{req_min}°C, {req_max}°C] — no excursion"
        )
        return {
            "excursion": False,
            "magnitude_c": 0.0,
            "severity": "none",
            "severity_score": 0.0,
            "sensitivity_mult": 1.0,
            "explanation": explanation,
        }

    # --- Duration ---
    duration = reading.excursion_duration_min
    if duration is not None:
        explanation.append(f"Excursion duration: {duration:.0f} minutes")
    else:
        explanation.append("Excursion duration not recorded — using 0 min for scoring")

    # --- Severity band ---
    severity = _classify_severity(magnitude, duration)
    explanation.append(f"Severity band → {severity!r} (magnitude={magnitude:.2f}°C, duration={duration or 0:.0f} min)")

    # --- Raw score ---
    dur_contribution = (duration or 0.0) / 10.0
    raw_score = (magnitude * 5.0) + dur_contribution
    explanation.append(
        f"Raw score = ({magnitude:.2f} × 5) + ({duration or 0:.0f} / 10) = {raw_score:.2f}"
    )

    # --- Sensitivity multiplier ---
    sensitivity = getattr(reading, "cargo_sensitivity", "standard") or "standard"
    mult = _SENSITIVITY_MULTIPLIER.get(sensitivity, 1.0)
    if mult != 1.0:
        explanation.append(
            f"Cargo sensitivity={sensitivity!r} → multiplier ×{mult} applied"
        )

    final_score = round(min(raw_score * mult, 100.0), 2)
    explanation.append(f"Final severity_score = min({raw_score:.2f} × {mult}, 100) = {final_score}")

    return {
        "excursion": True,
        "magnitude_c": magnitude,
        "severity": severity,
        "severity_score": final_score,
        "sensitivity_mult": mult,
        "explanation": explanation,
    }


def rank_excursions(db: Session) -> int:
    """
    Compute and persist severity_score for all ColdChainReadings where excursion=True.
    Also corrects the severity field if it differs from the computed band.
    Returns the number of readings updated.
    """
    from models import ColdChainReading

    readings = db.query(ColdChainReading).filter(
        ColdChainReading.excursion == True  # noqa: E712
    ).all()

    for reading in readings:
        result = compute_excursion_severity(reading)
        reading.severity_score = result["severity_score"]
        reading.severity = result["severity"]

    db.commit()
    return len(readings)


def get_reading_severity_detail(reading_id: str, db: Session) -> dict[str, Any] | None:
    """Return full severity breakdown for a single ColdChainReading."""
    from models import ColdChainReading

    reading = db.query(ColdChainReading).filter(ColdChainReading.id == reading_id).first()
    if reading is None:
        return None

    result = compute_excursion_severity(reading)
    return {
        "reading_id": reading.id,
        "shipment_id": reading.shipment_id,
        "sensor_id": reading.sensor_id,
        "recorded_at": reading.recorded_at.isoformat() if reading.recorded_at else None,
        "temperature_c": reading.temperature_c,
        "required_min_c": reading.required_min_c,
        "required_max_c": reading.required_max_c,
        "excursion_duration_min": reading.excursion_duration_min,
        "cargo_sensitivity": reading.cargo_sensitivity,
        **result,
    }


def get_ranked_excursions(db: Session) -> list[dict[str, Any]]:
    """
    Return all excursion readings ranked by severity_score descending.
    """
    from models import ColdChainReading, Shipment

    readings = db.query(ColdChainReading).filter(
        ColdChainReading.excursion == True  # noqa: E712
    ).all()

    results = []
    for reading in readings:
        scored = compute_excursion_severity(reading)
        # Fetch tracking number for context
        shipment = db.query(Shipment).filter(Shipment.id == reading.shipment_id).first()
        results.append({
            "reading_id": reading.id,
            "shipment_id": reading.shipment_id,
            "tracking_number": shipment.tracking_number if shipment else None,
            "sensor_id": reading.sensor_id,
            "recorded_at": reading.recorded_at.isoformat() if reading.recorded_at else None,
            "temperature_c": reading.temperature_c,
            "required_min_c": reading.required_min_c,
            "required_max_c": reading.required_max_c,
            "excursion_duration_min": reading.excursion_duration_min,
            "cargo_sensitivity": reading.cargo_sensitivity,
            **scored,
        })

    results.sort(key=lambda r: r["severity_score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results
