"""
Jarvis Exit Skill

Handles requests to exit Jarvis.
"""

from core.models.response import Response
from core.skills.base import Skill


class ExitSkill(Skill):
    """
    Handles exit requests.
    """

    @property
    def name(self) -> str:
        return "exit"

    def execute(self, request: str) -> Response:
        """
        Execute the exit skill.
        """

        return Response(
            message="Goodbye, Ludovic.",
            action="EXIT"
        )