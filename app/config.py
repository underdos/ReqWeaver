"""ReqWeaver Configuration — loads settings from environment variables."""
from __future__ import annotations
import os
from functools import lru_cache


class Settings:
    """Application settings loaded from environment variables."""
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_TIMEOUT: int = int(os.getenv("OPENAI_TIMEOUT", "120"))
    
    # App
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./reqweaver.db")
    
    @property
    def ai_available(self) -> bool:
        """Whether AI generation is available (API key configured)."""
        return bool(self.OPENAI_API_KEY)


@lru_cache()
def get_settings() -> Settings:
    return Settings()
