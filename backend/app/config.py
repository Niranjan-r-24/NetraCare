from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path
import os

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/netracare"
    SQLITE_FALLBACK_URL: str = "sqlite:///./netracare.db"
    AUTO_FALLBACK_TO_SQLITE: bool = True
    CLINIC_TIME_OVERRIDE: Optional[str] = None
    DATA_DIR: Optional[str] = None
    DATA_DIR_ITER2: Optional[str] = None
    DATA_DIR_ITER3: Optional[str] = None
    CHROMA_PERSIST_DIR: str = "chroma_db"
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    @property
    def resolved_data_dir(self) -> Path:
        if self.DATA_DIR:
            p = Path(self.DATA_DIR)
            if p.is_absolute() and p.exists():
                return p
            # Check relative to backend or project root
            for candidate in [
                p,
                Path(__file__).resolve().parent.parent / p,
                Path(__file__).resolve().parent.parent.parent / p,
                Path(__file__).resolve().parent.parent.parent / "docs" / "data"
            ]:
                if candidate.exists():
                    return candidate.resolve()
        return (Path(__file__).resolve().parent.parent.parent / "docs" / "data").resolve()

    @property
    def resolved_iter2_data_dir(self) -> Path:
        if self.DATA_DIR_ITER2:
            p = Path(self.DATA_DIR_ITER2)
            if p.is_absolute() and p.exists():
                return p
            for candidate in [
                p,
                Path(__file__).resolve().parent.parent / p,
                Path(__file__).resolve().parent.parent.parent / p,
                Path(__file__).resolve().parent.parent.parent / "docs" / "iteration-2" / "data"
            ]:
                if candidate.exists():
                    return candidate.resolve()
        return (Path(__file__).resolve().parent.parent.parent / "docs" / "iteration-2" / "data").resolve()

    @property
    def resolved_iter3_data_dir(self) -> Path:
        if self.DATA_DIR_ITER3:
            p = Path(self.DATA_DIR_ITER3)
            if p.is_absolute() and p.exists():
                return p
            for candidate in [
                p,
                Path(__file__).resolve().parent.parent / p,
                Path(__file__).resolve().parent.parent.parent / p,
                Path(__file__).resolve().parent.parent.parent / "docs" / "iteration-3" / "data"
            ]:
                if candidate.exists():
                    return candidate.resolve()
        return (Path(__file__).resolve().parent.parent.parent / "docs" / "iteration-3" / "data").resolve()

    @property
    def resolved_chroma_dir(self) -> Path:
        p = Path(self.CHROMA_PERSIST_DIR)
        if p.is_absolute():
            return p
        return (Path(__file__).resolve().parent.parent / p).resolve()


    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
