"""
Braintrust Eval wrapper for the offline bt-flywheel harness.

Run locally without Braintrust:
    python3 evals/bt-flywheel-harness/run_harness.py --runner scripted

Run with Claude Code:
    FLYWHEEL_HARNESS_RUNNER=claude braintrust eval evals/bt-flywheel-harness/eval_harness.py

Run as a Braintrust Eval:
    BRAINTRUST_API_KEY=... braintrust eval evals/bt-flywheel-harness/eval_harness.py

Compare variants:
    FLYWHEEL_HARNESS_SKILL_VARIANTS=none,current \
    BRAINTRUST_API_KEY=... braintrust eval evals/bt-flywheel-harness/eval_harness.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import braintrust

from harness.core import load_scenarios, run_scenario


_PROJECT = os.getenv("BRAINTRUST_EVAL_PROJECT", "bt-flywheel")
_RUNNER = os.getenv("FLYWHEEL_HARNESS_RUNNER", "scripted")


def _split_env(name, default):
    raw = os.getenv(name)
    if not raw:
        return default
    return [part.strip() for part in raw.split(",") if part.strip()]


def _rows():
    scenario_ids = _split_env("FLYWHEEL_HARNESS_SCENARIOS", [])
    variants = _split_env("FLYWHEEL_HARNESS_SKILL_VARIANTS", ["current"])
    scenarios = load_scenarios(scenario_ids or None)
    rows = []
    for scenario in scenarios:
        for variant in variants:
            rows.append(
                {
                    "input": {
                        "scenario_id": scenario.id,
                        "skill_variant": variant,
                        "runner": _RUNNER,
                    },
                    "expected": scenario.manifest["expected"],
                    "metadata": {
                        "scenario": scenario.id,
                        "skill_variant": variant,
                        "runner": _RUNNER,
                    },
                }
            )
    return rows


def task(input_data):
    return run_scenario(
        input_data["scenario_id"],
        skill_variant=input_data["skill_variant"],
        runner=input_data.get("runner", _RUNNER),
        keep_workspace=os.getenv("FLYWHEEL_HARNESS_KEEP_WORKSPACE") == "1",
    )


def _check_score(output, name):
    for check in output.get("checks", []):
        if check.get("name") == name:
            return {"score": check["score"], "metadata": check.get("metadata", {})}
    return {"score": 0.0, "metadata": {"missing_check": name}}


def aggregate_score(input, output, expected=None, **kwargs):
    return output.get("score", 0.0)


def handoff_contract(input, output, expected=None, **kwargs):
    return _check_score(output, "handoff_contract")


def expected_outcome(input, output, expected=None, **kwargs):
    return _check_score(output, "expected_outcome")


def evidence_terms(input, output, expected=None, **kwargs):
    return _check_score(output, "evidence_terms")


def change_policy(input, output, expected=None, **kwargs):
    return _check_score(output, "change_policy")


def bt_usage(input, output, expected=None, **kwargs):
    return _check_score(output, "bt_usage")


def acceptance(input, output, expected=None, **kwargs):
    return _check_score(output, "acceptance")


_SCORES = [
    aggregate_score,
    handoff_contract,
    expected_outcome,
    evidence_terms,
    change_policy,
    bt_usage,
    acceptance,
]


if os.getenv("FLYWHEEL_HARNESS_LLM_JUDGE") == "1":
    from openai import AsyncOpenAI
    from pydantic import BaseModel
    from typing import Literal

    class _JudgeChoice(BaseModel):
        choice: Literal["A", "B", "C", "D"]
        rationale: str

    _CHOICE_SCORES = {"A": 1.0, "B": 0.75, "C": 0.4, "D": 0.0}
    _CLIENT = AsyncOpenAI(
        api_key=os.getenv("BRAINTRUST_API_KEY"),
        base_url=os.getenv("BRAINTRUST_GATEWAY_BASE_URL", "https://gateway.braintrust.dev"),
    )
    _MODEL = os.getenv("FLYWHEEL_JUDGE_MODEL", "gpt-4o-mini")

    async def handoff_quality(input, output, expected=None, **kwargs):
        prompt = """\
You are judging an offline bt-flywheel skill run. Evaluate whether the final handoff is useful,
evidence-grounded, and appropriate for the scenario expectations.

Expected:
{expected}

Summary:
{summary}

Changed files:
{changed}

bt commands:
{commands}

(A) Excellent, (B) Good, (C) Fair, (D) Poor.
"""
        try:
            resp = await _CLIENT.responses.parse(
                model=_MODEL,
                input=[
                    {
                        "role": "user",
                        "content": prompt.format(
                            expected=json.dumps(expected, sort_keys=True),
                            summary=json.dumps(output.get("summary", {}), sort_keys=True),
                            changed=output.get("changed_files", []),
                            commands=output.get("bt_command_log", []),
                        ),
                    }
                ],
                text_format=_JudgeChoice,
            )
            parsed = resp.output_parsed
            return {
                "score": _CHOICE_SCORES.get(parsed.choice, 0.0),
                "metadata": {"choice": parsed.choice, "rationale": parsed.rationale},
            }
        except Exception as e:
            return {"score": 0.0, "metadata": {"error": str(e)}}

    _SCORES.append(handoff_quality)


braintrust.Eval(
    _PROJECT,
    data=_rows(),
    task=task,
    scores=_SCORES,
    experiment_name="Flywheel Offline Harness",
    metadata={
        "description": (
            "Runs fixture repos through an offline bt-flywheel harness with a fake bt CLI, "
            "then scores handoff quality, evidence use, change policy, and acceptance checks."
        )
    },
)
