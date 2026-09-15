"""
Shipments router — GET /api/shipments
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Shipment
from schemas import ShipmentOut, ShipmentList

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


@router.get("/{shipment_id}", response_model=ShipmentOut)
def get_shipment(shipment_id: str, db: Session = Depends(get_db)):
    """Get a single shipment by ID."""
    obj = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return obj
