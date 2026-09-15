"""
Summary router — Phase 4: watsonx.ai AI summary fully wired.

GET /api/summary/stats  — raw operational statistics used to build the prompt
GET /api/summary        — collects stats, calls watsonx Granite, returns generated text
                          (falls back gracefully if credentials are missing or call fails)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Disruption, Shipment, Fleet, ColdChainReading
from services.watsonx_client import generate_summary

router = APIRouter(prefix="/api/summary", tags=["Summary"])


# ---------------------------------------------------------------------------
# Helper — collect enriched stats from the database
# ---------------------------------------------------------------------------

def _collect_stats(db: Session) -> dict:
    """
    Gather operational statistics from the database.
    Returns the base stats dict plus optional enrichment fields used
    by the watsonx prompt builder.
    """
    active_disruptions = (
        db.query(Disruption).filter(Disruption.status == "active").count()
    )
    shipments_at_risk = (
        db.query(Shipment)
        .filter(Shipment.status.in_(["at_risk", "delayed"]))
        .count()
    )
    idle_fleet = db.query(Fleet).filter(Fleet.status == "idle").count()
    cold_chain_excursions = (
        db.query(ColdChainReading)
        .filter(ColdChainReading.excursion == True)  # noqa: E712
        .count()
    )
    critical_excursions = (
        db.query(ColdChainReading)
        .filter(
            ColdChainReading.excursion == True,  # noqa: E712
            ColdChainReading.severity == "critical",
        )
        .count()
    )

    # --- enrichment: disruption breakdown by type ---
    type_rows = (
        db.query(Disruption.type, Disruption.type)
        .filter(Disruption.status == "active")
        .all()
    )
    type_counts: dict[str, int] = {}
    for row in (
        db.query(Disruption.type)
        .filter(Disruption.status == "active")
        .all()
    ):
        t = row[0]
        type_counts[t] = type_counts.get(t, 0) + 1
    breakdown = ", ".join(f"{v} {k}" for k, v in type_counts.items())

    # --- enrichment: top at-risk shipment by impact_score ---
    top_shp = (
        db.query(Shipment)
        .filter(Shipment.status.in_(["at_risk", "delayed"]))
        .order_by(Shipment.impact_score.desc())
        .first()
    )
    top_shipment_str = (
        f"{top_shp.tracking_number} (impact score {top_shp.impact_score:.1f})"
        if top_shp and top_shp.impact_score
        else ""
    )

    return {
        "active_disruptions": active_disruptions,
        "shipments_at_risk": shipments_at_risk,
        "idle_fleet": idle_fleet,
        "cold_chain_excursions": cold_chain_excursions,
        "critical_excursions": critical_excursions,
        "disruption_breakdown": breakdown,
        "top_shipment": top_shipment_str,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/stats")
def get_summary_stats(db: Session = Depends(get_db)):
    """Return raw operational statistics used to build the AI summary prompt."""
    stats = _collect_stats(db)
    # Expose only the base numeric fields in the public stats endpoint
    return {
        "active_disruptions": stats["active_disruptions"],
        "shipments_at_risk": stats["shipments_at_risk"],
        "idle_fleet": stats["idle_fleet"],
        "cold_chain_excursions": stats["cold_chain_excursions"],
        "critical_excursions": stats["critical_excursions"],
    }


@router.get("")
def get_summary(db: Session = Depends(get_db)):
    """
    AI operational summary endpoint.

    Collects live DB statistics, enriches them, and calls IBM watsonx.ai
    Granite via generate_summary(). If credentials are missing or the API
    call fails, returns a template-filled fallback with ai_generated=False.
    """
    stats = _collect_stats(db)
    result = generate_summary(stats)
    return {
        "summary": result["summary"],
        "stats": {
            "active_disruptions": stats["active_disruptions"],
            "shipments_at_risk": stats["shipments_at_risk"],
            "idle_fleet": stats["idle_fleet"],
            "cold_chain_excursions": stats["cold_chain_excursions"],
            "critical_excursions": stats["critical_excursions"],
        },
        "ai_generated": result["ai_generated"],
        "model_id": result["model_id"],
    }
