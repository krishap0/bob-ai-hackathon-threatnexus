"""
FLEETIQ — Deterministic seed script.
Loads all demo data from JSON files and inserts it into the SQLite database.
Safe to run multiple times — clears and re-inserts on each run.
"""

import json
import os
import sys

# Ensure the backend root is on the path when running this script directly
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from datetime import datetime
from sqlalchemy.orm import Session
from database import engine, SessionLocal, Base
from models.disruption import Disruption
from models.carrier import Carrier
from models.shipment import Shipment
from models.fleet import Fleet
from models.cold_chain import ColdChainReading

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _load(filename: str) -> list:
    path = os.path.join(_DATA_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def run_seed(db: Session) -> None:
    """Drop all data and re-insert from JSON files. Deterministic every run."""

    print("  Seeding: creating tables if not exist…")
    Base.metadata.create_all(bind=engine)

    # Clear in reverse FK order
    print("  Seeding: clearing existing data…")
    db.query(ColdChainReading).delete()
    db.query(Shipment).delete()
    db.query(Disruption).delete()
    db.query(Carrier).delete()
    db.query(Fleet).delete()
    db.commit()

    # --- Disruptions ---
    disruptions_data = _load("disruptions.json")
    for d in disruptions_data:
        db.add(Disruption(
            id=d["id"],
            type=d["type"],
            title=d["title"],
            description=d["description"],
            severity=d["severity"],
            status=d["status"],
            affected_region=d["affected_region"],
            affected_routes=d["affected_routes"],
            latitude=d.get("latitude"),
            longitude=d.get("longitude"),
            started_at=_parse_dt(d["started_at"]),
            resolved_at=_parse_dt(d.get("resolved_at")),
            source=d["source"],
            created_at=_parse_dt(d["created_at"]),
        ))
    db.commit()
    print(f"  Seeded {len(disruptions_data)} disruptions.")

    # --- Carriers ---
    carriers_data = _load("carriers.json")
    for c in carriers_data:
        db.add(Carrier(
            id=c["id"],
            name=c["name"],
            code=c["code"],
            reliability_score=c["reliability_score"],
            speed_score=c["speed_score"],
            cost_index=c["cost_index"],
            active=c["active"],
            supported_route_types=c["supported_route_types"],
        ))
    db.commit()
    print(f"  Seeded {len(carriers_data)} carriers.")

    # --- Shipments ---
    shipments_data = _load("shipments.json")
    for s in shipments_data:
        db.add(Shipment(
            id=s["id"],
            tracking_number=s["tracking_number"],
            origin=s["origin"],
            destination=s["destination"],
            current_location=s["current_location"],
            route_id=s["route_id"],
            carrier_code=s["carrier_code"],
            status=s["status"],
            cargo_type=s["cargo_type"],
            cargo_description=s["cargo_description"],
            weight_kg=s["weight_kg"],
            value_usd=s["value_usd"],
            estimated_arrival=_parse_dt(s["estimated_arrival"]),
            actual_arrival=_parse_dt(s.get("actual_arrival")),
            disruption_id=s.get("disruption_id"),
            impact_score=s["impact_score"],
            created_at=_parse_dt(s["created_at"]),
        ))
    db.commit()
    print(f"  Seeded {len(shipments_data)} shipments.")

    # --- Fleet ---
    fleet_data = _load("fleet.json")
    for f in fleet_data:
        db.add(Fleet(
            id=f["id"],
            vehicle_id=f["vehicle_id"],
            vehicle_type=f["vehicle_type"],
            status=f["status"],
            current_location=f["current_location"],
            latitude=f.get("latitude"),
            longitude=f.get("longitude"),
            capacity_kg=f["capacity_kg"],
            available_capacity_kg=f["available_capacity_kg"],
            last_active_at=_parse_dt(f["last_active_at"]),
            idle_since=_parse_dt(f.get("idle_since")),
            assigned_route=f.get("assigned_route"),
            redeployable=f["redeployable"],
            redeployment_score=f["redeployment_score"],
        ))
    db.commit()
    print(f"  Seeded {len(fleet_data)} fleet vehicles.")

    # --- Cold-chain readings ---
    cold_chain_data = _load("cold_chain.json")
    for r in cold_chain_data:
        db.add(ColdChainReading(
            id=r["id"],
            shipment_id=r["shipment_id"],
            sensor_id=r["sensor_id"],
            recorded_at=_parse_dt(r["recorded_at"]),
            temperature_c=r["temperature_c"],
            humidity_pct=r.get("humidity_pct"),
            required_min_c=r["required_min_c"],
            required_max_c=r["required_max_c"],
            excursion=r["excursion"],
            excursion_duration_min=r.get("excursion_duration_min"),
            severity=r["severity"],
            severity_score=r["severity_score"],
            cargo_sensitivity=r["cargo_sensitivity"],
        ))
    db.commit()
    print(f"  Seeded {len(cold_chain_data)} cold-chain readings.")

    print("  Seed complete.")


if __name__ == "__main__":
    print("Running FLEETIQ seed script…")
    db = SessionLocal()
    try:
        run_seed(db)
    finally:
        db.close()
    print("Done.")
