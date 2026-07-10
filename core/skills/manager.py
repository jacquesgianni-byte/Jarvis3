"""
Jarvis Skills Manager

Responsible for registering and executing skills.
"""

from core.models.response import Response
from core.skills.base import Skill


class SkillsManager:

    def __init__(self):
        self.skills = {}

    def register(self, skill: Skill):
        """
        Register a skill.
        """
        self.skills[skill.name] = skill

    def get(self, name: str):
        """
        Get a skill by name.
        """
        return self.skills.get(name)

    def execute(self, name: str, request: str) -> Response:
        """
        Execute a registered skill.
        """

        skill = self.get(name)

        if skill is None:
            return Response(
                success=False,
                message=f"Skill '{name}' is not registered."
            )

        result = skill.execute(request)

        if isinstance(result, Response):
            return result

        return Response(
            success=True,
            message=result
        )