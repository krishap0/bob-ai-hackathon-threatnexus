"""
Fleet router — GET /api/fleet
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Fleet
from schemas import FleetOut, FleetList

router = APIRouter(prefix="/api/fleet", tags=["Fleet"])


@router.get("", response_model=FleetList)
def list_fleet(
    status: Optional[str] = None,
    vehicle_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List all fleet vehicles with optional filters."""
    query = db.query(Fleet)
    if status:
        query = query.filter(Fleet.status == status)
    if vehicle_type:
        query = query.filter(Fleet.vehicle_type == vehicle_type)
    items = query.order_by(Fleet.vehicle_id).all()
    return FleetList(total=len(items), items=items)


@router.get("/idle", response_model=FleetList)
def list_idle_fleet(db: Session = Depends(get_db)):
    """List only idle and redeployable fleet vehicles, ranked by redeployment_score."""
    items = (
        db.query(Fleet)
        .filter(Fleet.status == "idle")
        .order_by(Fleet.redeployment_score.desc())
        .all()
    )
    return FleetList(total=len(items), items=items)


@router.get("/{fleet_id}", response_model=FleetOut)
def get_fleet_vehicle(fleet_id: str, db: Session = Depends(get_db)):
    """Get a single fleet vehicle by ID."""
    obj = db.query(Fleet).filter(Fleet.id == fleet_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Fleet vehicle not found")
    return obj
