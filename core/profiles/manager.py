"""
from core.constants import (
    LANG_ENGLISH,
    VOICE_MALE,
    PERSONALITY_FRIENDLY,
)
Jarvis Profile Manager

Manages user profiles and the active user.
"""

from dataclasses import dataclass


@dataclass
class UserProfile:
    name: str
    language: str = "English"
    voice: str = "Male"
    personality: str = "Friendly"
    developer_mode: bool = False


class ProfileManager:

    def __init__(self):
        self._profiles = {}
        self._active = None

    def add_profile(self, profile: UserProfile):
        self._profiles[profile.name] = profile

    def set_active(self, name):
        if name in self._profiles:
            self._active = self._profiles[name]

    def active_profile(self):
        return self._active