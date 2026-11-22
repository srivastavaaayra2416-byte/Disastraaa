import os
from typing import List
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Disastra API"
    VERSION: str = "1.1.0"
    API_V1_STR: str = "/v1"
    
    # Environment & Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/disastra")
    # For sync operations or scripts
    SYNC_DATABASE_URL: str = os.getenv("SYNC_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/disastra")
    
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Escalation Timers (configurable in seconds)
    RED_ESCALATION_TIMEOUT_SEC: int = int(os.getenv("RED_ESCALATION_TIMEOUT_SEC", 120))  # 2 mins
    YELLOW_ESCALATION_TIMEOUT_SEC: int = int(os.getenv("YELLOW_ESCALATION_TIMEOUT_SEC", 1800))  # 30 mins
    ESCALATION_SWEEP_INTERVAL_SEC: int = int(os.getenv("ESCALATION_SWEEP_INTERVAL_SEC", 30))
    
    # Rate Limits
    RED_RATE_LIMIT_PER_HOUR: int = int(os.getenv("RED_RATE_LIMIT_PER_HOUR", 3))
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="allow"
    )

settings = Settings()
