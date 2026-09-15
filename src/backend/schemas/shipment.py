from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class ShipmentOut(BaseModel):
    id: str
    tracking_number: str
    origin: str
    destination: str
    current_location: str
    route_id: str
    carrier_code: str
    status: str
    cargo_type: str
    cargo_description: str
    weight_kg: float
    value_usd: float
    estimated_arrival: datetime
    actual_arrival: Optional[datetime]
    created_at: datetime
    disruption_id: Optional[str]
    impact_score: float

    model_config = {"from_attributes": True}


class ShipmentList(BaseModel):
    total: int
    items: List[ShipmentOut]
