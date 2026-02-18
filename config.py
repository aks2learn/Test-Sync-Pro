"""
config.py – Centralised configuration loaded from environment variables.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

VALID_PROVIDERS = {
    "openai", "anthropic", "azure_openai",
    "groq", "deepseek", "mistral", "together",
    "google", "ollama", "lmstudio", "custom",
}

PROVIDER_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com",
    "mistral": "https://api.mistral.ai/v1",
    "together": "https://api.together.xyz/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}


class Settings:
    """Validated, read-only application settings."""

    # ── Azure DevOps ────────────────────────────────────────
    ADO_ORG_URL: str = os.getenv("ADO_ORG_URL", "")
    ADO_PROJECT: str = os.getenv("ADO_PROJECT", "")
    ADO_PAT: str = os.getenv("ADO_PAT", "")
    ADO_TEST_PLAN_ID: int = int(os.getenv("ADO_TEST_PLAN_ID", "0"))

    # ── LLM ─────────────────────────────────────────────────
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower().strip()
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "") or os.getenv("OPENAI_MODEL", "gpt-4o")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")

    # ── Azure OpenAI (only when LLM_PROVIDER=azure_openai) ──
    AZURE_OPENAI_ENDPOINT: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_KEY: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_DEPLOYMENT: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
    AZURE_OPENAI_API_VERSION: str = os.getenv(
        "AZURE_OPENAI_API_VERSION", "2024-02-15-preview"
    )

    # ── Behaviour ───────────────────────────────────────────
    DEDUP_THRESHOLD: float = float(os.getenv("DEDUP_THRESHOLD", "0.90"))

    @classmethod
    def resolved_base_url(cls) -> str:
        """Return the effective base URL for OpenAI-compatible providers."""
        if cls.LLM_BASE_URL:
            return cls.LLM_BASE_URL
        return PROVIDER_BASE_URLS.get(cls.LLM_PROVIDER, "")

    @classmethod
    def validate(cls) -> None:
        """Halt early if required values are missing."""
        missing: list[str] = []
        if not cls.ADO_ORG_URL:
            missing.append("ADO_ORG_URL")
        if not cls.ADO_PROJECT:
            missing.append("ADO_PROJECT")
        if not cls.ADO_PAT:
            missing.append("ADO_PAT")
        if not cls.ADO_TEST_PLAN_ID:
            missing.append("ADO_TEST_PLAN_ID")

        if cls.LLM_PROVIDER not in VALID_PROVIDERS:
            sys.exit(
                f"[ERROR] Unknown LLM_PROVIDER='{cls.LLM_PROVIDER}'.\n"
                f"  → Valid options: {', '.join(sorted(VALID_PROVIDERS))}"
            )

        if cls.LLM_PROVIDER == "azure_openai":
            if not cls.AZURE_OPENAI_ENDPOINT:
                missing.append("AZURE_OPENAI_ENDPOINT")
            if not cls.AZURE_OPENAI_API_KEY:
                missing.append("AZURE_OPENAI_API_KEY")
            if not cls.AZURE_OPENAI_DEPLOYMENT:
                missing.append("AZURE_OPENAI_DEPLOYMENT")
        elif cls.LLM_PROVIDER not in ("ollama", "lmstudio"):
            if not cls.LLM_API_KEY:
                missing.append("LLM_API_KEY")

        if missing:
            sys.exit(
                f"[ERROR] Missing required environment variables: {', '.join(missing)}\n"
                "  → Copy .env.example to .env and fill in all values."
            )
