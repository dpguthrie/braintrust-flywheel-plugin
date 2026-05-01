#!/usr/bin/env python3
"""Analyze Braintrust cost drivers from exported JSON/JSONL rows."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


INTERESTING_NAME_PARTS = (
    "attachment",
    "body",
    "cache",
    "chunk",
    "completion",
    "content",
    "context",
    "document",
    "embedding",
    "endpoint",
    "facet",
    "html",
    "message",
    "metadata",
    "model",
    "output",
    "prompt",
    "request",
    "response",
    "result",
    "retrieved",
    "score",
    "scorer",
    "token",
    "tool",
    "topic",
    "transcript",
)


def json_bytes(value: Any) -> int:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    except Exception:
        encoded = str(value).encode("utf-8", errors="replace")
    return len(encoded)


def read_jsonish_file(path: Path) -> tuple[list[Any], list[str]]:
    errors: list[str] = []
    rows: list[Any] = []
    text = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        for lineno, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.extend(unwrap_rows(json.loads(line)))
            except Exception as exc:
                errors.append(f"{path}:{lineno}: {exc}")
        return rows, errors

    try:
        rows.extend(unwrap_rows(json.loads(text)))
    except Exception as exc:
        errors.append(f"{path}: {exc}")
    return rows, errors


def unwrap_rows(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("rows", "data", "spans", "logs", "results", "result", "items"):
            child = value.get(key)
            if isinstance(child, list):
                return child
        if isinstance(value.get("row"), dict):
            return [value["row"]]
    return [value]


def iter_input_paths(paths: list[Path]) -> tuple[list[Any], list[str]]:
    rows: list[Any] = []
    errors: list[str] = []
    files: list[Path] = []

    for path in paths:
        if path.is_dir():
            files.extend(
                p
                for p in sorted(path.rglob("*"))
                if p.suffix.lower() in {".json", ".jsonl", ".ndjson"}
            )
        else:
            files.append(path)

    for file_path in files:
        file_rows, file_errors = read_jsonish_file(file_path)
        rows.extend(file_rows)
        errors.extend(file_errors)

    return rows, errors


def normalize_path(parent: str, key: str) -> str:
    if not parent:
        return key
    return f"{parent}.{key}"


def walk_paths(
    value: Any,
    path: str,
    stats: dict[str, dict[str, Any]],
    *,
    row_idx: int,
    max_depth: int,
    max_items_per_array: int,
) -> None:
    if path:
        size = json_bytes(value)
        item = stats[path]
        item["total_bytes"] += size
        item["rows"].add(row_idx)
        item["count"] += 1
        if size > item["max_bytes"]:
            item["max_bytes"] = size

    if max_depth <= 0:
        return

    if isinstance(value, dict):
        for key, child in value.items():
            walk_paths(
                child,
                normalize_path(path, str(key)),
                stats,
                row_idx=row_idx,
                max_depth=max_depth - 1,
                max_items_per_array=max_items_per_array,
            )
    elif isinstance(value, list):
        for child in value[:max_items_per_array]:
            walk_paths(
                child,
                f"{path}[]" if path else "[]",
                stats,
                row_idx=row_idx,
                max_depth=max_depth - 1,
                max_items_per_array=max_items_per_array,
            )


def is_attachment_ref(value: Any) -> bool:
    return isinstance(value, dict) and value.get("type") in {
        "braintrust_attachment",
        "external_attachment",
        "inline_attachment",
    }


def find_attachment_refs(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if is_attachment_ref(value):
        found.append(path or "<root>")
    elif isinstance(value, dict):
        for key, child in value.items():
            found.extend(find_attachment_refs(child, normalize_path(path, str(key))))
    elif isinstance(value, list):
        for child in value:
            found.extend(find_attachment_refs(child, f"{path}[]" if path else "[]"))
    return found


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    sorted_values = sorted(values)
    idx = math.ceil((pct / 100) * len(sorted_values)) - 1
    return sorted_values[max(0, min(idx, len(sorted_values) - 1))]


def safe_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def get_nested(value: Any, path: str) -> Any:
    cur = value
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def first_present(row: Any, paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = get_nested(row, path)
        if value is not None:
            return value
    return None


def span_attributes(row: Any) -> dict[str, Any]:
    value = get_nested(row, "span_attributes")
    return value if isinstance(value, dict) else {}


def metrics(row: Any) -> dict[str, Any]:
    value = get_nested(row, "metrics")
    return value if isinstance(value, dict) else {}


def metadata(row: Any) -> dict[str, Any]:
    value = get_nested(row, "metadata")
    return value if isinstance(value, dict) else {}


def span_name(row: Any) -> str | None:
    value = first_present(
        row,
        (
            "span_attributes.name",
            "name",
            "metadata.name",
        ),
    )
    return str(value) if value is not None else None


def span_purpose(row: Any) -> str | None:
    value = first_present(row, ("span_attributes.purpose", "purpose"))
    return str(value) if value is not None else None


def span_type(row: Any) -> str | None:
    value = first_present(row, ("span_attributes.type", "type"))
    return str(value) if value is not None else None


def model_name(row: Any) -> str:
    value = first_present(
        row,
        (
            "metadata.model",
            "metrics.model",
            "span_attributes.model",
            "input.model",
            "output.model",
            "input.request.model",
            "output.response.model",
        ),
    )
    return str(value) if value else "<unknown>"


def token_counts(row: Any) -> tuple[int, int, int]:
    row_metrics = metrics(row)
    prompt = (
        safe_int(row_metrics.get("prompt_tokens"))
        or safe_int(row_metrics.get("input_tokens"))
        or safe_int(get_nested(row, "metadata.prompt_tokens"))
        or safe_int(get_nested(row, "metadata.input_tokens"))
    )
    completion = (
        safe_int(row_metrics.get("completion_tokens"))
        or safe_int(row_metrics.get("output_tokens"))
        or safe_int(get_nested(row, "metadata.completion_tokens"))
        or safe_int(get_nested(row, "metadata.output_tokens"))
    )
    total = (
        safe_int(row_metrics.get("total_tokens"))
        or safe_int(get_nested(row, "metadata.total_tokens"))
        or prompt + completion
    )
    return prompt, completion, total


def row_identity(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {
        "id": row.get("id"),
        "root_span_id": row.get("root_span_id"),
        "span_id": row.get("span_id"),
        "created": row.get("created"),
        "name": span_name(row),
        "purpose": span_purpose(row),
        "type": span_type(row),
    }


def add_token_record(
    bucket: dict[str, dict[str, Any]],
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    record = bucket.setdefault(
        model,
        {
            "model": model,
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    )
    record["calls"] += 1
    record["prompt_tokens"] += prompt_tokens
    record["completion_tokens"] += completion_tokens
    record["total_tokens"] += total_tokens


def scale_to_month(sample_value: int | float, sample_days: float | None) -> int | None:
    if not sample_days or sample_days <= 0:
        return None
    return int(sample_value * (30.437 / sample_days))


def build_summary(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    rows, errors = iter_input_paths([Path(p) for p in args.paths])
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total_bytes": 0, "max_bytes": 0, "count": 0, "rows": set()}
    )
    row_sizes: list[int] = []
    largest_rows: list[dict[str, Any]] = []
    attachment_paths: Counter[str] = Counter()
    span_name_counts: Counter[str] = Counter()
    scorer_name_counts: Counter[str] = Counter()
    trace_stats: dict[str, dict[str, Any]] = {}
    llm_tokens_by_model: dict[str, dict[str, Any]] = {}
    scorer_llm_tokens_by_model: dict[str, dict[str, Any]] = {}
    scorer_spans = 0
    llm_spans = 0
    topic_or_facet_spans = 0

    for idx, row in enumerate(rows):
        size = json_bytes(row)
        row_sizes.append(size)
        identity = row_identity(row)
        largest_rows.append({"row_index": idx, "estimated_bytes": size, **identity})
        walk_paths(
            row,
            "",
            stats,
            row_idx=idx,
            max_depth=args.max_depth,
            max_items_per_array=args.max_items_per_array,
        )
        attachment_paths.update(find_attachment_refs(row))

        name = identity.get("name")
        if name:
            span_name_counts[str(name)] += 1

        root_span_id = identity.get("root_span_id") or identity.get("id")
        if root_span_id:
            trace = trace_stats.setdefault(
                str(root_span_id),
                {
                    "root_span_id": root_span_id,
                    "estimated_bytes": 0,
                    "spans": 0,
                    "max_row_bytes": 0,
                    "first_created": identity.get("created"),
                    "span_names": Counter(),
                },
            )
            trace["estimated_bytes"] += size
            trace["spans"] += 1
            trace["max_row_bytes"] = max(trace["max_row_bytes"], size)
            if name:
                trace["span_names"][str(name)] += 1

        purpose = (identity.get("purpose") or "").lower()
        typ = (identity.get("type") or "").lower()
        prompt_tokens, completion_tokens, total_tokens = token_counts(row)
        model = model_name(row)

        if typ == "llm" or total_tokens > 0:
            llm_spans += 1
            add_token_record(
                llm_tokens_by_model,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

        if purpose == "scorer":
            scorer_spans += 1
            scorer_name_counts[str(name or "<unknown>")] += 1
            if typ == "llm" or total_tokens > 0:
                add_token_record(
                    scorer_llm_tokens_by_model,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )

        if typ in {"facet", "topic"} or purpose in {"facet", "topic"}:
            topic_or_facet_spans += 1

    total_bytes = sum(row_sizes)
    monthly_bytes = scale_to_month(total_bytes, args.sample_days)

    def stat_record(path: str, values: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": path,
            "total_bytes": values["total_bytes"],
            "share": (values["total_bytes"] / total_bytes) if total_bytes else 0,
            "max_bytes": values["max_bytes"],
            "count": values["count"],
            "rows": len(values["rows"]),
        }

    top_paths = [
        stat_record(path, values)
        for path, values in sorted(
            stats.items(),
            key=lambda item: item[1]["total_bytes"],
            reverse=True,
        )
        if values["total_bytes"] >= args.min_bytes
    ][: args.top]

    interesting_paths = [
        record
        for record in top_paths
        if any(part in record["path"].lower() for part in INTERESTING_NAME_PARTS)
    ]

    largest_rows = sorted(
        largest_rows,
        key=lambda item: item["estimated_bytes"],
        reverse=True,
    )[: args.top]

    largest_traces = []
    for trace in sorted(
        trace_stats.values(),
        key=lambda item: item["estimated_bytes"],
        reverse=True,
    )[: args.top]:
        names = trace["span_names"].most_common(5)
        largest_traces.append(
            {
                "root_span_id": trace["root_span_id"],
                "estimated_bytes": trace["estimated_bytes"],
                "spans": trace["spans"],
                "max_row_bytes": trace["max_row_bytes"],
                "first_created": trace["first_created"],
                "top_span_names": ", ".join(f"{name} ({count})" for name, count in names),
            }
        )

    estimated_monthly_scorer_spans = scale_to_month(scorer_spans, args.sample_days)
    estimated_monthly_llm_spans = scale_to_month(llm_spans, args.sample_days)

    cost_estimates = {
        "log_price_per_gb": args.log_price_per_gb,
        "score_price_per_1000": args.score_price_per_1000,
        "estimated_monthly_log_cost": None,
        "estimated_monthly_scorer_platform_cost": None,
    }
    if monthly_bytes is not None and args.log_price_per_gb is not None:
        cost_estimates["estimated_monthly_log_cost"] = (
            monthly_bytes / 1_000_000_000
        ) * args.log_price_per_gb
    if (
        estimated_monthly_scorer_spans is not None
        and args.score_price_per_1000 is not None
    ):
        cost_estimates["estimated_monthly_scorer_platform_cost"] = (
            estimated_monthly_scorer_spans / 1000
        ) * args.score_price_per_1000

    summary = {
        "sample_rows": len(rows),
        "estimated_sample_bytes": total_bytes,
        "estimated_monthly_bytes": monthly_bytes,
        "row_size": {
            "avg": int(total_bytes / len(row_sizes)) if row_sizes else 0,
            "p50": percentile(row_sizes, 50),
            "p95": percentile(row_sizes, 95),
            "max": max(row_sizes) if row_sizes else 0,
        },
        "top_paths": top_paths,
        "interesting_paths": interesting_paths,
        "largest_rows": largest_rows,
        "largest_traces": largest_traces,
        "span_names": [
            {"name": name, "count": count}
            for name, count in span_name_counts.most_common(args.top)
        ],
        "scorers": {
            "sample_scorer_spans": scorer_spans,
            "estimated_monthly_scorer_spans": estimated_monthly_scorer_spans,
            "by_name": [
                {"name": name, "count": count}
                for name, count in scorer_name_counts.most_common(args.top)
            ],
            "llm_tokens_by_model": sorted(
                scorer_llm_tokens_by_model.values(),
                key=lambda item: item["total_tokens"],
                reverse=True,
            )[: args.top],
        },
        "llm": {
            "sample_llm_spans": llm_spans,
            "estimated_monthly_llm_spans": estimated_monthly_llm_spans,
            "tokens_by_model": sorted(
                llm_tokens_by_model.values(),
                key=lambda item: item["total_tokens"],
                reverse=True,
            )[: args.top],
        },
        "topics": {
            "sample_topic_or_facet_spans": topic_or_facet_spans,
        },
        "attachment_references": [
            {"path": path, "count": count}
            for path, count in attachment_paths.most_common(args.top)
        ],
        "cost_estimates": cost_estimates,
        "parse_errors": errors[:20],
    }

    return summary, render_markdown(summary, args)


def format_bytes(num_bytes: int | None) -> str:
    if num_bytes is None:
        return "n/a"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1000 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1000
    return f"{num_bytes} B"


def format_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def render_table(records: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not records:
        return "_No rows._\n"
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]
    for record in records:
        values = []
        for _, key in columns:
            value = record.get(key)
            if key.endswith("bytes") or key in {"estimated_bytes", "total_bytes", "max_bytes"}:
                values.append(format_bytes(value))
            elif key == "share":
                values.append(f"{value * 100:.1f}%")
            elif value is None:
                values.append("")
            else:
                values.append(str(value).replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(summary: dict[str, Any], args: argparse.Namespace) -> str:
    lines = [
        "# Braintrust Cost Driver Estimate",
        "",
        "## Summary",
        "",
        f"- Rows analyzed: {summary['sample_rows']}",
        f"- Estimated sample bytes: {format_bytes(summary['estimated_sample_bytes'])}",
        f"- Estimated monthly bytes: {format_bytes(summary['estimated_monthly_bytes'])}",
        f"- Average row size: {format_bytes(summary['row_size']['avg'])}",
        f"- P95 row size: {format_bytes(summary['row_size']['p95'])}",
        f"- Max row size: {format_bytes(summary['row_size']['max'])}",
        f"- Scorer spans in sample: {summary['scorers']['sample_scorer_spans']}",
        f"- Estimated monthly scorer spans: {summary['scorers']['estimated_monthly_scorer_spans'] or 'n/a'}",
        f"- LLM spans in sample: {summary['llm']['sample_llm_spans']}",
        f"- Estimated monthly LLM spans: {summary['llm']['estimated_monthly_llm_spans'] or 'n/a'}",
        f"- Estimated monthly log cost: {format_money(summary['cost_estimates']['estimated_monthly_log_cost'])}",
        f"- Estimated monthly scorer platform cost: {format_money(summary['cost_estimates']['estimated_monthly_scorer_platform_cost'])}",
        "",
        "This is an approximation from exported row JSON. It ranks likely drivers; it is not a billing ledger.",
        "",
        "## Top Paths",
        "",
        render_table(
            summary["top_paths"],
            [
                ("Path", "path"),
                ("Total", "total_bytes"),
                ("Share", "share"),
                ("Max", "max_bytes"),
                ("Rows", "rows"),
                ("Count", "count"),
            ],
        ),
        "## Interesting Candidate Paths",
        "",
        render_table(
            summary["interesting_paths"],
            [
                ("Path", "path"),
                ("Total", "total_bytes"),
                ("Share", "share"),
                ("Max", "max_bytes"),
                ("Rows", "rows"),
            ],
        ),
        "## Largest Rows",
        "",
        render_table(
            summary["largest_rows"],
            [
                ("Row index", "row_index"),
                ("Bytes", "estimated_bytes"),
                ("ID", "id"),
                ("Root span", "root_span_id"),
                ("Span", "span_id"),
                ("Created", "created"),
                ("Name", "name"),
                ("Purpose", "purpose"),
                ("Type", "type"),
            ],
        ),
        "## Largest Traces",
        "",
        render_table(
            summary["largest_traces"],
            [
                ("Root span", "root_span_id"),
                ("Bytes", "estimated_bytes"),
                ("Spans", "spans"),
                ("Max row", "max_row_bytes"),
                ("Created", "first_created"),
                ("Top names", "top_span_names"),
            ],
        ),
        "## Scorers",
        "",
        "### Scorer Span Counts",
        "",
        render_table(summary["scorers"]["by_name"], [("Name", "name"), ("Count", "count")]),
        "### Scorer LLM Tokens by Model",
        "",
        render_table(
            summary["scorers"]["llm_tokens_by_model"],
            [
                ("Model", "model"),
                ("Calls", "calls"),
                ("Prompt tokens", "prompt_tokens"),
                ("Completion tokens", "completion_tokens"),
                ("Total tokens", "total_tokens"),
            ],
        ),
        "## LLM Tokens by Model",
        "",
        render_table(
            summary["llm"]["tokens_by_model"],
            [
                ("Model", "model"),
                ("Calls", "calls"),
                ("Prompt tokens", "prompt_tokens"),
                ("Completion tokens", "completion_tokens"),
                ("Total tokens", "total_tokens"),
            ],
        ),
        "## Attachment References",
        "",
        render_table(
            summary["attachment_references"],
            [("Path", "path"), ("Count", "count")],
        ),
        "## Caveats",
        "",
        "- Nested path totals overlap with parent path totals; use them for ranking, not additive accounting.",
        "- Existing rows with attachment references usually do not contain detached attachment body bytes, so attachment body usage may be underrepresented.",
        "- Scorer span counts are an approximation of score volume unless the exported rows are known to map one-to-one with score executions.",
        "- Token costs require external model pricing and any customer-specific provider discounts.",
        "- Compact JSON byte size is close enough for ranking fields but can differ from Braintrust's exact ingest accounting.",
        "- Use this report with code/config inspection before making instrumentation changes.",
        "",
    ]
    if args.sample_days:
        lines.insert(6, f"- Sample window: {args.sample_days:g} days")
    if summary["parse_errors"]:
        lines.extend(["## Parse Errors", ""])
        lines.extend(f"- {error}" for error in summary["parse_errors"])
        lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="JSON, JSONL, NDJSON, or directories to analyze")
    parser.add_argument("--sample-days", type=float, default=None, help="Days represented by the sample for monthly extrapolation")
    parser.add_argument("--top", type=int, default=25, help="Number of rows/paths to show")
    parser.add_argument("--min-bytes", type=int, default=1, help="Minimum total bytes for a path to appear")
    parser.add_argument("--max-depth", type=int, default=5, help="Maximum nested path depth to analyze")
    parser.add_argument("--max-items-per-array", type=int, default=50, help="Maximum array items to inspect per array")
    parser.add_argument("--log-price-per-gb", type=float, default=None, help="Optional log ingest price per decimal GB for rough cost estimates")
    parser.add_argument("--score-price-per-1000", type=float, default=None, help="Optional scorer platform price per 1,000 scorer spans for rough cost estimates")
    parser.add_argument("--output", help="Write Markdown report to this file")
    parser.add_argument("--json-output", help="Write machine-readable JSON summary to this file")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    summary, markdown = build_summary(args)

    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)

    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
