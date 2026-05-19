#!/usr/bin/env python3
"""Measure deterministic trace-shape numbers from exported Braintrust spans.

Reads JSON / JSONL files produced by `bt sql --json ...` or `bt view trace --json ...`
and emits a single JSON blob of measurements to stdout (or `--output` if given).

The script does only deterministic counting and byte accounting. It does NOT emit
findings, severities, or recommendations — that's the agent's job. The output is
the raw signal the agent uses to inform interpretation against the rubrics in
`references/`.

Measurements:
  - sample_summary: counts of spans, distinct traces, roots, LLM spans, scorer spans
  - field_bytes:    top-N field paths under input/output/metadata by total JSON bytes
  - payload_size:   per-span byte distribution (median, p95, p99, max)
  - duplicate_bytes: large input/output payloads hashed across spans within the
                     same trace; reports bytes appearing on >1 span
  - spans_per_trace: median, p95, max
  - span_names:     distinct count, anonymous count, singleton count, top-N
  - llm_completeness: ratios for metadata.model / metrics.prompt_tokens / metrics.completion_tokens
  - scorer_spans:   total ratio + token totals by model
"""

from __future__ import annotations

import argparse
import json
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


def read_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("rows", "data", "objects", "results", "spans"):
            if key in data and isinstance(data[key], list):
                return [r for r in data[key] if isinstance(r, dict)]
        return [data]
    return []


def json_bytes(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
    except Exception:
        return len(str(value).encode("utf-8", errors="replace"))


def dig(row: dict[str, Any], path: str) -> Any:
    cur: Any = row
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str, sort_keys=True).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:16]


def percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    values_sorted = sorted(values)
    idx = min(len(values_sorted) - 1, int(len(values_sorted) * p))
    return values_sorted[idx]


def is_root(row: dict[str, Any]) -> bool:
    if row.get("is_root") is True:
        return True
    rsid = row.get("root_span_id")
    sid = row.get("span_id") or row.get("id")
    return bool(rsid and sid and rsid == sid)


def measure(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    llm_spans = [r for r in rows if dig(r, "span_attributes.type") == "llm"]
    scorer_spans = [r for r in rows if dig(r, "span_attributes.purpose") == "scorer"]
    roots = [r for r in rows if is_root(r)]

    by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        rid = r.get("root_span_id") or r.get("span_id") or r.get("id")
        if rid:
            by_root[rid].append(r)

    # Per-span total bytes (compact JSON of input + output + metadata)
    payload_sizes: list[int] = []
    for r in rows:
        size = sum(json_bytes(r.get(k)) for k in ("input", "output", "metadata") if r.get(k) is not None)
        payload_sizes.append(size)

    # Field-bytes attribution under top-level containers
    field_totals: Counter[str] = Counter()
    for r in rows:
        for top in ("input", "output", "metadata"):
            value = r.get(top)
            if isinstance(value, dict):
                for k, v in value.items():
                    field_totals[f"{top}.{k}"] += json_bytes(v)
            elif value is not None:
                field_totals[top] += json_bytes(value)
    top_fields = [{"path": p, "bytes": b} for p, b in field_totals.most_common(20)]

    # Duplicate payload bytes within a trace (parent↔child)
    DUP_MIN = 1024  # only count payloads ≥1 KB
    dup_bytes = 0
    dup_occurrences = 0
    for trace_spans in by_root.values():
        if len(trace_spans) < 2:
            continue
        seen_hashes: dict[str, int] = {}
        for span in trace_spans:
            for field_name in ("input", "output"):
                value = span.get(field_name)
                if value is None:
                    continue
                size = json_bytes(value)
                if size < DUP_MIN:
                    continue
                h = stable_hash(value)
                if h in seen_hashes:
                    dup_occurrences += 1
                    dup_bytes += size
                else:
                    seen_hashes[h] = size

    # Spans per trace
    spans_per_trace = sorted(len(v) for v in by_root.values())

    # Span names
    name_counts: Counter[str] = Counter(
        (dig(r, "span_attributes.name") or r.get("name") or "").strip() for r in rows
    )
    ANON = {"", "anonymous", "<anonymous>", "default", "function"}
    anon_count = sum(c for n, c in name_counts.items() if n.lower() in ANON)
    singleton_count = sum(1 for n, c in name_counts.items() if c == 1)
    top_names = [{"name": n, "count": c} for n, c in name_counts.most_common(20)]

    # LLM completeness ratios
    llm_n = len(llm_spans)
    llm_completeness = None
    if llm_n:
        with_model = sum(1 for r in llm_spans if dig(r, "metadata.model"))
        with_prompt = sum(1 for r in llm_spans if dig(r, "metrics.prompt_tokens") is not None)
        with_completion = sum(1 for r in llm_spans if dig(r, "metrics.completion_tokens") is not None)
        llm_completeness = {
            "llm_spans": llm_n,
            "with_model": with_model,
            "with_model_ratio": with_model / llm_n,
            "with_prompt_tokens": with_prompt,
            "with_prompt_tokens_ratio": with_prompt / llm_n,
            "with_completion_tokens": with_completion,
            "with_completion_tokens_ratio": with_completion / llm_n,
        }

    # Root span input/output emptiness
    def empty(v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str) and len(v.strip()) < 5:
            return True
        if isinstance(v, (dict, list)) and not v:
            return True
        return False

    root_io = None
    if roots:
        empty_in = sum(1 for r in roots if empty(r.get("input")))
        empty_out = sum(1 for r in roots if empty(r.get("output")))
        root_io = {
            "root_count": len(roots),
            "empty_input": empty_in,
            "empty_input_ratio": empty_in / len(roots),
            "empty_output": empty_out,
            "empty_output_ratio": empty_out / len(roots),
        }

    # Scorer spans
    scorer_summary = None
    if scorer_spans:
        by_model: dict[str | None, dict[str, int]] = defaultdict(
            lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        )
        for r in scorer_spans:
            model = dig(r, "metadata.model")
            by_model[model]["calls"] += 1
            by_model[model]["prompt_tokens"] += int(dig(r, "metrics.prompt_tokens") or 0)
            by_model[model]["completion_tokens"] += int(dig(r, "metrics.completion_tokens") or 0)
        scorer_summary = {
            "scorer_spans": len(scorer_spans),
            "scorer_to_total_ratio": len(scorer_spans) / total if total else 0,
            "by_model": [
                {"model": m, **stats} for m, stats in by_model.items()
            ],
        }

    # Session split (by likely correlation fields)
    session_split = None
    for path in ("metadata.session_id", "metadata.conversation_id", "metadata.thread_id"):
        session_to_roots: dict[Any, set[str]] = defaultdict(set)
        for r in rows:
            sid = dig(r, path)
            rid = r.get("root_span_id") or r.get("span_id") or r.get("id")
            if sid is not None and rid:
                session_to_roots[sid].add(rid)
        if session_to_roots:
            split = {s: len(rs) for s, rs in session_to_roots.items() if len(rs) > 1}
            session_split = {
                "field": path,
                "sessions": len(session_to_roots),
                "sessions_with_multiple_roots": len(split),
            }
            break

    return {
        "sample_summary": {
            "spans": total,
            "distinct_traces": len(by_root),
            "root_spans": len(roots),
            "llm_spans": llm_n,
            "scorer_spans": len(scorer_spans),
        },
        "payload_size_bytes": {
            "median": percentile(payload_sizes, 0.5),
            "p95": percentile(payload_sizes, 0.95),
            "p99": percentile(payload_sizes, 0.99),
            "max": max(payload_sizes) if payload_sizes else 0,
        },
        "field_bytes_top": top_fields,
        "duplicate_payload": {
            "min_payload_bytes": DUP_MIN,
            "duplicate_occurrences": dup_occurrences,
            "duplicate_bytes": dup_bytes,
        },
        "spans_per_trace": {
            "median": percentile(spans_per_trace, 0.5),
            "p95": percentile(spans_per_trace, 0.95),
            "max": spans_per_trace[-1] if spans_per_trace else 0,
        },
        "span_names": {
            "distinct": len(name_counts),
            "anonymous_count": anon_count,
            "singleton_count": singleton_count,
            "top": top_names,
        },
        "root_io": root_io,
        "llm_completeness": llm_completeness,
        "scorer": scorer_summary,
        "session_split": session_split,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="JSON / JSONL files exported from `bt sql` or `bt view`")
    parser.add_argument("--output", help="Optional JSON output path (default: stdout)")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    rows: list[dict[str, Any]] = []
    for raw in args.inputs:
        p = Path(raw)
        if not p.exists():
            print(f"warn: skipping missing file {p}", file=sys.stderr)
            continue
        rows.extend(read_file(p))

    if not rows:
        print("error: no rows parsed from inputs", file=sys.stderr)
        return 2

    result = measure(rows)
    serialized = json.dumps(result, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(serialized, encoding="utf-8")
        print(f"wrote {args.output}: {result['sample_summary']['spans']} spans across {result['sample_summary']['distinct_traces']} traces", file=sys.stderr)
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    sys.exit(main())
