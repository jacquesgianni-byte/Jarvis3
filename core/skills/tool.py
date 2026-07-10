"""
Jarvis Tool Skill

Handles execution of Jarvis tools.
"""

from core.models.response import Response
from core.skills.base import Skill


class ToolSkill(Skill):
    """
    Handles execution of Jarvis tools.
    """

    def __init__(self, tools):
        self.tools = tools

    @property
    def name(self) -> str:
        return "tool"

    def execute(self, request: str) -> Response:
        """
        Execute the tool skill.
        """

        result = self.tools.run("hello")

        return Response(
            message=result
        )