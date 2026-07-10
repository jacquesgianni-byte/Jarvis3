"""
Jarvis Personality Service

Manages the active Jarvis personality.
"""

from core.services.base import Service


class PersonalityService(Service):

    def __init__(self):
        self._active = "Jarvis"

        self._personalities = {
            "Jarvis": {
                "description": "Professional, calm and intelligent."
            }
        }

    @property
    def name(self) -> str:
        return "personality"

    def get_active(self):
        """
        Return the active personality.
        """
        return self._active

    def set_active(self, name: str):
        """
        Set the active personality.
        """

        if name in self._personalities:
            self._active = name
            return True

        return False

    def list(self):
        """
        Return all available personalities.
        """
        return list(self._personalities.keys())