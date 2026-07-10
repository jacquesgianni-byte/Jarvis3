def get_intent(question):
    question = question.lower()

    if "weather" in question:
        return "WEATHER"

    if "time" in question:
        return "TIME"

    if "hello" in question:
        return "GREETING"

    return "CHAT"