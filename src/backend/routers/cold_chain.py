"""
Cold-chain router — GET /api/cold-chain
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import ColdChainReading
from schemas import ColdChainReadingOut, ColdChainReadingList

router = APIRouter(prefix="/api/cold-chain", tags=["Cold Chain"])


@router.get("", response_model=ColdChainReadingList)
def list_cold_chain_readings(
    excursion_only: bool = False,
    shipment_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List cold-chain sensor readings. Pass excursion_only=true to filter excursions."""
    query = db.query(ColdChainReading)
    if excursion_only:
        query = query.filter(ColdChainReading.excursion == True)  # noqa: E712
    if shipment_id:
        query = query.filter(ColdChainReading.shipment_id == shipment_id)
    items = query.order_by(ColdChainReading.recorded_at.desc()).all()
    return ColdChainReadingList(total=len(items), items=items)


@router.get("/ranked", response_model=ColdChainReadingList)
def list_ranked_excursions(db: Session = Depends(get_db)):
    """List all excursions ranked by severity_score descending."""
    items = (
        db.query(ColdChainReading)
        .filter(ColdChainReading.excursion == True)  # noqa: E712
        .order_by(ColdChainReading.severity_score.desc())
        .all()
    )
    return ColdChainReadingList(total=len(items), items=items)


@router.get("/{reading_id}", response_model=ColdChainReadingOut)
def get_reading(reading_id: str, db: Session = Depends(get_db)):
    """Get a single cold-chain reading by ID."""
    obj = db.query(ColdChainReading).filter(ColdChainReading.id == reading_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Cold-chain reading not found")
    return obj
