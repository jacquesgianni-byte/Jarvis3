"""
Jarvis Runtime Settings

Contains runtime settings used by Jarvis.

Genesis-014 Task 001 — secure runtime configuration:

  * ROOT CAUSE FIX: environment-backed fields previously used
    os.getenv(...) directly as dataclass defaults, which Python
    evaluates ONCE at class definition (import) time. Because Jarvis's
    import chain runs before load_dotenv(), the defaults froze as empty
    strings. Fields now use field(default_factory=...), evaluated at
    INSTANCE creation — every Settings() call reads the live environment.

  * IMPORT-ORDER IMMUNITY: this module calls load_dotenv() itself,
    before the class is defined. python-dotenv is idempotent, never
    overrides real environment variables, and no-ops if .env is absent.
    Safe for both development (.env) and production (real env vars).

  * FIELD NAMES UNCHANGED: default_model is kept as-is; the frozen
    OpenAIProvider reads self.settings.default_model throughout and must
    not be touched (Genesis-013 frozen). anthropic_model is added
    alongside it for the future ClaudeProvider.

  * No secrets are ever hardcoded in this file.
"""

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Settings:
    """
    Runtime settings for Jarvis.

    Environment-backed fields are evaluated at instance creation via
    default_factory — never at import time.
    """

    # ==========================
    # OpenAI
    # ==========================
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    default_model: str = "gpt-5"          # name unchanged — OpenAIProvider reads this

    # reasoning_effort controls how much hidden reasoning GPT-5 / o-series
    # models apply before writing a reply. 'high' (the model default) burns
    # the entire token budget on thinking and returns an empty completion for
    # conversational queries. 'low' produces fast, correct responses suitable
    # for a voice assistant. Override in .env: REASONING_EFFORT=medium|high
    reasoning_effort: str = field(
        default_factory=lambda: os.getenv("REASONING_EFFORT", "low")
    )

    # ==========================
    # Engineering
    # ==========================

    # Maximum files a single engineering task may modify before the
    # guardrail rejects it. Override in .env: ENGINEERING_MAX_FILES=10
    engineering_max_files: int = field(
        default_factory=lambda: int(os.getenv("ENGINEERING_MAX_FILES", "5"))
    )

    # ==========================
    # Anthropic
    # ==========================
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    anthropic_model: str = "claude-sonnet-4-6"   # corrected model string

    # ==========================
    # AI
    # ==========================
    default_ai_provider: str = "openai"

    # ==========================
    # Voice
    # ==========================
    voice_enabled: bool = True

    # ==========================
    # Memory
    # ==========================
    memory_enabled: bool = True

    # ==========================
    # Assistant
    # ==========================
    assistant_name: str = "Jarvis"
    personality: str = "Friendly"
    language: str = "English"