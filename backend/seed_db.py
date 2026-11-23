import sys
import os

# Add parent directory to path so app imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.seeder import seed_database

if __name__ == "__main__":
    with_appts = "--with-appointments" in sys.argv
    db = SessionLocal()
    try:
        seed_database(db, seed_appointments=with_appts)
        print("Database seeded successfully.")
    finally:
        db.close()
