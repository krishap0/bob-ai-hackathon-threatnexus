from __future__ import annotations
from typing import List
from pydantic import BaseModel


class CarrierOut(BaseModel):
    id: str
    name: str
    code: str
    reliability_score: float
    speed_score: float
    cost_index: float
    active: bool
    supported_route_types: str

    model_config = {"from_attributes": True}


class CarrierList(BaseModel):
    total: int
    items: List[CarrierOut]
