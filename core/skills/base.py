"""
Jarvis Skill Base Class

Every Jarvis skill inherits from this class.
"""

from abc import ABC, abstractmethod


class Skill(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Name of the skill.
        """
        pass

    @abstractmethod
    def execute(self, request: str):
        """
        Execute the skill.
        """
        pass