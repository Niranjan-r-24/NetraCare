from datetime import datetime, date, time
from typing import Optional
from app.config import settings

class ClockService:
    @staticmethod
    def now(override: Optional[datetime] = None) -> datetime:
        if override:
            return override
        if settings.CLINIC_TIME_OVERRIDE:
            try:
                # Expected format: 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD HH:MM'
                override_str = settings.CLINIC_TIME_OVERRIDE.strip()
                if len(override_str) == 16:
                    return datetime.strptime(override_str, "%Y-%m-%d %H:%M")
                return datetime.strptime(override_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        return datetime.now()

    @staticmethod
    def today() -> date:
        return ClockService.now().date()
