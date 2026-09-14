from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, automations, billing, ingest, leads, presets, profile, team, imports, integrations, outreach
from app.config import settings
from app.services.superuser import ensure_local_superuser
from app.db import Base, SessionLocal, engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # MVP bootstrap. Replace create_all with Alembic migrations before production.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_local_superuser(db)
    yield

app = FastAPI(
    title=f"{settings.app_name} API",
    version="0.6.4",
    lifespan=lifespan,
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")
app.include_router(automations.router, prefix="/api/v1")
app.include_router(ingest.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(team.router, prefix="/api/v1")
app.include_router(imports.router, prefix="/api/v1")
app.include_router(integrations.router, prefix="/api/v1")
app.include_router(outreach.router, prefix="/api/v1")
app.include_router(outreach.agent_router, prefix="/api/v1")
app.include_router(leads.router, prefix="/api/v1")
app.include_router(profile.router, prefix="/api/v1")
app.include_router(presets.router, prefix="/api/v1")

STATIC_DIR = Path(__file__).resolve().parent / "static"
ADMIN_STATIC_DIR = Path(__file__).resolve().parent / "admin_static"
app.mount("/dashboard", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
app.mount("/admin", StaticFiles(directory=ADMIN_STATIC_DIR, html=True), name="admin-ui")

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard/")

@app.get("/health")
def health():
    return {"ok": True, "version": "0.6.4"}
