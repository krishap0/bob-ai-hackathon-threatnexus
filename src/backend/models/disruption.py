"""
Disruption ORM model.
Represents a supply-chain disruption event (port congestion, severe weather, etc.).
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, JSON, Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base


class Disruption(Base):
    __tablename__ = "disruptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Classification
    type = Column(
        SAEnum(
            "port_congestion",
            "road_closure",
            "severe_weather",
            "carrier_outage",
            "geopolitical",
            name="disruption_type",
        ),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    description = Column(String(2000), nullable=False, default="")
    severity = Column(
        SAEnum("low", "medium", "high", "critical", name="disruption_severity"),
        nullable=False,
    )
    status = Column(
        SAEnum("active", "monitoring", "resolved", name="disruption_status"),
        nullable=False,
        default="active",
    )

    # Geography
    affected_region = Column(String(200), nullable=False)
    affected_routes = Column(JSON, nullable=False, default=list)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Timing
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Source
    source = Column(String(100), nullable=False, default="Manual")

    # Relationships — a disruption can affect many shipments
    shipments = relationship("Shipment", back_populates="disruption")

    def __repr__(self):
        return f"<Disruption id={self.id!r} type={self.type!r} severity={self.severity!r}>"
