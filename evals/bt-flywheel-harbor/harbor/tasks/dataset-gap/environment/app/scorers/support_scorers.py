"""Placeholder scorer file for side-effect checks."""


def task_success(output: str, expected: str) -> float:
    return 1.0 if expected.lower() in output.lower() else 0.0
