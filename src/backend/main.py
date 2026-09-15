"""
FLEETIQ — FastAPI application entry point.
Phase 2: Full backend foundation with database, routers, and seeding.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, SessionLocal, Base
from seed.seed_data import run_seed
from routers import disruptions, shipments, fleet, cold_chain, carriers, summary


@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup: create tables and seed demo data."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run_seed(db)
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
    version="0.2.0",
    lifespan=lifespan,
)

# --- CORS ---
# Allow the Vite dev server (port 5173) and any localhost origin during development.
_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",  # fallback if dev port changes
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


# --- Health check ---
@app.get("/health", tags=["Health"])
def health_check():
    """Liveness probe — confirms the API is running."""
    return {"status": "ok", "service": "FLEETIQ", "version": "0.2.0"}


# --- Dev-only seed endpoint ---
@app.post("/api/seed", tags=["Dev"])
def reseed_database():
    """Re-run the seed script. Only available when APP_ENV=development."""
    if os.getenv("APP_ENV", "development") != "development":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Seed endpoint disabled in production")
    db = SessionLocal()
    try:
        run_seed(db)
    finally:
        db.close()
    return {"status": "reseeded"}
