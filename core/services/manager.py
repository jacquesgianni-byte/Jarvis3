"""
Jarvis Service Manager

Responsible for registering and retrieving services.
"""

from core.services.base import Service


class ServiceManager:

    def __init__(self):
        self.services = {}

    def register(self, service: Service):
        """
        Register a service.
        """
        self.services[service.name] = service

    def get(self, name: str):
        """
        Get a registered service.
        """
        return self.services.get(name)

    def list(self):
        """
        Return all registered services.
        """
        return list(self.services.values())