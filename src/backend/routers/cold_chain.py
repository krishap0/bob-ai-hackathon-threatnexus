"""
Cold-chain router — GET /api/cold-chain  (Phase 2 + Phase 3 extensions)
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import ColdChainReading
from schemas import ColdChainReadingOut, ColdChainReadingList
from services import cold_chain_ranker

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


@router.get("/ranked")
def list_ranked_excursions(db: Session = Depends(get_db)):
    """
    Phase 3: Return all excursion readings with full severity scoring,
    ranked by severity_score descending.
    """
    items = cold_chain_ranker.get_ranked_excursions(db)
    return {"total": len(items), "items": items}


@router.get("/{reading_id}/severity")
def get_reading_severity(reading_id: str, db: Session = Depends(get_db)):
    """Phase 3: Full severity scoring breakdown for a single cold-chain reading."""
    result = cold_chain_ranker.get_reading_severity_detail(reading_id, db)
    if result is None:
        raise HTTPException(status_code=404, detail="Cold-chain reading not found")
    return result


@router.get("/{reading_id}", response_model=ColdChainReadingOut)
def get_reading(reading_id: str, db: Session = Depends(get_db)):
    """Get a single cold-chain reading by ID."""
    obj = db.query(ColdChainReading).filter(ColdChainReading.id == reading_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Cold-chain reading not found")
    return obj
