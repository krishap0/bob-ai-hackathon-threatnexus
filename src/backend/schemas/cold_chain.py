from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class ColdChainReadingOut(BaseModel):
    id: str
    shipment_id: str
    sensor_id: str
    recorded_at: datetime
    temperature_c: float
    humidity_pct: Optional[float]
    required_min_c: float
    required_max_c: float
    excursion: bool
    excursion_duration_min: Optional[float]
    severity: str
    severity_score: float
    cargo_sensitivity: str

    model_config = {"from_attributes": True}


class ColdChainReadingList(BaseModel):
    total: int
    items: List[ColdChainReadingOut]
