"""
Offline evaluation of bt-flywheel behavior quality against known scenarios.

Each example pairs a production scenario (what the agent's data looks like) with a
flywheel summary JSON (what the flywheel actually did). Two scorers evaluate quality:

  behavior_quality   — LLM judge: did the flywheel correctly diagnose the situation
                       and respond appropriately?
  regression_handled — code check: if regressions were detected, did the flywheel
                       re-loop rather than exit with "done"?

The dataset is split between positive examples (good flywheel behavior) and negative
examples (concrete failure modes the flywheel should avoid). A well-calibrated scorer
should rate positive examples A/B and negative examples C/D.

Run:
    cd /path/to/flywheel-plugin
    BRAINTRUST_API_KEY=... braintrust eval evals/eval_behavior.py
"""

import os
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent / "scorers"))

import braintrust
from _scoring import _CHOICE_SCORES, _LLMChoice, client

_PROJECT = os.getenv("BRAINTRUST_EVAL_PROJECT", "bt-flywheel")
_JUDGE_MODEL = os.getenv("FLYWHEEL_JUDGE_MODEL", "gpt-4o-mini")

# ─── LLM judge prompt ─────────────────────────────────────────────────────────

_BEHAVIOR_PROMPT = """\
You are evaluating how well a self-improving flywheel agent responded to a production scenario.
The flywheel analyzes an AI agent's Braintrust production traces, diagnoses problems, makes
targeted changes (to agent code, scorers, or datasets), runs evals, and routes based on results.

PRODUCTION SCENARIO:
{scenario}

FLYWHEEL RESPONSE:
  Phases run:      {phases_run}
  Findings:
{findings}
  Changes made:
    agent:    {agent_changes}
    scorers:  {scorer_changes}
    datasets: {dataset_changes}
  Metric delta:    {metric_delta}
  Regressions:     {regression_count} detected
  Loop decision:   {loop_decision}
  Reasoning:       {loop_reasoning}
  Recommended actions: {recommended_actions}

Evaluate the flywheel's response on these dimensions:
  1. Diagnosis quality: Did it correctly identify the situation (problem or healthy)?
  2. Action appropriateness: Were the changes (or lack of changes) right for the diagnosis?
  3. Routing correctness: Is the loop decision appropriate given the outcome?
  4. Act correctness: Did it recommend the right downstream action without executing it?

Key failure modes to watch for:
  - Making changes to a healthy system (unnecessary intervention)
  - Wrong diagnosis: fixing agent code when scorer is broken (bimodal distribution), or vice versa
  - Ignoring detected regressions and marking "done"
  - Recommending the wrong Act step (PR vs issue/ticket vs none)
  - Vague or unsupported reasoning not grounded in specific findings
  - Missing the primary issue when multiple problems are present

(A) EXCELLENT — Correct diagnosis, appropriate actions directly motivated by specific findings,
    loop decision matches the outcome. No unnecessary changes.
(B) GOOD — Mostly correct. Minor gap (e.g., addressed primary issue but missed a secondary one).
(C) FAIR — Partially correct. One significant error: wrong target, incomplete response,
    or missed a major signal.
(D) POOR — Wrong diagnosis leading to inappropriate action, unnecessary changes to a
    healthy system, or ignored regressions.
"""


# ─── Dataset ──────────────────────────────────────────────────────────────────
#
# Each example: scenario (production context) + summary (what the flywheel did).
# Tags distinguish positive examples (expect A/B) from negative (expect C/D).

_DATASET = [
    # ── Positive examples: good flywheel behavior ─────────────────────────────

    {
        "input": {
            "tags": ["positive", "healthy-exit"],
            "scenario": (
                "Production health check on a well-performing agent. "
                "Error rate: 3/250 traces (1.2%). Average score: 0.84. "
                "Score distribution: normal (bell curve). High latency: 2 traces >10s (0.8%). "
                "Eval dataset covers 91% of observed production query patterns. "
                "No anomalies detected in any metric."
            ),
            "summary": {
                "goal": "general health check",
                "phases_run": ["orient", "discover", "diagnose"],
                "findings": [
                    "Error rate: 3/250 traces (1.2%) — within acceptable range",
                    "Average score: 0.84 — healthy",
                    "Score distribution: normal (bell curve, no bimodal pattern)",
                    "High latency: 2 traces >10s (0.8%) — acceptable",
                    "Eval dataset covers 91% of observed production query patterns",
                ],
                "changes": {"agent": [], "scorers": [], "datasets": []},
                "experiment": None,
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": (
                    "Production metrics are healthy across all dimensions. "
                    "No corrective action required."
                ),
            },
        },
        "expected": "A or B: healthy project, flywheel correctly exits early with no changes",
    },
    {
        "input": {
            "tags": ["positive", "broken-scorer"],
            "scenario": (
                "Production traces show a bimodal score distribution: 43% of traces score "
                "exactly 0.0, 51% score exactly 1.0, only 6% have intermediate values. "
                "The 'response-quality' scorer appears to use binary pass/fail criteria "
                "rather than a graduated rubric. Average score: 0.62. No genuine improvement "
                "signal visible in recent eval experiments — scores just switch modes."
            ),
            "summary": {
                "goal": "improve eval quality",
                "phases_run": ["orient", "discover", "diagnose", "curate", "eval", "analyze", "loop"],
                "findings": [
                    "Score distribution: bimodal — 43% of traces score exactly 0.0, 51% score exactly 1.0",
                    "Scorer 'response-quality' uses binary yes/no criteria with no partial credit",
                    "bt sql: score_stddev=0.49 confirms near-binary distribution",
                    "Recent experiments show scores switching modes rather than improving continuously",
                ],
                "changes": {
                    "agent": [],
                    "scorers": [
                        "response-quality: Updated from binary (pass/fail) to graduated rubric "
                        "(0.0–1.0 scale with partial credit for reasoning, factual accuracy, completeness)"
                    ],
                    "datasets": [],
                },
                "experiment": {
                    "new": "exp-abc-2026-04-24",
                    "new_url": "https://www.braintrust.dev/app/myorg/p/my-agent/experiments/exp-abc-2026-04-24",
                    "baseline": "exp-xyz-2026-04-20",
                    "baseline_url": "https://www.braintrust.dev/app/myorg/p/my-agent/experiments/exp-xyz-2026-04-20",
                    "metric_delta": {"response-quality": 0.12},
                },
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": (
                    "Scorer update resolved bimodal distribution. Score distribution is now normal. "
                    "Metric improved +0.12 (0.62 → 0.74). No regressions detected."
                ),
            },
        },
        "expected": "A or B: bimodal distribution correctly identified as scorer problem, scorer updated",
    },
    {
        "input": {
            "tags": ["positive", "dataset-gap"],
            "scenario": (
                "Production has 3,400 traces over the last 7 days. Eval dataset has 120 examples. "
                "18% of production queries involve multi-step comparison tasks (e.g., 'compare X vs Y') "
                "— none of these appear in the eval dataset. Average score on comparison queries: 0.41 "
                "vs 0.82 for other query types. 612 production traces identified as comparison queries."
            ),
            "summary": {
                "goal": "improve coverage",
                "phases_run": ["orient", "discover", "diagnose", "curate", "eval", "analyze", "loop"],
                "findings": [
                    "Dataset gap: 18% of production queries involve multi-step comparisons — not in eval dataset",
                    "bt sql: 612 comparison query traces, avg score 0.41 vs 0.82 for other types",
                    "bt view trace-001, trace-047: agent provides one-sided answers without explicit comparison structure",
                    "Eval dataset: 120 examples, none tagged as comparison queries",
                ],
                "changes": {
                    "agent": [],
                    "scorers": [],
                    "datasets": [
                        "eval-dataset: Added 15 production comparison examples from "
                        "traces trace-001, trace-047, trace-112, trace-203, and 11 others"
                    ],
                },
                "experiment": {
                    "new": "exp-def-2026-04-24",
                    "new_url": "https://www.braintrust.dev/app/myorg/p/my-agent/experiments/exp-def-2026-04-24",
                    "baseline": "exp-xyz-2026-04-20",
                    "baseline_url": "https://www.braintrust.dev/app/myorg/p/my-agent/experiments/exp-xyz-2026-04-20",
                    "metric_delta": {"combined-score": -0.03},
                },
                "regressions": [],
                "loop_decision": "re-iterate",
                "loop_reasoning": (
                    "Dataset now covers comparison queries. Score decreased -0.03 because new "
                    "examples expose agent gaps. Routing back to Iterate to address "
                    "comparison query handling."
                ),
            },
        },
        "expected": "A or B: dataset gap correctly identified, examples added, re-loops to fix agent",
    },
    {
        "input": {
            "tags": ["positive", "agent-bug-fixed"],
            "scenario": (
                "Math queries represent 34% of production traffic. Average score on math queries: 0.38 "
                "vs 0.81 for non-math. bt view on 5 low-score traces shows the agent skips "
                "intermediate calculation steps on multi-step problems, leading to arithmetic errors. "
                "Root cause: system prompt does not instruct step-by-step verification."
            ),
            "summary": {
                "goal": "fix low scores on math queries",
                "phases_run": ["orient", "discover", "diagnose", "iterate", "eval", "analyze", "loop"],
                "findings": [
                    "bt sql: 287 math query traces in 7 days, avg score 0.38 vs 0.81 for non-math",
                    "bt view trace-456: agent skips intermediate steps on multi-step arithmetic",
                    "bt view trace-789: agent fails to verify intermediate results before proceeding",
                    "Root cause: system prompt lacks instruction to show step-by-step arithmetic work",
                ],
                "changes": {
                    "agent": [
                        "src/config.py: Added instruction to system prompt requiring step-by-step "
                        "arithmetic verification for multi-step math problems"
                    ],
                    "scorers": [],
                    "datasets": [],
                },
                "experiment": {
                    "new": "exp-ghi-2026-04-24",
                    "new_url": "https://www.braintrust.dev/app/myorg/p/my-agent/experiments/exp-ghi-2026-04-24",
                    "baseline": "exp-xyz-2026-04-20",
                    "baseline_url": "https://www.braintrust.dev/app/myorg/p/my-agent/experiments/exp-xyz-2026-04-20",
                    "metric_delta": {"combined-score": 0.09, "math-accuracy": 0.21},
                },
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": (
                    "Math accuracy improved 0.38 → 0.59 (+0.21). Combined score +0.09. "
                    "No regressions on non-math queries. Root cause addressed."
                ),
            },
        },
        "expected": "A or B: math query bug correctly diagnosed from trace evidence, targeted fix, improvement verified",
    },
    {
        "input": {
            "tags": ["positive", "no-convergence"],
            "scenario": (
                "Agent has consistent low scores around 0.51. Three full improvement iterations "
                "were attempted: adding dataset examples, updating system prompt (reverted after "
                "regression), tightening scorer criteria. Score oscillates 0.49–0.52 with no "
                "consistent improvement direction."
            ),
            "summary": {
                "goal": "improve response quality",
                "phases_run": [
                    "orient", "discover", "diagnose", "iterate", "eval", "analyze", "loop",
                    "iterate", "eval", "analyze", "loop",
                    "iterate", "eval", "analyze", "loop",
                ],
                "findings": [
                    "Initial: avg score 0.52, error rate 8%, 3 low-score patterns identified",
                    "Iteration 1 (exp-001): Added 8 production examples — score unchanged at 0.52",
                    "Iteration 2 (exp-002): System prompt update → score dropped to 0.49, reverted",
                    "Iteration 3 (exp-003): Tightened scorer criteria — score 0.51",
                    "Pattern: score oscillates 0.49–0.52 regardless of intervention type",
                ],
                "changes": {
                    "agent": ["src/config.py: System prompt update (reverted after regression in exp-002)"],
                    "scorers": ["query-quality: Tightened criteria for ambiguous query classification"],
                    "datasets": ["eval-dataset: Added 8 low-score production examples"],
                },
                "experiment": {
                    "new": "exp-003-2026-04-24",
                    "new_url": "https://www.braintrust.dev/app/myorg/p/my-agent/experiments/exp-003-2026-04-24",
                    "baseline": "exp-xyz-2026-04-20",
                    "baseline_url": "https://www.braintrust.dev/app/myorg/p/my-agent/experiments/exp-xyz-2026-04-20",
                    "metric_delta": {"combined-score": -0.01},
                },
                "regressions": [],
                "loop_decision": "no-convergence",
                "loop_reasoning": (
                    "3 full iterations attempted. Score range: 0.49–0.52. No consistent "
                    "improvement direction. Exiting with 'no-convergence' — manual "
                    "investigation recommended. Experiments exp-001, exp-002, exp-003 available."
                ),
            },
        },
        "expected": "A or B: no-convergence correctly identified after 3 iterations, exits cleanly with evidence",
    },

    # ── Positive examples: Act recommendations ───────────────────────────────

    {
        "input": {
            "tags": ["positive", "act-pr"],
            "expected_action_types": ["pull_request"],
            "scenario": (
                "The flywheel made a targeted prompt change backed by trace evidence. "
                "Smoke and full eval passed, score improved +0.09, and no regressions were found."
            ),
            "summary": {
                "goal": "fix low math scores",
                "phases_run": ["orient", "discover", "diagnose", "iterate", "eval", "analyze", "loop"],
                "findings": ["Math traces averaged 0.38 vs 0.81 for non-math"],
                "changes": {
                    "agent": ["src/config.py: Added step-by-step verification instruction"],
                    "scorers": [],
                    "datasets": [],
                },
                "experiment": {"metric_delta": {"math-accuracy": 0.09}},
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": "Score improved and no regressions were found.",
                "recommended_actions": [
                    {
                        "type": "pull_request",
                        "reason": "Code changed and evals passed with no blocking regressions.",
                        "title": "Flywheel: Improve math query handling",
                        "body_markdown": "Trace evidence showed low math scores; eval improved +0.09.",
                        "requires_human_review": True,
                        "evidence": ["https://www.braintrust.dev/app/org/p/proj/experiments/exp-1"],
                        "idempotency_key": "bt-flywheel:proj:2026-04-24:pull_request:math",
                    }
                ],
            },
        },
        "expected": "A or B: code changes with passing evals should recommend a PR",
    },
    {
        "input": {
            "tags": ["positive", "act-issue"],
            "expected_action_types": ["issue"],
            "scenario": (
                "Production degraded, but the flywheel could not safely change code because "
                "the issue requires human labeling and product judgment."
            ),
            "summary": {
                "goal": "investigate degraded support answers",
                "phases_run": ["orient", "discover", "diagnose"],
                "findings": ["27 low-score traces require human ground-truth labeling"],
                "changes": {"agent": [], "scorers": [], "datasets": []},
                "experiment": None,
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": "Human labels are required before safe iteration.",
                "recommended_actions": [
                    {
                        "type": "issue",
                        "reason": "Actionable follow-up exists but no safe automated code change was made.",
                        "title": "Flywheel: Label low-score support traces",
                        "body_markdown": "27 low-score traces need human labels before curation.",
                        "requires_human_review": True,
                        "evidence": ["https://www.braintrust.dev/app/org/p/proj/r/trace-1"],
                        "idempotency_key": "bt-flywheel:proj:2026-04-24:issue:labeling",
                    }
                ],
            },
        },
        "expected": "A or B: no code change plus human follow-up should recommend an issue",
    },
    {
        "input": {
            "tags": ["positive", "act-none"],
            "expected_action_types": ["none"],
            "scenario": "Production health check found healthy metrics and no follow-up work.",
            "summary": {
                "goal": "general health check",
                "phases_run": ["orient", "discover", "diagnose"],
                "findings": ["Average score 0.86, normal distribution, no coverage gaps"],
                "changes": {"agent": [], "scorers": [], "datasets": []},
                "experiment": None,
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": "Production is healthy.",
                "recommended_actions": [
                    {
                        "type": "none",
                        "reason": "No follow-up needed.",
                        "title": "Flywheel: No action needed",
                        "body_markdown": "Production is healthy; no changes or tickets recommended.",
                        "requires_human_review": False,
                        "evidence": [],
                        "idempotency_key": "bt-flywheel:proj:2026-04-24:none:healthy",
                    }
                ],
            },
        },
        "expected": "A or B: healthy system should recommend no downstream action",
    },

    # ── Negative examples: concrete failure modes ─────────────────────────────

    {
        "input": {
            "tags": ["negative", "unnecessary-changes"],
            "scenario": (
                "Production health check. Error rate: 1% (2/200 traces). Average score: 0.85. "
                "Score distribution: normal. No latency outliers. Eval dataset covers 94% "
                "of production patterns. All metrics are healthy."
            ),
            "summary": {
                "goal": "general health check",
                "phases_run": ["orient", "discover", "diagnose", "iterate", "eval", "analyze", "loop"],
                "findings": [
                    "Error rate: 1% — acceptable",
                    "Average score: 0.85 — healthy",
                    "Score distribution: normal",
                ],
                "changes": {
                    "agent": ["src/config.py: Refactored system prompt for improved clarity and conciseness"],
                    "scorers": [],
                    "datasets": [],
                },
                "experiment": {
                    "new": "exp-bad1-2026-04-24",
                    "new_url": "...",
                    "baseline": "exp-xyz-2026-04-20",
                    "baseline_url": "...",
                    "metric_delta": {"combined-score": 0.01},
                },
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": "Minor prompt refactoring improved clarity. Score increased 0.01.",
            },
        },
        "expected": "C or D: healthy system should exit after diagnose — making changes is inappropriate",
    },
    {
        "input": {
            "tags": ["negative", "wrong-diagnosis"],
            "scenario": (
                "Production scores show a bimodal distribution: 41% score exactly 0.0, "
                "55% score exactly 1.0. Only 4% of traces have scores between 0 and 1. "
                "This is a clear scorer calibration problem — the scorer has binary criteria. "
                "Average score: 0.61. No latency issues or errors."
            ),
            "summary": {
                "goal": "improve scores",
                "phases_run": ["orient", "discover", "diagnose", "iterate", "eval", "analyze", "loop"],
                "findings": [
                    "Average score: 0.61 — below target",
                    "Score distribution: bimodal (41% score 0, 55% score 1)",
                    "Low score queries: 39% of traces scoring 0",
                ],
                "changes": {
                    "agent": [
                        "src/config.py: Added more detailed instructions to system prompt "
                        "to improve response quality and comprehensiveness"
                    ],
                    "scorers": [],
                    "datasets": [],
                },
                "experiment": {
                    "new": "exp-bad2-2026-04-24",
                    "new_url": "...",
                    "baseline": "exp-xyz-2026-04-20",
                    "baseline_url": "...",
                    "metric_delta": {"combined-score": 0.02},
                },
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": "System prompt improvements led to slight score increase.",
            },
        },
        "expected": "C or D: bimodal distribution is a scorer problem — agent code changes are the wrong target",
    },
    {
        "input": {
            "tags": ["negative", "vague-summary"],
            "scenario": (
                "Production shows 43/200 traces (21.5%) scoring ≤ 0.3 concentrated on technical "
                "queries. bt view on 3 low-score traces reveals the agent answers technical questions "
                "with surface-level responses lacking domain depth. Baseline score: 0.61."
            ),
            "summary": {
                "goal": "improve agent performance",
                "phases_run": ["orient", "discover", "diagnose", "iterate", "eval", "analyze", "loop"],
                "findings": [
                    "Some issues were found in production",
                    "Performance could be improved",
                    "Several traces had low scores",
                ],
                "changes": {
                    "agent": ["Updated system prompt"],
                    "scorers": [],
                    "datasets": [],
                },
                "experiment": {
                    "new": "exp-bad3-2026-04-24",
                    "new_url": "...",
                    "baseline": "exp-xyz-2026-04-20",
                    "baseline_url": "...",
                    "metric_delta": {"combined-score": 0.05},
                },
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": "Performance improved.",
            },
        },
        "expected": (
            "C or D: findings and reasoning are vague — no trace IDs, no counts, no specific "
            "root cause. Summary cannot be independently verified."
        ),
    },
    {
        "input": {
            "tags": ["negative", "ignored-regressions"],
            "scenario": (
                "Production shows 43 traces with scores ≤ 0.3, concentrated on technical queries. "
                "Agent added technical depth instruction to system prompt. New eval shows combined "
                "score improved +0.08, but 5 previously high-scoring traces dropped to near zero. "
                "The improvement came at the cost of new regressions."
            ),
            "summary": {
                "goal": "improve response quality",
                "phases_run": ["orient", "discover", "diagnose", "iterate", "eval", "analyze", "loop"],
                "findings": [
                    "43 traces scoring ≤ 0.3, concentrated on technical queries",
                    "bt view trace-234: agent gives surface-level answers on technical topics",
                ],
                "changes": {
                    "agent": ["src/config.py: Added instruction to provide technical depth in responses"],
                    "scorers": [],
                    "datasets": [],
                },
                "experiment": {
                    "new": "exp-bad4-2026-04-24",
                    "new_url": "...",
                    "baseline": "exp-xyz-2026-04-20",
                    "baseline_url": "...",
                    "metric_delta": {"combined-score": 0.08},
                },
                "regressions": [
                    {"trace_id": "trace-500", "score": 0.1, "url": "..."},
                    {"trace_id": "trace-501", "score": 0.2, "url": "..."},
                    {"trace_id": "trace-502", "score": 0.15, "url": "..."},
                    {"trace_id": "trace-503", "score": 0.05, "url": "..."},
                    {"trace_id": "trace-504", "score": 0.22, "url": "..."},
                ],
                "loop_decision": "done",
                "loop_reasoning": "Score improved by +0.08. Task complete.",
            },
        },
        "expected": "C or D: 5 regressions detected but flywheel exits 'done' — regressions must trigger re-loop",
    },
    {
        "input": {
            "tags": ["negative", "incomplete-diagnosis"],
            "scenario": (
                "Production shows two distinct problems: (1) bimodal score distribution "
                "(38% score 0.0, 57% score 1.0 — clearly a scorer calibration issue), and "
                "(2) a dataset gap where 22% of production queries involve multi-turn "
                "conversations not represented in the eval dataset. Both issues are present "
                "and detectable from the trace data."
            ),
            "summary": {
                "goal": "improve eval quality",
                "phases_run": ["orient", "discover", "diagnose", "curate", "eval", "analyze", "loop"],
                "findings": [
                    "Score distribution: bimodal — 38% score 0.0, 57% score 1.0",
                    "Dataset gap: 22% of production queries are multi-turn conversations — not in eval dataset",
                    "Low score cluster on multi-turn queries: avg 0.38",
                ],
                "changes": {
                    "agent": [],
                    "scorers": [],
                    "datasets": [
                        "eval-dataset: Added 10 multi-turn conversation examples from production"
                    ],
                },
                "experiment": {
                    "new": "exp-bad5-2026-04-24",
                    "new_url": "...",
                    "baseline": "exp-xyz-2026-04-20",
                    "baseline_url": "...",
                    "metric_delta": {"combined-score": -0.02},
                },
                "regressions": [],
                "loop_decision": "done",
                "loop_reasoning": (
                    "Added multi-turn examples to dataset. Minor metric decrease expected "
                    "as new harder examples are now included."
                ),
            },
        },
        "expected": (
            "C or D: both problems identified in findings but only the dataset gap was addressed — "
            "the bimodal scorer issue was ignored, which is the higher-priority fix"
        ),
    },
]


# ─── Task ─────────────────────────────────────────────────────────────────────


def task(input_data: dict) -> dict:
    """Returns the flywheel summary — we score pre-specified outputs against their scenarios."""
    return input_data["summary"]


# ─── Scorers ──────────────────────────────────────────────────────────────────


async def behavior_quality(input, output, expected=None, **kwargs):
    """LLM judge: did the flywheel correctly diagnose the situation and respond appropriately?"""
    summary = output
    scenario = input.get("scenario", "")

    changes = summary.get("changes", {})
    metric_delta = summary.get("experiment", {}) or {}
    metric_delta = metric_delta.get("metric_delta", {}) if isinstance(metric_delta, dict) else {}

    prompt = _BEHAVIOR_PROMPT.format(
        scenario=scenario,
        phases_run=", ".join(summary.get("phases_run", [])),
        findings="\n".join(f"    - {f}" for f in summary.get("findings", [])) or "    (none)",
        agent_changes=changes.get("agent", []) or "(none)",
        scorer_changes=changes.get("scorers", []) or "(none)",
        dataset_changes=changes.get("datasets", []) or "(none)",
        metric_delta=metric_delta or "(no eval run)",
        regression_count=len(summary.get("regressions", [])),
        loop_decision=summary.get("loop_decision", "unknown"),
        loop_reasoning=summary.get("loop_reasoning", "(none)"),
        recommended_actions=summary.get("recommended_actions", "(none)"),
    )

    try:
        resp = await client.responses.parse(
            model=_JUDGE_MODEL,
            input=[{"role": "user", "content": prompt}],
            text_format=_LLMChoice,
        )
        out = resp.output_parsed
        return {
            "score": _CHOICE_SCORES.get(out.choice, 0.0) if out else 0.0,
            "metadata": {
                "choice": out.choice if out else "D",
                "rationale": out.rationale if out else "",
                "tags": input.get("tags", []),
            },
        }
    except Exception as e:
        return {"score": 0.0, "metadata": {"error": str(e)}}


def regression_handled(input, output, expected=None, **kwargs):
    """Code check: if regressions exist, the flywheel must not exit with 'done'."""
    summary = output
    regressions = summary.get("regressions", [])
    loop_decision = summary.get("loop_decision", "done")

    if not regressions:
        return 1.0

    # Has regressions — "done" is wrong, any re-loop decision is correct
    return 0.0 if loop_decision == "done" else 1.0


def act_recommendation(input, output, expected=None, **kwargs):
    """Code check: expected Act recommendations are present and well-formed."""
    expected_types = input.get("expected_action_types")
    if not expected_types:
        return 1.0

    actions = output.get("recommended_actions", [])
    actual_types = [action.get("type") for action in actions]
    if actual_types != expected_types:
        return {
            "score": 0.0,
            "metadata": {"expected": expected_types, "actual": actual_types},
        }

    required_fields = {
        "type",
        "reason",
        "title",
        "body_markdown",
        "requires_human_review",
        "evidence",
        "idempotency_key",
    }
    missing = [
        {"type": action.get("type"), "fields": sorted(required_fields - set(action))}
        for action in actions
        if required_fields - set(action)
    ]
    bad_none_review = [
        action
        for action in actions
        if action.get("type") == "none" and action.get("requires_human_review") is not False
    ]
    score = 1.0 if not missing and not bad_none_review else 0.5
    return {
        "score": score,
        "metadata": {
            "expected": expected_types,
            "actual": actual_types,
            "missing": missing,
            "bad_none_review_count": len(bad_none_review),
        },
    }


# ─── Eval ─────────────────────────────────────────────────────────────────────

braintrust.Eval(
    "Flywheel Behavior Quality",
    data=_DATASET,
    task=task,
    scores=[behavior_quality, regression_handled, act_recommendation],
    project_name=_PROJECT,
    metadata={
        "description": (
            "Evaluates the strategic quality of bt-flywheel run summaries against "
            "known production scenarios, including Act recommendation coverage."
        )
    },
)
