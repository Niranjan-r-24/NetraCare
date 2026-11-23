from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine, SessionLocal, ensure_schema_updates
from app.models import Doctor
from app.seeder import seed_database
from app.api import auth, doctors, slots, appointments, urgent_cases, facts, chat, staff
import logging

logger = logging.getLogger("netracare.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist and schema is updated
    ensure_schema_updates(engine)
    db = SessionLocal()
    try:
        doctor_count = db.query(Doctor).count()
        if doctor_count == 0:
            logger.info("Database appears empty. Seeding clinic master data...")
            seed_database(db, seed_appointments=False)
    finally:
        db.close()
    yield
    # Shutdown logic if any

app = FastAPI(
    title="NetraCare Clinic API",
    description="Agentic AI Clinic System - Iteration 2 LLM Integration Backend",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(doctors.router, prefix="/api/v1")
app.include_router(slots.router, prefix="/api/v1")
app.include_router(appointments.router, prefix="/api/v1")
app.include_router(urgent_cases.router, prefix="/api/v1")
app.include_router(facts.router, prefix="/api/v1")
app.include_router(chat.router)
app.include_router(staff.router)

@app.get("/health")
def health_check():
    return {"status": "ok", "iteration": 3, "app": "NetraCare"}

@app.get("/")
def root():
    return {
        "message": "Welcome to NetraCare Clinic API",
        "docs_url": "/docs",
        "health_url": "/health"
    }
