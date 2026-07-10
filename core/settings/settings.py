"""
Jarvis Runtime Settings

Contains runtime settings used by Jarvis.
"""

from dataclasses import dataclass


@dataclass
class Settings:
    """
    Runtime settings for Jarvis.
    """

    # OpenAI
    openai_api_key: str = "***REMOVED***"
    default_model: str = "gpt-5"

    # AI
    default_ai_provider: str = "openai"

    # Voice
    voice_enabled: bool = True

    # Memory
    memory_enabled: bool = True

    # Assistant
    assistant_name: str = "Jarvis"
    personality: str = "Friendly"
    language: str = "English"