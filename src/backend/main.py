"""
FLEETIQ — FastAPI application entry point.
Phase 3: Full backend with Phase 3 intelligence scoring on startup.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, SessionLocal, Base
from seed.seed_data import run_seed
from services.impact_analyzer import compute_impact_scores
from services.fleet_optimizer import score_idle_fleet
from services.cold_chain_ranker import rank_excursions
from routers import disruptions, shipments, fleet, cold_chain, carriers, summary


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    On startup:
    1. Create all tables (if not exist).
    2. Seed deterministic demo data.
    3. Run Phase 3 scoring algorithms to populate computed fields.
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Step 1 — seed
        run_seed(db)
        # Step 2 — impact scores
        n_impact = compute_impact_scores(db)
        print(f"  Phase 3: computed impact_score for {n_impact} shipments.")
        # Step 3 — fleet redeployment scores
        n_fleet = score_idle_fleet(db)
        print(f"  Phase 3: scored {n_fleet} idle fleet vehicles.")
        # Step 4 — cold-chain severity scores
        n_cc = rank_excursions(db)
        print(f"  Phase 3: ranked {n_cc} cold-chain excursions.")
    finally:
        db.close()
    yield
    # (shutdown logic would go here if needed)


app = FastAPI(
    title="FLEETIQ API",
    description=(
        "AI-Powered Supply Chain Disruption & Fleet Utilisation Assistant. "
        "Identifies affected shipments, recommends rerouting, detects idle fleet, "
        "and severity-ranks cold-chain excursions."
    ),
    version="0.3.0",
    lifespan=lifespan,
)

# --- CORS ---
_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(disruptions.router)
app.include_router(shipments.router)
app.include_router(fleet.router)
app.include_router(cold_chain.router)
app.include_router(carriers.router)
app.include_router(summary.router)


@app.get("/health", tags=["Health"])
def health_check():
    """Liveness probe — confirms the API is running."""
    return {"status": "ok", "service": "FLEETIQ", "version": "0.3.0"}


@app.post("/api/seed", tags=["Dev"])
def reseed_database():
    """Re-run the seed + scoring pipeline. Only available in development."""
    if os.getenv("APP_ENV", "development") != "development":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Seed endpoint disabled in production")
    db = SessionLocal()
    try:
        run_seed(db)
        compute_impact_scores(db)
        score_idle_fleet(db)
        rank_excursions(db)
    finally:
        db.close()
    return {"status": "reseeded"}
