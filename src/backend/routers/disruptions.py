"""
Disruptions router — GET /api/disruptions
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Disruption, Shipment
from schemas import DisruptionOut, DisruptionList, ShipmentList, ShipmentOut

router = APIRouter(prefix="/api/disruptions", tags=["Disruptions"])


@router.get("", response_model=DisruptionList)
def list_disruptions(
    status: Optional[str] = None,
    type: Optional[str] = None,
    severity: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all disruptions with optional filters."""
    query = db.query(Disruption)
    if status:
        query = query.filter(Disruption.status == status)
    if type:
        query = query.filter(Disruption.type == type)
    if severity:
        query = query.filter(Disruption.severity == severity)
    items = query.order_by(Disruption.started_at.desc()).all()
    return DisruptionList(total=len(items), items=items)


@router.get("/{disruption_id}", response_model=DisruptionOut)
def get_disruption(disruption_id: str, db: Session = Depends(get_db)):
    """Get a single disruption by ID."""
    obj = db.query(Disruption).filter(Disruption.id == disruption_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Disruption not found")
    return obj


@router.get("/{disruption_id}/affected", response_model=ShipmentList)
def get_affected_shipments(disruption_id: str, db: Session = Depends(get_db)):
    """List all shipments linked to this disruption."""
    disruption = db.query(Disruption).filter(Disruption.id == disruption_id).first()
    if not disruption:
        raise HTTPException(status_code=404, detail="Disruption not found")
    items = (
        db.query(Shipment)
        .filter(Shipment.disruption_id == disruption_id)
        .order_by(Shipment.impact_score.desc())
        .all()
    )
    return ShipmentList(total=len(items), items=items)
