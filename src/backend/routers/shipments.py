"""
Shipments router — GET /api/shipments  (Phase 2 + Phase 3 extensions)
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Shipment
from schemas import ShipmentOut, ShipmentList
from services import impact_analyzer, route_recommender

router = APIRouter(prefix="/api/shipments", tags=["Shipments"])


@router.get("", response_model=ShipmentList)
def list_shipments(
    status: Optional[str] = None,
    cargo_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all shipments with optional filters."""
    query = db.query(Shipment)
    if status:
        query = query.filter(Shipment.status == status)
    if cargo_type:
        query = query.filter(Shipment.cargo_type == cargo_type)
    items = query.order_by(Shipment.impact_score.desc()).all()
    return ShipmentList(total=len(items), items=items)


@router.get("/impacted")
def list_impacted_shipments(db: Session = Depends(get_db)):
    """
    Phase 3: Return all shipments with a disruption link,
    scored by impact_score and sorted highest-first.
    """
    return {"items": impact_analyzer.get_all_impacted_shipments(db)}


@router.get("/{shipment_id}", response_model=ShipmentOut)
def get_shipment(shipment_id: str, db: Session = Depends(get_db)):
    """Get a single shipment by ID."""
    obj = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return obj


@router.get("/{shipment_id}/impact")
def get_shipment_impact(shipment_id: str, db: Session = Depends(get_db)):
    """Phase 3: Full impact scoring breakdown for a single shipment."""
    result = impact_analyzer.get_shipment_impact_detail(shipment_id, db)
    if result is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return result


@router.get("/{shipment_id}/recommendations")
def get_shipment_recommendations(shipment_id: str, db: Session = Depends(get_db)):
    """Phase 3: Ranked reroute / carrier-change / hold recommendations for a shipment."""
    obj = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return route_recommender.get_recommendations(shipment_id, db)
