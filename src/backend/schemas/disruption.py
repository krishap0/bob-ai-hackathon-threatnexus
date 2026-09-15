from __future__ import annotations
from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel


class DisruptionOut(BaseModel):
    id: str
    type: str
    title: str
    description: str
    severity: str
    status: str
    affected_region: str
    affected_routes: List[Any]
    latitude: Optional[float]
    longitude: Optional[float]
    started_at: datetime
    resolved_at: Optional[datetime]
    created_at: datetime
    source: str

    model_config = {"from_attributes": True}


class DisruptionList(BaseModel):
    total: int
    items: List[DisruptionOut]
