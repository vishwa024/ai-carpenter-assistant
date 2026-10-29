"""Application configuration loader for AI Carpenter Assistant.

Supports loading environment variables from system environment and local .env file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def load_dotenv(dotenv_path: Optional[Path] = None) -> None:
    """Lightweight built-in .env parser to avoid strict external dependencies."""
    if dotenv_path is None:
        # Search current working dir, project root, and script dir
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent.parent / ".env",
            Path(__file__).resolve().parent / ".env",
        ]
        for candidate in candidates:
            if candidate.is_file():
                dotenv_path = candidate
                break

    if not dotenv_path or not dotenv_path.is_file():
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    # Do not overwrite already set environment variables
                    if key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass


# Load .env upon module import
load_dotenv()


@dataclass(frozen=True)
class Config:
    """Runtime configuration settings."""

    # Server settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    CHANNEL: str = os.getenv("CHANNEL", "web").lower()  # 'whatsapp' or 'web'

    # Gemini API settings
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Meta WhatsApp Cloud API settings
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "carpenter_secret_verify_2026")
    WHATSAPP_APP_SECRET: str = os.getenv("WHATSAPP_APP_SECRET", "")

    # WhatsApp Web Direct Access settings
    WHATSAPP_WEB_URL: str = os.getenv("WHATSAPP_WEB_URL", "https://web.whatsapp.com")

    # Workshop Metadata
    WORKSHOP_NAME: str = os.getenv("WORKSHOP_NAME", "Heritage Woodworks & Joinery")
    CARPENTER_NAME: str = os.getenv("CARPENTER_NAME", "Rajesh Sharma")

    @property
    def is_whatsapp_configured(self) -> bool:
        """Check if production WhatsApp Cloud API credentials are provided."""
        return bool(self.WHATSAPP_TOKEN and self.WHATSAPP_PHONE_NUMBER_ID)

    @property
    def is_gemini_configured(self) -> bool:
        """Check if Gemini API Key is configured."""
        return bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY != "your_gemini_api_key")

    @property
    def is_app_secret_configured(self) -> bool:
        """Check if WhatsApp App Secret is set for signature validation."""
        return bool(self.WHATSAPP_APP_SECRET and self.WHATSAPP_APP_SECRET != "your_meta_app_secret")


# Singleton instance
config = Config()