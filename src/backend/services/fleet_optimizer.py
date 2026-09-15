"""
fleet_optimizer — Phase 3 stub.
Scores idle fleet vehicles for redeployment suitability.
Full Haversine + capacity matching algorithm in Phase 3.
"""


def score_idle_fleet(db) -> None:
    """
    Phase 3 will compute redeployment_score using:
      - Haversine proximity to disrupted route origin
      - available_capacity_kg vs stranded shipment weight
      - vehicle_type match
    and update Fleet.redeployable / Fleet.redeployment_score in DB.
    """
    pass
