#!/usr/bin/env python3
"""Fetch Braintrust project configuration: scorer definitions, automation rules,
experiments, datasets, and project settings. Cross-joins scorers with their
active automation rules so sampling rates and filters are visible alongside
scorer type and model before making cost recommendations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


API_BASE_DEFAULT = "https://api.braintrust.dev"


def resolve_api_base() -> str:
    """Resolve the Braintrust API base URL for the active profile.

    Priority:
    1. BRAINTRUST_API_URL env var (same var the bt CLI reads)
    2. api_url from the active profile in ~/.config/bt/auth.json
    3. Hardcoded default (cloud SaaS)
    """
    env_url = os.environ.get("BRAINTRUST_API_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")

    try:
        auth_path = Path.home() / ".config" / "bt" / "auth.json"
        auth = json.loads(auth_path.read_text())
        profiles = auth.get("profiles") or {}

        # Find the active profile: check local .bt/config.json first, then any project config
        active_profile: str | None = None
        for config_path in [Path(".bt/config.json"), Path.home() / ".config" / "bt" / "config.json"]:
            if config_path.exists():
                cfg = json.loads(config_path.read_text())
                active_profile = cfg.get("profile") or cfg.get("org")
                if active_profile:
                    break

        if active_profile and active_profile in profiles:
            url = profiles[active_profile].get("api_url", "").strip()
            if url:
                return url.rstrip("/")

        # Fall back to first profile with a non-default URL, then first profile overall
        for prof in profiles.values():
            url = prof.get("api_url", "").strip()
            if url:
                return url.rstrip("/")
    except Exception:
        pass

    return API_BASE_DEFAULT


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def api_get(path: str, *, api_key: str, api_base: str = API_BASE_DEFAULT, params: dict[str, str] | None = None) -> dict[str, Any]:
    url = f"{api_base}{path}"
    if params:
        query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{query}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc


def paginate(path: str, *, api_key: str, api_base: str = API_BASE_DEFAULT, extra_params: dict[str, str] | None = None, limit: int = 100) -> list[dict[str, Any]]:
    params = {"limit": str(limit), **(extra_params or {})}
    data = api_get(path, api_key=api_key, api_base=api_base, params=params)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("objects", "data", "rows", "results", "items"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


# ---------------------------------------------------------------------------
# bt CLI helpers (for OAuth-authed commands)
# ---------------------------------------------------------------------------

def bt_scorers_list() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["bt", "scorers", "list", "--json"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"bt scorers list failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    if isinstance(data, list):
        return data
    return data.get("objects", data.get("data", []))


# ---------------------------------------------------------------------------
# Scorer definition analysis
# ---------------------------------------------------------------------------

def classify_scorer(scorer: dict[str, Any]) -> dict[str, Any]:
    fd = scorer.get("function_data") or {}
    fd_type = fd.get("type", "")          # "code" or "prompt"
    pd = scorer.get("prompt_data") or {}
    opts = pd.get("options") or {}
    model = opts.get("model") or ""
    params = opts.get("params") or {}
    reasoning = params.get("reasoning_effort") or ""

    if fd_type == "prompt" or pd:
        scorer_type = "llm"
    elif fd_type == "code":
        scorer_type = "code"
    else:
        scorer_type = "unknown"

    return {
        "id": scorer.get("id"),
        "name": scorer.get("name"),
        "slug": scorer.get("slug"),
        "scorer_type": scorer_type,
        "model": model or None,
        "reasoning_effort": reasoning or None,
        "tags": scorer.get("tags") or [],
        "description": scorer.get("description") or None,
    }


# ---------------------------------------------------------------------------
# Automation rule analysis
# ---------------------------------------------------------------------------

def summarize_automation(rule: dict[str, Any], scorer_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # The scorer reference may be in different fields depending on API version
    scorer_id = (
        rule.get("scorer_id")
        or rule.get("function_id")
        or (rule.get("scorer") or {}).get("id")
    )
    scorer = scorer_by_id.get(scorer_id or "") or {}
    scorer_info = classify_scorer(scorer) if scorer else {}

    sampling_rate = rule.get("sampling_rate")
    if sampling_rate is None:
        sampling_rate = rule.get("config", {}).get("sampling_rate")

    filter_clause = rule.get("filter") or rule.get("btql_filter") or rule.get("config", {}).get("filter")
    apply_root = rule.get("apply_to_root_span") if rule.get("apply_to_root_span") is not None else rule.get("config", {}).get("apply_to_root_span")
    span_names = rule.get("apply_to_span_names") or rule.get("config", {}).get("apply_to_span_names") or []

    at_full_rate = sampling_rate is None or sampling_rate >= 1.0

    return {
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name"),
        "scorer_id": scorer_id,
        "scorer_name": scorer_info.get("name") or scorer.get("name") or rule.get("scorer_name"),
        "scorer_type": scorer_info.get("scorer_type") or "unknown",
        "model": scorer_info.get("model"),
        "reasoning_effort": scorer_info.get("reasoning_effort"),
        "scorer_tags": scorer_info.get("tags") or [],
        "sampling_rate": sampling_rate,
        "at_full_rate": at_full_rate,
        "apply_to_root_span": apply_root,
        "apply_to_span_names": span_names,
        "has_filter": bool(filter_clause),
        "filter": filter_clause,
    }


# ---------------------------------------------------------------------------
# Experiment / dataset summaries
# ---------------------------------------------------------------------------

def summarize_list(items: list[dict[str, Any]], label: str) -> dict[str, Any]:
    if not items:
        return {"count": 0, "note": f"no {label} found or API unavailable"}
    dates = [i.get("created") for i in items if i.get("created")]
    return {
        "count": len(items),
        "most_recent": sorted(dates)[-1] if dates else None,
        "oldest": sorted(dates)[0] if dates else None,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def pct(rate: float | None) -> str:
    if rate is None:
        return "?"
    return f"{rate * 100:.0f}%"


def render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []

    lines += [
        "# Braintrust Project Config Summary",
        "",
        f"**Project:** {summary.get('project_name') or summary.get('project_id')}",
        f"**Org:** {summary.get('org_name') or '?'}",
        "",
    ]

    # Automation rules
    rules = summary.get("automation_rules") or []
    if summary.get("automation_rules_unavailable"):
        lines += [
            "## Scorer Automation Rules",
            "",
            "> **Unavailable** — `BRAINTRUST_API_KEY` not set. Check the Braintrust UI under Project → Logs → Score to review sampling rates and filters.",
            "",
        ]
    elif not rules:
        lines += ["## Scorer Automation Rules", "", "_No active automation rules found._", ""]
    else:
        lines += ["## Scorer Automation Rules", ""]
        header = "| Rule | Scorer | Type | Model | Sampling | Root only | Span filter | SQL filter |"
        sep    = "|---|---|---|---|---|---|---|---|"
        lines += [header, sep]
        for r in rules:
            span_filter = ", ".join(r.get("apply_to_span_names") or []) or "—"
            lines.append(
                f"| {r.get('rule_name') or '—'}"
                f" | {r.get('scorer_name') or '—'}"
                f" | {r.get('scorer_type') or '?'}"
                f" | {r.get('model') or '—'}"
                f" | {pct(r.get('sampling_rate'))}"
                f" | {'yes' if r.get('apply_to_root_span') else 'no'}"
                f" | {span_filter}"
                f" | {'yes' if r.get('has_filter') else 'no'}"
                " |"
            )
        lines.append("")

        # Call out full-rate rules
        full_rate = [r for r in rules if r.get("at_full_rate")]
        llm_full = [r for r in full_rate if r.get("scorer_type") == "llm"]
        if full_rate:
            lines += [
                f"> **{len(full_rate)} rule(s) running at 100% sampling** "
                f"({len(llm_full)} LLM-as-judge). "
                "Consider reducing sampling on code scorers to 10–20%.",
                "",
            ]

    # Scorer definitions (unattached)
    scorers = summary.get("scorer_definitions") or []
    if scorers:
        active_ids = {r.get("scorer_id") for r in rules}
        attached = [s for s in scorers if s.get("id") in active_ids]
        unattached = [s for s in scorers if s.get("id") not in active_ids]
        delete_tagged = [s for s in scorers if "delete-scorer" in (s.get("tags") or [])]

        lines += [
            "## Scorer Definitions",
            "",
            f"- Total defined: {len(scorers)}",
            f"- Attached to an active automation: {len(attached)}",
            f"- Defined but not in any automation: {len(unattached)}",
            f"- Tagged `delete-scorer`: {len(delete_tagged)}",
            "",
        ]

        llm_scorers = [s for s in scorers if s.get("scorer_type") == "llm"]
        if llm_scorers:
            lines += ["### LLM-as-Judge Scorers", ""]
            header = "| Name | Model | Reasoning | Tags | In automation |"
            sep    = "|---|---|---|---|---|"
            lines += [header, sep]
            for s in llm_scorers:
                in_auto = "yes" if s.get("id") in active_ids else "no"
                tags = ", ".join(s.get("tags") or []) or "—"
                lines.append(
                    f"| {s.get('name') or '—'}"
                    f" | {s.get('model') or '—'}"
                    f" | {s.get('reasoning_effort') or '—'}"
                    f" | {tags}"
                    f" | {in_auto}"
                    " |"
                )
            lines.append("")

    # Experiments
    exp = summary.get("experiments") or {}
    lines += [
        "## Experiments",
        "",
        f"- Count (last 100): {exp.get('count', '?')}",
        f"- Most recent: {exp.get('most_recent') or '?'}",
        "",
    ]

    # Datasets
    ds = summary.get("datasets") or {}
    lines += [
        "## Datasets",
        "",
        f"- Count (last 100): {ds.get('count', '?')}",
        f"- Most recent: {ds.get('most_recent') or '?'}",
        "",
    ]

    # Project settings
    proj = summary.get("project_settings") or {}
    if proj:
        lines += [
            "## Project Settings",
            "",
            f"- Name: {proj.get('name') or '?'}",
            f"- Created: {proj.get('created') or '?'}",
        ]
        if proj.get("settings"):
            lines.append(f"- Settings: `{json.dumps(proj['settings'])}`")
        lines.append("")

    lines += [
        "## Caveats",
        "",
        "- Automation rule shapes vary by Braintrust API version; fields may appear under different keys.",
        "- Scorer definitions include all scorers ever created, not just those in active automations.",
        "- Experiment and dataset counts are capped at 100; higher-volume projects may have more.",
        "- This config view complements `analyze-cost-drivers.py`; use both together.",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_summary(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    api_key = args.api_key or os.environ.get("BRAINTRUST_API_KEY") or ""
    api_base = (args.api_base or resolve_api_base()).rstrip("/")
    project_id = args.project_id

    summary: dict[str, Any] = {
        "project_id": project_id,
        "project_name": None,
        "org_name": None,
    }

    # Fetch scorer definitions via bt CLI (handles OAuth + API key auth)
    raw_scorers: list[dict[str, Any]] = []
    try:
        raw_scorers = bt_scorers_list()
    except Exception as exc:
        print(f"warning: bt scorers list failed: {exc}", file=sys.stderr)

    scorer_definitions = [classify_scorer(s) for s in raw_scorers]
    scorer_by_id = {s["id"]: s for s in raw_scorers if s.get("id")}

    summary["scorer_definitions"] = scorer_definitions

    if not api_key:
        print(
            "warning: BRAINTRUST_API_KEY not set — skipping REST API calls "
            "(automation rules, experiments, datasets, project settings).\n"
            "Set BRAINTRUST_API_KEY or pass --api-key to get the full config picture.",
            file=sys.stderr,
        )
        summary["automation_rules_unavailable"] = True
        summary["automation_rules"] = []
        summary["experiments"] = {"count": None, "note": "API key required"}
        summary["datasets"] = {"count": None, "note": "API key required"}
        summary["project_settings"] = {}
    else:
        # Fetch concurrently
        results: dict[str, Any] = {}
        errors: dict[str, str] = {}

        def fetch(name: str, fn):
            try:
                results[name] = fn()
            except Exception as exc:
                errors[name] = str(exc)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(fetch, "automations", lambda: paginate(
                    "/v1/project_score",
                    api_key=api_key, api_base=api_base,
                    extra_params={"project_id": project_id},
                )): "automations",
                pool.submit(fetch, "experiments", lambda: paginate(
                    "/v1/experiment",
                    api_key=api_key, api_base=api_base,
                    extra_params={"project_id": project_id},
                )): "experiments",
                pool.submit(fetch, "datasets", lambda: paginate(
                    "/v1/dataset",
                    api_key=api_key, api_base=api_base,
                    extra_params={"project_id": project_id},
                )): "datasets",
                pool.submit(fetch, "project", lambda: api_get(
                    f"/v1/project/{project_id}",
                    api_key=api_key, api_base=api_base,
                )): "project",
            }
            for f in as_completed(futures):
                pass  # results/errors populated by fetch()

        for name, err in errors.items():
            print(f"warning: {name} fetch failed: {err}", file=sys.stderr)

        raw_rules = results.get("automations") or []
        automation_rules = [summarize_automation(r, scorer_by_id) for r in raw_rules]
        summary["automation_rules"] = automation_rules
        summary["automation_rules_unavailable"] = False

        summary["experiments"] = summarize_list(results.get("experiments") or [], "experiments")
        summary["datasets"] = summarize_list(results.get("datasets") or [], "datasets")

        proj = results.get("project") or {}
        summary["project_name"] = proj.get("name")
        summary["org_name"] = proj.get("org_name")
        summary["project_settings"] = {
            "name": proj.get("name"),
            "created": proj.get("created"),
            "settings": proj.get("settings"),
        }

    return summary, render_markdown(summary)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True, help="Braintrust project ID (UUID)")
    parser.add_argument("--api-key", default=None, help="Braintrust API key (falls back to BRAINTRUST_API_KEY env var)")
    parser.add_argument("--api-base", default=None, help="Braintrust API base URL (default: resolves from BRAINTRUST_API_URL env var, active bt profile, or https://api.braintrust.dev)")
    parser.add_argument("--output", help="Write Markdown report to this file (default: stdout)")
    parser.add_argument("--json-output", help="Write machine-readable JSON summary to this file")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    summary, markdown = build_summary(args)

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(markdown)

    if args.json_output:
        Path(args.json_output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"wrote {args.json_output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
