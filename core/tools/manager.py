"""
Jarvis Tool Manager

Registers and executes tools.
"""


class ToolManager:

    def __init__(self):
        self._tools = {}

    def register(self, name, tool):
        self._tools[name] = tool

    def run(self, name, *args, **kwargs):

        if name not in self._tools:
            return f"Tool '{name}' not found."

        return self._tools[name](*args, **kwargs)