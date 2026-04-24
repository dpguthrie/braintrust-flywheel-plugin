"""
Pure scoring logic for bt-flywheel quality scorers.

Importable without triggering Braintrust registration — safe to use in tests and evals.
Registration lives in flywheel_scorers.py.
"""

import json
import os
import re
from typing import Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

# ─── Configuration ─────────────────────────────────────────────────────────────

_JUDGE_MODEL = os.getenv("FLYWHEEL_JUDGE_MODEL", "gpt-4o-mini")
_CODE_PATHS = os.getenv("FLYWHEEL_CODE_PATHS", "")

# Matches any Edit/Write span; narrowed to specific paths when FLYWHEEL_CODE_PATHS is set
_edit_re = (
    re.compile(rf"^(Edit|Write): .*({_CODE_PATHS})")
    if _CODE_PATHS
    else re.compile(r"^(Edit|Write):")
)

client = AsyncOpenAI(
    api_key=os.getenv("BRAINTRUST_API_KEY"),
    base_url=os.getenv("BRAINTRUST_GATEWAY_BASE_URL", "https://gateway.braintrust.dev"),
)


# ─── Span helpers ─────────────────────────────────────────────────────────────


def _span_name(span) -> str:
    sa = getattr(span, "span_attributes", {})
    if hasattr(sa, "get"):
        return sa.get("name", "") or ""
    return ""


def _span_input(span) -> dict:
    raw = getattr(span, "input", None)
    return raw if isinstance(raw, dict) else {}


def _span_start(span) -> float:
    m = getattr(span, "metrics", None)
    return getattr(m, "start", 0.0) or 0.0 if m else 0.0


async def _get_spans(trace) -> list:
    try:
        spans = await trace.get_spans()
    except Exception:
        try:
            spans = await trace.get_spans(span_type=["tool"])
        except Exception:
            return []
    return sorted(spans, key=_span_start)


def _extract_summary_text(spans: list) -> str | None:
    for s in spans:
        name = _span_name(s)
        if "bt-flywheel-summary.json" in name or "bt-flywheel-narrative.md" in name:
            return _span_input(s).get("content") or None
    return None


# ─── Pure scoring logic ───────────────────────────────────────────────────────


def score_evidence_before_change(spans: list) -> dict:
    """Each code edit should be preceded by bt sql or bt view evidence gathering."""
    names = [_span_name(s) for s in spans]
    evidence_re = re.compile(r"^Bash:.*\b(bt sql|bt view)\b", re.IGNORECASE)

    edit_indices = [i for i, n in enumerate(names) if _edit_re.search(n)]
    if not edit_indices:
        return {"score": 1.0, "metadata": {"edit_count": 0}}

    with_evidence = sum(
        1 for i in edit_indices if any(evidence_re.search(n) for n in names[:i])
    )
    return {
        "score": with_evidence / len(edit_indices),
        "metadata": {
            "edit_count": len(edit_indices),
            "evidence_before": with_evidence,
            "edited_files": [names[i].split(": ", 1)[-1] for i in edit_indices],
        },
    }


def score_smoke_test_discipline(spans: list) -> dict:
    """Smoke run (--first N) should precede any full eval."""
    eval_spans = [
        s
        for s in spans
        if re.search(r"braintrust eval|bt eval", _span_name(s), re.IGNORECASE)
        and _span_name(s).startswith("Bash:")
    ]
    if not eval_spans:
        return {"score": 1.0, "metadata": {"eval_runs": 0}}

    smoke, full = [], []
    for s in eval_spans:
        inp = _span_input(s)
        cmd = inp.get("command", _span_name(s))
        (smoke if "--first" in cmd else full).append(s)

    if not full:
        return {
            "score": 1.0,
            "metadata": {"smoke_only": True, "eval_runs": len(eval_spans)},
        }
    if not smoke:
        return {"score": 0.4, "metadata": {"smoke_runs": 0, "full_runs": len(full)}}

    smoke_first = min(_span_start(s) for s in smoke) < min(_span_start(s) for s in full)
    return {
        "score": 1.0 if smoke_first else 0.2,
        "metadata": {
            "smoke_runs": len(smoke),
            "full_runs": len(full),
            "smoke_before_full": smoke_first,
        },
    }


def score_run_efficiency(spans: list) -> dict:
    """Penalize duplicate Bash commands and auth-seeking calls."""
    auth_re = re.compile(
        r"(cat.*\.config/bt|cat.*\.env|grep.*API_KEY|printenv.*KEY|find.*\.env)",
        re.IGNORECASE,
    )
    seen, duplicates, auth_calls = set(), 0, 0
    for s in spans:
        if not _span_name(s).startswith("Bash:"):
            continue
        cmd = _span_input(s).get("command", "")
        key = re.sub(r"\s+", " ", cmd.strip().lower())
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
        if auth_re.search(cmd):
            auth_calls += 1

    score = max(0.0, 1.0 - duplicates * 0.1 - auth_calls * 0.05)
    return {
        "score": score,
        "metadata": {
            "unique_bash_calls": len(seen),
            "duplicate_commands": duplicates,
            "auth_seeking_calls": auth_calls,
        },
    }


def score_claimed_vs_actual(spans: list) -> dict:
    """Summary's claimed changes should match actual Edit/Write spans on code files."""
    actual = {
        _span_name(s).split(": ", 1)[-1].strip()
        for s in spans
        if _edit_re.search(_span_name(s))
    }

    summary_text = _extract_summary_text(spans)
    if not summary_text:
        return (
            {"score": 1.0, "metadata": {"note": "no summary, no edits"}}
            if not actual
            else {
                "score": 0.3,
                "metadata": {
                    "note": "edits made but no summary",
                    "actual": list(actual),
                },
            }
        )

    try:
        summary = json.loads(summary_text)
    except (json.JSONDecodeError, TypeError):
        return {"score": 0.5, "metadata": {"note": "summary not valid JSON"}}

    agent_changes = summary.get("changes", {}).get("agent", [])
    claimed = {
        m.group(1) for c in agent_changes if (m := re.match(r"^([^\s:]+\.\w+):", c))
    }

    if not claimed and not actual:
        return {"score": 1.0, "metadata": {"note": "no changes claimed or made"}}
    if not actual:
        return {
            "score": 0.2,
            "metadata": {
                "note": "claimed changes but no edits found",
                "claimed": list(claimed),
            },
        }
    if not claimed:
        return {
            "score": 0.4,
            "metadata": {
                "note": "edits not reflected in summary",
                "actual": list(actual),
            },
        }

    overlap = claimed & actual
    p = len(overlap) / len(claimed)
    r = len(overlap) / len(actual)
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {
        "score": f1,
        "metadata": {
            "claimed": list(claimed),
            "actual": list(actual),
            "precision": p,
            "recall": r,
        },
    }


# ─── LLM judges ───────────────────────────────────────────────────────────────

_NARRATIVE_PROMPT = """\
You are evaluating the specificity of a self-improving agent's run summary.
A strong summary includes exact metric deltas, file paths, trace IDs, SQL result counts,
Braintrust experiment links, and before/after comparisons — enough detail to independently
verify what changed. A weak summary says things like "improved performance" or "fixed an issue"
with no specifics.

Run summary:
{summary}

(A) EXCELLENT — Specific metrics, file paths, score deltas, trace IDs or URLs, query counts. Reader can verify independently.
(B) GOOD — Some specifics but key details missing (e.g., file mentioned but not what changed).
(C) FAIR — Mostly generic. Hard to verify without re-running the analysis.
(D) POOR — No specifics, summary not written, or placeholder text.
"""

_COHERENCE_PROMPT = """\
You are evaluating whether a self-improving agent's code changes are logically motivated by its findings.

Findings:
{findings}

Changes made:
{changes}

(A) EXCELLENT — Every change directly addresses a specific finding. No unmotivated changes.
(B) GOOD — Most changes connect to findings. One or two minor gaps.
(C) FAIR — Some changes lack clear motivation, or a significant finding was ignored.
(D) POOR — Changes don't connect to findings, or agent made speculative changes.
"""


class _LLMChoice(BaseModel):
    rationale: str = Field(
        description="Write out your reasoning step by step before selecting a choice. Avoid stating the conclusion first."
    )
    choice: Literal["A", "B", "C", "D"]


_CHOICE_SCORES = {"A": 1.0, "B": 0.75, "C": 0.4, "D": 0.0}


async def score_narrative_specificity(spans: list) -> dict:
    text = _extract_summary_text(spans)
    if not text:
        return {"score": 0.0, "metadata": {"note": "no summary found"}}
    prompt = _NARRATIVE_PROMPT.format(summary=text[:4000])
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
            },
        }
    except Exception as e:
        return {"score": 0.0, "metadata": {"error": str(e)}}


async def score_diagnostic_coherence(spans: list) -> dict:
    text = _extract_summary_text(spans)
    if not text:
        return {"score": 0.5, "metadata": {"note": "no summary"}}
    try:
        summary = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"score": 0.5, "metadata": {"note": "summary not valid JSON"}}

    agent_changes = summary.get("changes", {}).get("agent", [])
    if not agent_changes:
        return {"score": 1.0, "metadata": {"note": "no changes — coherence N/A"}}

    findings = summary.get("findings", [])
    prompt = _COHERENCE_PROMPT.format(
        findings="\n".join(f"- {f}" for f in findings) or "(none)",
        changes="\n".join(f"- {c}" for c in agent_changes),
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
                "findings_count": len(findings),
                "changes_count": len(agent_changes),
            },
        }
    except Exception as e:
        return {"score": 0.0, "metadata": {"error": str(e)}}
