"""
Jarvis Identity Skill

Handles identity-related questions.
"""

from core.models.response import Response
from core.skills.base import Skill


class IdentitySkill(Skill):
    """
    Handles identity-related requests.
    """

    @property
    def name(self) -> str:
        return "identity"

    def execute(self, request: str) -> Response:
        """
        Execute the identity skill.
        """

        request = request.lower()

        if "my name" in request:
            return Response(
                message="Your name is Ludovic."
            )

        return Response(
            message="My name is Jarvis."
        )