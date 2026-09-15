"""
Carriers router — GET /api/carriers
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Carrier
from schemas import CarrierOut, CarrierList

router = APIRouter(prefix="/api/carriers", tags=["Carriers"])


@router.get("", response_model=CarrierList)
def list_carriers(db: Session = Depends(get_db)):
    """List all carriers."""
    items = db.query(Carrier).order_by(Carrier.name).all()
    return CarrierList(total=len(items), items=items)


@router.get("/{carrier_id}", response_model=CarrierOut)
def get_carrier(carrier_id: str, db: Session = Depends(get_db)):
    """Get a single carrier by ID."""
    obj = db.query(Carrier).filter(Carrier.id == carrier_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Carrier not found")
    return obj
