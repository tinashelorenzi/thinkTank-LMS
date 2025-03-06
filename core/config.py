import os
from pydantic import BaseSettings, PostgresDsn, validator
from typing import Optional, Dict, Any, List


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    
    These settings can be overridden by setting environment variables
    with the same name (prefixed with LMS_).
    
    Example:
        LMS_SECRET_KEY=mysecretkey
        LMS_DATABASE_URL=postgres://user:pass@localhost:5432/lms
    """
    
    # Base
    PROJECT_NAME: str = "Canvas-like LMS"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False
    
    # Security
    SECRET_KEY: str = "CHANGE_THIS_TO_A_SECURE_SECRET"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost", "http://localhost:8000", "http://localhost:3000"]
    
    # Database
    DATABASE_URL: Optional[PostgresDsn] = None
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "lms_db"
    
    @validator("DATABASE_URL", pre=True)
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgres",
            user=values.get("DB_USER"),
            password=values.get("DB_PASSWORD"),
            host=values.get("DB_HOST"),
            port=values.get("DB_PORT"),
            path=f"/{values.get('DB_NAME') or ''}",
        )
    
    # Email settings
    SMTP_TLS: bool = True
    SMTP_PORT: Optional[int] = 587
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[str] = None
    EMAILS_FROM_NAME: Optional[str] = None

    # File storage
    STORAGE_TYPE: str = "local"  # local, s3, azure, gcp
    STORAGE_ROOT: str = "media"
    S3_BUCKET: Optional[str] = None
    S3_REGION: Optional[str] = None
    S3_ACCESS_KEY: Optional[str] = None
    S3_SECRET_KEY: Optional[str] = None
    
    # Admin settings
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "CHANGE_THIS_ADMIN_PASSWORD"
    
    # Other settings
    TIME_ZONE: str = "UTC"
    DEFAULT_LANGUAGE: str = "en"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "LMS_"
        case_sensitive = True


settings = Settings()