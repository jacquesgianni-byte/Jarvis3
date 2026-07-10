"""
Jarvis Greeting Skill
"""

from core.models.response import Response
from core.skills.base import Skill


class GreetingSkill(Skill):
    """
    Handles greeting requests.
    """

    @property
    def name(self) -> str:
        return "greeting"

    def execute(self, request: str) -> Response:
        """
        Execute the greeting skill.
        """

        return Response(
            message="Hello! How can I help you today?"
        )