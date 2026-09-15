from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class FleetOut(BaseModel):
    id: str
    vehicle_id: str
    vehicle_type: str
    status: str
    current_location: str
    latitude: Optional[float]
    longitude: Optional[float]
    capacity_kg: float
    available_capacity_kg: float
    last_active_at: datetime
    idle_since: Optional[datetime]
    assigned_route: Optional[str]
    redeployable: bool
    redeployment_score: float

    model_config = {"from_attributes": True}


class FleetList(BaseModel):
    total: int
    items: List[FleetOut]
