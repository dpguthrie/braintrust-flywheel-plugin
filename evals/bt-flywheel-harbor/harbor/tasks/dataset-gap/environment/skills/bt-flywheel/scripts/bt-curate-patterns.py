#!/usr/bin/env python3
"""Safe curation helpers for the bt-flywheel skill.

This file is import-safe: no Braintrust writes happen unless insert_labeled_rows()
is called with dry_run=False or the CLI is invoked with --execute. Writes go through
the `bt datasets` CLI so auth/profile/project behavior stays consistent with the
rest of the flywheel workflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from typing import Any

TRAIN_FRACTION = 0.8
DEFAULT_SPLIT_SEED = "flywheel-v1"
DEFAULT_LABELER_MODEL = "gpt-4o"


def generate_ground_truth(
    input_value: dict[str, Any],
    system_context: str,
    model: str = DEFAULT_LABELER_MODEL,
) -> str:
    """Generate ideal expected output for a failing production example."""
    import openai

    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"{system_context}\n\n"
                    "Given the input below, produce the ideal correct output. "
                    "Be concise and faithful to what the agent should do."
                ),
            },
            {"role": "user", "content": str(input_value)},
        ],
    )
    return response.choices[0].message.content


def assign_split(
    row_id: str,
    seed: str = DEFAULT_SPLIT_SEED,
    train_fraction: float = TRAIN_FRACTION,
) -> str:
    """Assign the same row to the same train/validation split every iteration."""
    hash_val = hashlib.sha256(f"{seed}:{row_id}".encode()).hexdigest()
    return "train" if int(hash_val, 16) % 100 < (train_fraction * 100) else "validation"


def dataset_record_id(row: dict[str, Any], project_id: str) -> str:
    """Return the stable Braintrust dataset record id for a curated production row."""
    if row.get("dataset_id"):
        return str(row["dataset_id"])
    if row.get("record_id"):
        return str(row["record_id"])
    if row.get("id"):
        return str(row["id"])
    return f"flywheel:{project_id}:{row['trace_id']}"


def build_dataset_payload(
    row: dict[str, Any],
    project_id: str,
    flywheel_iteration: str,
    split_seed: str = DEFAULT_SPLIT_SEED,
    labeler_model: str = DEFAULT_LABELER_MODEL,
) -> dict[str, Any]:
    """Build the Braintrust dataset row payload for one labeled row."""
    trace_id = row["trace_id"]
    split = assign_split(trace_id, seed=split_seed)
    bucket = row["bucket"]
    return {
        "id": dataset_record_id(row, project_id),
        "input": row["input"],
        "expected": row["expected"],
        "tags": ["production", "flywheel-curated", split, bucket],
        "metadata": {
            "source_trace_id": trace_id,
            "source_project_id": project_id,
            "production_score": row.get("score"),
            "bucket": bucket,
            "split": split,
            "labeler_model": labeler_model,
            "flywheel_iteration": flywheel_iteration,
        },
    }


def write_dataset_rows_with_bt(
    payloads: list[dict[str, Any]],
    project_name: str,
    dataset_name: str,
    create_dataset: bool = False,
    description: str | None = None,
) -> None:
    """Write dataset rows through `bt datasets create/update` using stdin JSON."""
    command = [
        "bt",
        "datasets",
        "create" if create_dataset else "update",
        dataset_name,
        "-p",
        project_name,
        "--id-field",
        "id",
        "--json",
        "--no-input",
    ]
    if create_dataset and description:
        command.extend(["--description", description])

    subprocess.run(
        command,
        input=json.dumps(payloads),
        text=True,
        check=True,
    )


def insert_labeled_rows(
    labeled_rows: list[dict[str, Any]],
    project_name: str,
    dataset_name: str,
    project_id: str,
    flywheel_iteration: str,
    dry_run: bool = True,
    create_dataset: bool = False,
    description: str | None = None,
) -> list[dict[str, Any]]:
    """Build or upsert labeled rows. Defaults to dry-run for autonomous safety."""
    payloads = [
        build_dataset_payload(
            row=row,
            project_id=project_id,
            flywheel_iteration=flywheel_iteration,
        )
        for row in labeled_rows
    ]
    if dry_run:
        return payloads

    write_dataset_rows_with_bt(
        payloads=payloads,
        project_name=project_name,
        dataset_name=dataset_name,
        create_dataset=create_dataset,
        description=description,
    )
    return payloads


def filter_validation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter fetched dataset rows to validation split."""
    return [row for row in rows if row.get("metadata", {}).get("split") == "validation"]


def _main() -> None:
    parser = argparse.ArgumentParser(description="Build or upsert bt-flywheel dataset payloads.")
    parser.add_argument("--labeled-rows", required=True, help="JSON file containing a list of labeled row objects")
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--iteration", required=True)
    parser.add_argument("--execute", action="store_true", help="Write rows to Braintrust instead of dry-running")
    parser.add_argument("--create", action="store_true", help="Create the dataset while writing rows")
    parser.add_argument("--description", help="Dataset description when --create is used")
    args = parser.parse_args()

    with open(args.labeled_rows, "r", encoding="utf-8") as fh:
        labeled_rows = json.load(fh)

    payloads = insert_labeled_rows(
        labeled_rows=labeled_rows,
        project_name=args.project_name,
        dataset_name=args.dataset_name,
        project_id=args.project_id,
        flywheel_iteration=args.iteration,
        dry_run=not args.execute,
        create_dataset=args.create,
        description=args.description,
    )
    if not args.execute:
        print(json.dumps(payloads, indent=2))


if __name__ == "__main__":
    _main()
