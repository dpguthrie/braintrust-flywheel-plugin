"""Stable placeholder agent file for side-effect checks."""


SYSTEM_PROMPT = "Answer support questions using the approved support knowledge base."


def route(input_text: str) -> str:
    return "support_answer"
