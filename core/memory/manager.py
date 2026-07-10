"""
Jarvis Memory Manager

Handles Jarvis memory.
"""


class MemoryManager:

    def __init__(self):
        self._memory = {}

    def remember(self, key, value):
        self._memory[key] = value

    def recall(self, key):
        return self._memory.get(key)

    def forget(self, key):
        self._memory.pop(key, None)