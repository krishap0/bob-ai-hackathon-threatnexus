"""
Fleet ORM model.
Represents a fleet vehicle (truck, van, ship, rail car, air freight).
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, Enum as SAEnum
from database import Base


class Fleet(Base):
    __tablename__ = "fleet"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vehicle_id = Column(String(50), nullable=False, unique=True)  # e.g. "TRK-042"

    # Classification
    vehicle_type = Column(
        SAEnum("truck", "van", "ship", "rail_car", "air_freight", name="vehicle_type"),
        nullable=False,
    )
    status = Column(
        SAEnum("active", "idle", "maintenance", "decommissioned", name="fleet_status"),
        nullable=False,
        default="active",
    )

    # Location
    current_location = Column(String(200), nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Capacity
    capacity_kg = Column(Float, nullable=False, default=0.0)
    available_capacity_kg = Column(Float, nullable=False, default=0.0)

    # Timing
    last_active_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    idle_since = Column(DateTime, nullable=True)

    # Assignment
    assigned_route = Column(String(50), nullable=True)

    # Computed by Phase 3 fleet_optimizer — stored for API access
    redeployable = Column(Boolean, nullable=False, default=False)
    redeployment_score = Column(Float, nullable=False, default=0.0)

    def __repr__(self):
        return f"<Fleet vehicle_id={self.vehicle_id!r} status={self.status!r}>"
