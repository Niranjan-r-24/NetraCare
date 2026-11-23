import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

logger = logging.getLogger("netracare.database")
logging.basicConfig(level=logging.INFO)

Base = declarative_base()

def get_engine():
    # Attempt primary database connection
    pg_url = settings.DATABASE_URL
    try:
        logger.info(f"Attempting connection to primary database: {pg_url.split('@')[-1] if '@' in pg_url else pg_url}")
        connect_args = {}
        if pg_url.startswith("postgresql"):
            connect_args = {"connect_timeout": 3}
        elif pg_url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
        test_engine = create_engine(pg_url, pool_pre_ping=True, connect_args=connect_args)
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Successfully connected to primary database.")
        return test_engine
    except Exception as exc:
        if settings.AUTO_FALLBACK_TO_SQLITE:
            logger.warning(
                f"Primary database connection failed: {exc}. "
                f"Falling back to SQLite at {settings.SQLITE_FALLBACK_URL}"
            )
            return create_engine(
                settings.SQLITE_FALLBACK_URL,
                connect_args={"check_same_thread": False}
            )
        else:
            raise exc

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def ensure_schema_updates(target_engine=None):
    if target_engine is None:
        target_engine = engine
    Base.metadata.create_all(bind=target_engine)
    try:
        inspector = inspect(target_engine)
        tables = inspector.get_table_names()

        with target_engine.connect() as conn:
            if "patients" in tables:
                patient_cols = [c["name"] for c in inspector.get_columns("patients")]
                if "general_health" not in patient_cols:
                    conn.execute(text("ALTER TABLE patients ADD COLUMN general_health VARCHAR(255) DEFAULT 'None recorded'"))
                if "allergies" not in patient_cols:
                    conn.execute(text("ALTER TABLE patients ADD COLUMN allergies VARCHAR(255) DEFAULT 'None known'"))
                conn.commit()

            if "appointments" in tables:
                appt_cols = [c["name"] for c in inspector.get_columns("appointments")]
                if "reason" not in appt_cols:
                    conn.execute(text("ALTER TABLE appointments ADD COLUMN reason VARCHAR(300)"))
                if "doctor_note" not in appt_cols:
                    conn.execute(text("ALTER TABLE appointments ADD COLUMN doctor_note TEXT"))
                if "is_urgent" not in appt_cols:
                    conn.execute(text("ALTER TABLE appointments ADD COLUMN is_urgent BOOLEAN DEFAULT 0"))
                if "source" not in appt_cols:
                    conn.execute(text("ALTER TABLE appointments ADD COLUMN source VARCHAR(20) DEFAULT 'Website'"))
                if "intake_notes" not in appt_cols:
                    conn.execute(text("ALTER TABLE appointments ADD COLUMN intake_notes TEXT"))
                conn.commit()

            if "urgent_cases" in tables:
                urgent_cols = [c["name"] for c in inspector.get_columns("urgent_cases")]
                if "source" not in urgent_cols:
                    conn.execute(text("ALTER TABLE urgent_cases ADD COLUMN source VARCHAR(20) DEFAULT 'Appointment'"))
                conn.commit()
    except Exception as e:
        logger.warning(f"Schema update notice: {e}")

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
