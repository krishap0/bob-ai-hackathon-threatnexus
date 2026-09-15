"""
ColdChainReading ORM model.
Represents a temperature sensor reading for a cold-chain shipment.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from database import Base


class ColdChainReading(Base):
    __tablename__ = "cold_chain_readings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Link to shipment
    shipment_id = Column(String(36), ForeignKey("shipments.id"), nullable=False)
    sensor_id = Column(String(50), nullable=False)

    # Reading
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    temperature_c = Column(Float, nullable=False)
    humidity_pct = Column(Float, nullable=True)

    # Required temperature range for this cargo
    required_min_c = Column(Float, nullable=False)
    required_max_c = Column(Float, nullable=False)

    # Excursion detection (computed during seed / Phase 3 ranker)
    excursion = Column(Boolean, nullable=False, default=False)
    excursion_duration_min = Column(Float, nullable=True)

    # Severity — computed by Phase 3 cold_chain_ranker
    severity = Column(
        SAEnum("none", "minor", "moderate", "severe", "critical", name="excursion_severity"),
        nullable=False,
        default="none",
    )
    severity_score = Column(Float, nullable=False, default=0.0)

    # Cargo sensitivity type (used by ranker lookup table)
    cargo_sensitivity = Column(
        SAEnum("standard", "pharmaceutical", "frozen_food", "fresh_produce", name="cargo_sensitivity"),
        nullable=False,
        default="standard",
    )

    # Relationships
    shipment = relationship("Shipment", back_populates="cold_chain_readings")

    def __repr__(self):
        return (
            f"<ColdChainReading shipment={self.shipment_id!r} "
            f"temp={self.temperature_c}°C excursion={self.excursion}>"
        )
