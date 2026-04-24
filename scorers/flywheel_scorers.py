"""
Flywheel quality scorers for Claude Code sessions running the bt-flywheel skill.

These scorers run *online* in Braintrust against Claude Code traces, measuring
the quality of the flywheel agent's own behavior — not the downstream task agent.

Six scorers are registered:
  Evidence Before Change   — each code edit should be preceded by bt sql/bt view evidence
  Smoke Test Discipline    — a --first N smoke run should precede any full eval
  Run Efficiency           — penalizes duplicate Bash commands and auth-seeking calls
  Narrative Specificity    — LLM judge: run summary should cite specific metrics/paths/IDs
  Diagnostic Coherence     — LLM judge: code changes should be motivated by findings
  Claimed vs Actual        — summary's claimed file changes should match actual Edit/Write spans

Configuration (set in environment before deploying):

  BRAINTRUST_CC_PROJECT       Project where Claude Code traces are logged.
                              Default: "my-agent-claude-code"

  FLYWHEEL_CODE_PATHS         Pipe-separated regex alternation for paths considered
                              "code files" in edit-tracking scorers.
                              Example: "src/|evals/|scorers\\.py"
                              Default: empty — matches all Edit/Write spans

  FLYWHEEL_JUDGE_MODEL        Model used for LLM-judge scorers.
                              Default: "gpt-4o-mini"

  BRAINTRUST_API_KEY          Required. Your Braintrust API key.

  BRAINTRUST_GATEWAY_BASE_URL Override Braintrust gateway base URL.
                              Default: https://gateway.braintrust.dev/v1

Deployment:

  BRAINTRUST_API_KEY=... \\
  BRAINTRUST_CC_PROJECT=my-agent-claude-code \\
  FLYWHEEL_CODE_PATHS="src/|evals/|scorers\\.py" \\
  bt functions push --language python \\
    --requirements scorers/requirements.txt \\
    --if-exists replace \\
    scorers/flywheel_scorers.py

  Re-run any time you want to push updated scorer logic.
"""

import os
from typing import Any

import braintrust
from pydantic import BaseModel

from _scoring import (
    _get_spans,
    score_claimed_vs_actual,
    score_diagnostic_coherence,
    score_evidence_before_change,
    score_narrative_specificity,
    score_run_efficiency,
    score_smoke_test_discipline,
)

# ─── Configuration ─────────────────────────────────────────────────────────────

_PROJECT_NAME = os.getenv("BRAINTRUST_CC_PROJECT", "my-agent-claude-code")


# ─── Online scorer handlers ────────────────────────────────────────────────────


async def evidence_before_change_scorer(input, trace):
    spans = await _get_spans(trace)
    return {"name": "Evidence Before Change", **score_evidence_before_change(spans)}


async def smoke_test_discipline_scorer(input, trace):
    spans = await _get_spans(trace)
    return {"name": "Smoke Test Discipline", **score_smoke_test_discipline(spans)}


async def run_efficiency_scorer(input, trace):
    spans = await _get_spans(trace)
    return {"name": "Run Efficiency", **score_run_efficiency(spans)}


async def narrative_specificity_scorer(input, trace):
    spans = await _get_spans(trace)
    return {
        "name": "Narrative Specificity",
        **(await score_narrative_specificity(spans)),
    }


async def diagnostic_coherence_scorer(input, trace):
    spans = await _get_spans(trace)
    return {"name": "Diagnostic Coherence", **(await score_diagnostic_coherence(spans))}


async def claimed_vs_actual_scorer(input, trace):
    spans = await _get_spans(trace)
    return {"name": "Claimed vs Actual", **score_claimed_vs_actual(spans)}


# ─── Registration ─────────────────────────────────────────────────────────────
# Module-level calls are required for bt functions push to discover scorers during import.


class _ScorerInput(BaseModel):
    input: Any
    trace: Any


_project = braintrust.projects.create(name=_PROJECT_NAME)

_project.scorers.create(
    name="Evidence Before Change",
    slug="evidence-before-change",
    description="Verifies bt sql or bt view evidence preceded each code edit.",
    parameters=_ScorerInput,
    handler=evidence_before_change_scorer,
)

_project.scorers.create(
    name="Smoke Test Discipline",
    slug="smoke-test-discipline",
    description="Checks that a --first N smoke eval ran before any full eval.",
    parameters=_ScorerInput,
    handler=smoke_test_discipline_scorer,
)

_project.scorers.create(
    name="Run Efficiency",
    slug="run-efficiency",
    description="Penalizes duplicate Bash commands and auth-seeking calls.",
    parameters=_ScorerInput,
    handler=run_efficiency_scorer,
)

_project.scorers.create(
    name="Narrative Specificity",
    slug="narrative-specificity",
    description="LLM judge: rates whether the run summary contains specific metrics, paths, and IDs.",
    parameters=_ScorerInput,
    handler=narrative_specificity_scorer,
)

_project.scorers.create(
    name="Diagnostic Coherence",
    slug="diagnostic-coherence",
    description="LLM judge: rates whether code changes are logically motivated by the findings.",
    parameters=_ScorerInput,
    handler=diagnostic_coherence_scorer,
)

_project.scorers.create(
    name="Claimed vs Actual",
    slug="claimed-vs-actual",
    description="Compares files claimed in the summary to actual Edit/Write spans.",
    parameters=_ScorerInput,
    handler=claimed_vs_actual_scorer,
)
