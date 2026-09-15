# FLEETIQ — FastAPI Backend
# Phase 1: Minimal health-check entry point.
# Full implementation added in Phase 2 (models, seed, routers, services).

from fastapi import FastAPI

app = FastAPI(
    title="FLEETIQ API",
    description=(
        "AI-Powered Supply Chain Disruption & Fleet Utilisation Assistant. "
        "Identifies affected shipments, recommends rerouting, detects idle fleet, "
        "and severity-ranks cold-chain excursions."
    ),
    version="0.1.0",
)


@app.get("/health", tags=["Health"])
def health_check():
    """Liveness probe — confirms the API is running."""
    return {"status": "ok", "service": "FLEETIQ", "version": "0.1.0"}
