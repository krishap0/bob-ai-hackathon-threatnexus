"""
Carrier ORM model.
Represents a freight carrier with scoring attributes used for recommendations.
"""

import uuid
from sqlalchemy import Column, String, Float, Boolean
from database import Base


class Carrier(Base):
    __tablename__ = "carriers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False, unique=True)
    code = Column(String(20), nullable=False, unique=True)  # e.g. "MAERSK"

    # Scoring attributes used by route_recommender (Phase 3)
    reliability_score = Column(Float, nullable=False, default=0.8)   # 0–1
    speed_score = Column(Float, nullable=False, default=0.7)          # 0–1
    cost_index = Column(Float, nullable=False, default=1.0)           # relative multiplier
    active = Column(Boolean, nullable=False, default=True)

    # Supported route types (stored as comma-separated string for simplicity)
    supported_route_types = Column(String(200), nullable=False, default="sea,land,air")

    def __repr__(self):
        return f"<Carrier code={self.code!r} name={self.name!r}>"
