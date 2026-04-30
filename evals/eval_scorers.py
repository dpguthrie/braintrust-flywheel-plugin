"""
Offline unit tests for the four deterministic bt-flywheel scorer functions.

Each test case is a fixture span sequence paired with an expected score range.
Scorer functions are imported from scorers/_scoring.py — no Braintrust registration occurs.

Run:
    cd /path/to/flywheel-plugin
    BRAINTRUST_API_KEY=... braintrust eval evals/eval_scorers.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scorers"))

import braintrust
from _scoring import (
    score_claimed_vs_actual,
    score_evidence_before_change,
    score_run_efficiency,
    score_smoke_test_discipline,
)

_PROJECT = os.getenv("BRAINTRUST_EVAL_PROJECT", "bt-flywheel")


# ─── Mock span ────────────────────────────────────────────────────────────────


class _Span:
    """Minimal mock satisfying the _span_name / _span_input / _span_start interface."""

    def __init__(
        self,
        name: str,
        command: str | None = None,
        start: float = 0.0,
        content: str | None = None,
    ):
        self.span_attributes = {"name": name}
        self.input: dict = {}
        if command is not None:
            self.input["command"] = command
        if content is not None:
            self.input["content"] = content
        self.metrics = type("M", (), {"start": start})()


def _build_spans(raw: list[dict]) -> list[_Span]:
    return [
        _Span(
            name=d["name"],
            command=d.get("command"),
            start=d.get("start", 0.0),
            content=d.get("content"),
        )
        for d in raw
    ]


# ─── Dataset ──────────────────────────────────────────────────────────────────
#
# span dict keys: name (required), command, start, content (all optional)
# Summary content uses a "Bash: write bt-flywheel-summary.json" span so it is
# detectable by _extract_summary_text but NOT matched by the Edit/Write regex.

_DATASET = [
    # ── Evidence Before Change ────────────────────────────────────────────────
    {
        "input": {
            "scorer": "evidence_before_change",
            "label": "bt sql before edit → 1.0",
            "spans": [
                {"name": "Bash: bt sql SELECT ...", "command": "bt sql SELECT count(*) FROM project_logs", "start": 1.0},
                {"name": "Edit: src/agent.py", "start": 2.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },
    {
        "input": {
            "scorer": "evidence_before_change",
            "label": "bt view before edit → 1.0",
            "spans": [
                {"name": "Bash: bt view exp-123", "command": "bt view exp-123 --limit 20", "start": 1.0},
                {"name": "Edit: src/agent.py", "start": 2.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },
    {
        "input": {
            "scorer": "evidence_before_change",
            "label": "one bt sql before two edits → 1.0 (evidence is cumulative)",
            "spans": [
                {"name": "Bash: bt sql SELECT ...", "command": "bt sql SELECT ...", "start": 1.0},
                {"name": "Edit: src/agent.py", "start": 2.0},
                {"name": "Edit: evals/eval_agent.py", "start": 3.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },
    {
        "input": {
            "scorer": "evidence_before_change",
            "label": "edit with no preceding evidence → 0.0",
            "spans": [
                {"name": "Edit: src/agent.py", "start": 1.0},
            ],
        },
        "expected": {"min": 0.0, "max": 0.0},
    },
    {
        "input": {
            "scorer": "evidence_before_change",
            "label": "Read (not bt sql/view) before edit → 0.0",
            "spans": [
                {"name": "Read: src/agent.py", "start": 1.0},
                {"name": "Edit: src/agent.py", "start": 2.0},
            ],
        },
        "expected": {"min": 0.0, "max": 0.0},
    },
    {
        "input": {
            "scorer": "evidence_before_change",
            "label": "evidence before second edit only → 0.5",
            "spans": [
                {"name": "Edit: src/agent.py", "start": 1.0},
                {"name": "Bash: bt sql SELECT ...", "command": "bt sql SELECT ...", "start": 2.0},
                {"name": "Edit: evals/eval_agent.py", "start": 3.0},
            ],
        },
        "expected": {"min": 0.45, "max": 0.55},
    },
    {
        "input": {
            "scorer": "evidence_before_change",
            "label": "evidence but no edits → 1.0",
            "spans": [
                {"name": "Bash: bt sql SELECT ...", "command": "bt sql SELECT ...", "start": 1.0},
                {"name": "Read: src/agent.py", "start": 2.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },

    # ── Smoke Test Discipline ─────────────────────────────────────────────────
    {
        "input": {
            "scorer": "smoke_test_discipline",
            "label": "smoke then full → 1.0",
            "spans": [
                {"name": "Bash: bt eval evals/eval.py --first 20", "command": "bt eval evals/eval.py --first 20", "start": 1.0},
                {"name": "Bash: bt eval evals/eval.py", "command": "bt eval evals/eval.py", "start": 2.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },
    {
        "input": {
            "scorer": "smoke_test_discipline",
            "label": "smoke only → 1.0",
            "spans": [
                {"name": "Bash: bt eval evals/eval.py --first 5", "command": "bt eval evals/eval.py --first 5", "start": 1.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },
    {
        "input": {
            "scorer": "smoke_test_discipline",
            "label": "no eval runs → 1.0",
            "spans": [
                {"name": "Read: evals/eval_agent.py", "start": 1.0},
                {"name": "Edit: src/agent.py", "start": 2.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },
    {
        "input": {
            "scorer": "smoke_test_discipline",
            "label": "full eval, no smoke → 0.4",
            "spans": [
                {"name": "Bash: bt eval evals/eval.py", "command": "bt eval evals/eval.py", "start": 1.0},
            ],
        },
        "expected": {"min": 0.35, "max": 0.45},
    },
    {
        "input": {
            "scorer": "smoke_test_discipline",
            "label": "full before smoke (wrong order) → 0.2",
            "spans": [
                {"name": "Bash: bt eval evals/eval.py", "command": "bt eval evals/eval.py", "start": 1.0},
                {"name": "Bash: bt eval evals/eval.py --first 20", "command": "bt eval evals/eval.py --first 20", "start": 2.0},
            ],
        },
        "expected": {"min": 0.1, "max": 0.3},
    },

    # ── Run Efficiency ────────────────────────────────────────────────────────
    {
        "input": {
            "scorer": "run_efficiency",
            "label": "all unique commands → 1.0",
            "spans": [
                {"name": "Bash: bt sql ...", "command": "bt sql SELECT count(*) FROM project_logs LIMIT 100", "start": 1.0},
                {"name": "Bash: bt view ...", "command": "bt view exp-123 --limit 20", "start": 2.0},
                {"name": "Bash: bt eval ...", "command": "bt eval evals/eval.py --first 20", "start": 3.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },
    {
        "input": {
            "scorer": "run_efficiency",
            "label": "2 duplicate commands → 0.8",
            "spans": [
                {"name": "Bash: ls evals/", "command": "ls evals/", "start": 1.0},
                {"name": "Bash: ls evals/", "command": "ls evals/", "start": 2.0},
                {"name": "Bash: ls evals/", "command": "ls evals/", "start": 3.0},
            ],
        },
        "expected": {"min": 0.75, "max": 0.85},
    },
    {
        "input": {
            "scorer": "run_efficiency",
            "label": "auth-seeking (cat ~/.env) → small penalty",
            "spans": [
                {"name": "Bash: cat ...", "command": "cat ~/.env", "start": 1.0},
                {"name": "Bash: bt sql ...", "command": "bt sql SELECT ...", "start": 2.0},
            ],
        },
        "expected": {"min": 0.9, "max": 0.99},
    },
    {
        "input": {
            "scorer": "run_efficiency",
            "label": "duplicate auth-seeking → compounded penalty",
            "spans": [
                {"name": "Bash: grep ...", "command": "grep API_KEY ~/.env", "start": 1.0},
                {"name": "Bash: grep ...", "command": "grep API_KEY ~/.env", "start": 2.0},
                {"name": "Bash: printenv ...", "command": "printenv BRAINTRUST_KEY", "start": 3.0},
            ],
        },
        "expected": {"min": 0.0, "max": 0.85},
    },
    {
        "input": {
            "scorer": "run_efficiency",
            "label": "no bash spans → 1.0",
            "spans": [
                {"name": "Read: src/agent.py", "start": 1.0},
                {"name": "Edit: src/agent.py", "start": 2.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },

    # ── Claimed vs Actual ─────────────────────────────────────────────────────
    # Summary content is carried by a "Bash: write bt-flywheel-summary.json" span
    # so it is found by _extract_summary_text but not counted as a code edit.
    {
        "input": {
            "scorer": "claimed_vs_actual",
            "label": "claimed files exactly match actual edits → 1.0",
            "spans": [
                {"name": "Edit: src/agent.py", "start": 1.0},
                {
                    "name": "Bash: write bt-flywheel-summary.json",
                    "content": '{"changes": {"agent": ["src/agent.py: updated system prompt to handle comparisons"]}}',
                    "start": 2.0,
                },
            ],
        },
        "expected": {"min": 0.9, "max": 1.0},
    },
    {
        "input": {
            "scorer": "claimed_vs_actual",
            "label": "claims extra file not actually edited → reduced F1",
            "spans": [
                {"name": "Edit: src/agent.py", "start": 1.0},
                {
                    "name": "Bash: write bt-flywheel-summary.json",
                    "content": '{"changes": {"agent": ["src/agent.py: updated system prompt", "scorers.py: tightened criteria"]}}',
                    "start": 2.0,
                },
            ],
        },
        "expected": {"min": 0.0, "max": 0.75},
    },
    {
        "input": {
            "scorer": "claimed_vs_actual",
            "label": "summary misses one actual edit → reduced recall",
            "spans": [
                {"name": "Edit: src/agent.py", "start": 1.0},
                {"name": "Edit: evals/eval_agent.py", "start": 2.0},
                {
                    "name": "Bash: write bt-flywheel-summary.json",
                    "content": '{"changes": {"agent": ["src/agent.py: updated system prompt"]}}',
                    "start": 3.0,
                },
            ],
        },
        "expected": {"min": 0.0, "max": 0.75},
    },
    {
        "input": {
            "scorer": "claimed_vs_actual",
            "label": "no edits, no summary → 1.0",
            "spans": [
                {"name": "Read: src/agent.py", "start": 1.0},
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },
    {
        "input": {
            "scorer": "claimed_vs_actual",
            "label": "edits made but no summary → penalized",
            "spans": [
                {"name": "Edit: src/agent.py", "start": 1.0},
            ],
        },
        "expected": {"min": 0.0, "max": 0.4},
    },
    {
        "input": {
            "scorer": "claimed_vs_actual",
            "label": "summary with no agent changes, no edits → 1.0",
            "spans": [
                {
                    "name": "Bash: write bt-flywheel-summary.json",
                    "content": '{"changes": {"agent": [], "scorers": [], "datasets": []}}',
                    "start": 1.0,
                },
            ],
        },
        "expected": {"min": 1.0, "max": 1.0},
    },
]


# ─── Task ─────────────────────────────────────────────────────────────────────


def task(input_data: dict) -> dict:
    scorer_name = input_data["scorer"]
    spans = _build_spans(input_data["spans"])

    scorer_fn = {
        "evidence_before_change": score_evidence_before_change,
        "smoke_test_discipline": score_smoke_test_discipline,
        "run_efficiency": score_run_efficiency,
        "claimed_vs_actual": score_claimed_vs_actual,
    }[scorer_name]

    return scorer_fn(spans)


# ─── Scorer ───────────────────────────────────────────────────────────────────


def score_in_range(input, output, expected=None, **kwargs):
    """Checks that the computed score falls within [expected.min, expected.max]."""
    if expected is None:
        return None
    actual = output.get("score", -1) if isinstance(output, dict) else -1
    lo, hi = expected.get("min", 0.0), expected.get("max", 1.0)
    return 1.0 if lo <= actual <= hi else 0.0


# ─── Eval ─────────────────────────────────────────────────────────────────────

braintrust.Eval(
    _PROJECT,
    data=_DATASET,
    task=task,
    scores=[score_in_range],
    experiment_name="Scorer Unit Tests",
    metadata={
        "description": (
            "Unit tests for the 4 deterministic bt-flywheel online scorer functions. "
            "Each case specifies a fixture span sequence and asserts the computed score "
            "falls within an expected range."
        )
    },
)
