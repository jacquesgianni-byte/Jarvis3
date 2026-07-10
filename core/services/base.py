"""
Jarvis Service Base Class

Every Jarvis service inherits from this class.
"""

from abc import ABC, abstractmethod


class Service(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Name of the service.
        """
        pass