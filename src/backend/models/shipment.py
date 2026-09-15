"""
Shipment ORM model.
Represents a freight shipment that may be affected by a disruption.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tracking_number = Column(String(50), nullable=False, unique=True)

    # Route information
    origin = Column(String(200), nullable=False)
    destination = Column(String(200), nullable=False)
    current_location = Column(String(200), nullable=False)
    route_id = Column(String(50), nullable=False)  # matches disruption.affected_routes entries
    carrier_code = Column(String(20), nullable=False)

    # Status
    status = Column(
        SAEnum(
            "on_time", "delayed", "at_risk", "diverted", "delivered",
            name="shipment_status",
        ),
        nullable=False,
        default="on_time",
    )

    # Cargo
    cargo_type = Column(
        SAEnum("standard", "cold_chain", "hazmat", "fragile", name="cargo_type"),
        nullable=False,
        default="standard",
    )
    cargo_description = Column(String(300), nullable=False, default="")
    weight_kg = Column(Float, nullable=False, default=0.0)
    value_usd = Column(Float, nullable=False, default=0.0)

    # Timing
    estimated_arrival = Column(DateTime, nullable=False)
    actual_arrival = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Disruption link (nullable — not all shipments are affected)
    disruption_id = Column(String(36), ForeignKey("disruptions.id"), nullable=True)

    # Computed by Phase 3 impact_analyzer — stored here for API access
    impact_score = Column(Float, nullable=False, default=0.0)

    # Relationships
    disruption = relationship("Disruption", back_populates="shipments")
    cold_chain_readings = relationship("ColdChainReading", back_populates="shipment")

    def __repr__(self):
        return f"<Shipment tracking={self.tracking_number!r} status={self.status!r}>"
