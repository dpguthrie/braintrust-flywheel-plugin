"""bt-flywheel artifact mapping for the Harbor-to-Braintrust importer."""

from __future__ import annotations

from braintrust_harbor import ArtifactSpec, SuiteArtifactConfig


BT_FLYWHEEL_SUITE_ARTIFACTS = SuiteArtifactConfig(
    artifacts=(
        ArtifactSpec(
            key="summary_json",
            paths=("bt-flywheel-summary.json",),
            kind="json",
        ),
        ArtifactSpec(
            key="narrative_text",
            paths=("bt-flywheel-narrative.md",),
            kind="text",
            limit=20000,
        ),
        ArtifactSpec(
            key="command_log",
            paths=("bt-command-log.jsonl",),
            kind="jsonl",
        ),
    ),
    command_log_key="command_log",
    command_span_prefix="bt",
    command_tool_name="bt",
)
