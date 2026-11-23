import os
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root and backend to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

EVAL_DB_FILE = ROOT / "evals" / "eval_netracare.db"
EVAL_DB_URL = f"sqlite:///{EVAL_DB_FILE.resolve()}"

# Mandatory safeguard: Never allow evals to touch netracare.db
assert "netracare.db" not in str(EVAL_DB_URL).replace("eval_netracare.db", ""), (
    "FATAL SAFETY VIOLATION: Evals must never point to netracare.db!"
)

# Set environment overrides
os.environ["DATABASE_URL"] = EVAL_DB_URL
os.environ["SQLITE_FALLBACK_URL"] = EVAL_DB_URL
os.environ["CLINIC_TIME_OVERRIDE"] = "2026-11-02 10:00"

# Dedicated evaluation engine and session factory
eval_engine = create_engine(
    EVAL_DB_URL,
    connect_args={"check_same_thread": False}
)
EvalSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=eval_engine)

from app.database import Base, ensure_schema_updates
from app.models import Appointment, UrgentCase, StaffApproval
from app.seeder import seed_database
import app.database

# Patch active app database globals in memory to strictly isolate evals
app.database.engine = eval_engine
app.database.SessionLocal = EvalSessionLocal


def get_eval_db():
    """Context manager / generator for eval db sessions."""
    db = EvalSessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_eval_db():
    """
    Completely re-seeds eval_netracare.db from scratch before every booking scenario.
    Clears all active appointments, urgent cases, and staff approvals, then re-seeds.
    """
    Base.metadata.create_all(bind=eval_engine)
    ensure_schema_updates(eval_engine)

    db = EvalSessionLocal()
    try:
        db.query(StaffApproval).delete()
        db.query(UrgentCase).delete()
        db.query(Appointment).delete()
        db.commit()

        seed_database(db, seed_appointments=True)
    finally:
        db.close()
