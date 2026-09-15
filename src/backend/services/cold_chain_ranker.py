"""
cold_chain_ranker — Phase 3 stub.
Computes severity_score for each ColdChainReading excursion.
Full severity band algorithm in Phase 3.
"""


def rank_excursions(db) -> None:
    """
    Phase 3 will compute severity_score = (magnitude * 5) + (duration_min / 10),
    capped at 100, and assign severity bands:
      critical  — magnitude > 10°C OR duration > 240 min
      severe    — magnitude 5–10°C OR duration 120–240 min
      moderate  — magnitude 2–5°C OR duration 60–120 min
      minor     — magnitude < 2°C AND duration < 60 min
    """
    pass
