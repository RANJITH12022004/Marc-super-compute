"""fake_mic.py - replayable fake microphone lines for demos."""

DEMO = [
    "Hey Marc",
    "Text Amma I'll be home by 8, play the driving playlist, and email the hackathon recap to myself",
    "yes",
    "Open VS Code on my laptop and type the demo notes",
    "stop Marc",
]


def replay():
    """Yield each line in DEMO in order."""
    for line in DEMO:
        yield line
