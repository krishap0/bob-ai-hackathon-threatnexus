"""
disruption_engine — Phase 3 stub.
Detects active disruptions and identifies affected shipments.
Full implementation in Phase 3.
"""


def detect_active_disruptions(db) -> list:
    """Return all active disruptions. Phase 3 will add scoring logic."""
    from models import Disruption
    return db.query(Disruption).filter(Disruption.status == "active").all()
