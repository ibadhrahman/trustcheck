"""
TrustCheck application configuration.
Loads settings from environment variables / .env file.
"""
from __future__ import annotations

import secrets
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Security
    secret_key: str = secrets.token_hex(32)
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"

    # Database
    database_url: str = "sqlite:///./trustcheck.db"

    # App
    app_env: str = "development"
    debug: bool = True
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    # Upload
    max_upload_size_mb: int = 5
    private_upload_dir: str = "private_uploads"

    # Buyer order outcomes
    order_issue_response_hours: int = Field(default=48, ge=1, le=720)
    order_issue_warning_threshold: int = Field(default=3, ge=2, le=3)
    order_issue_warning_window_days: int = Field(default=30, ge=1, le=365)

    # Duplicate detection
    phash_similarity_threshold: int = 10
    duplicate_window_hours: int = 168

    # OCR
    ocr_engine: str = "auto"

    # HMAC for tx reference fingerprinting
    hmac_secret: str = secrets.token_hex(32)

    # DeepSeek Multimodal AI
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4.1-flash"
    deepseek_enabled: bool = True
    deepseek_timeout_seconds: int = 30
    deepseek_max_retries: int = 0

    # Gemini Multimodal AI (Optional)
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_enabled: bool = True
    gemini_timeout_seconds: int = 15
    gemini_max_retries: int = 0

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


settings = Settings()
