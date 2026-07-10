class MemoryManager:

    def __init__(self):
        self.history = []

    def remember(self, message):
        self.history.append(message)

    def recall(self):
        return self.history