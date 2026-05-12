# bt-flywheel Skill Evaluation Strategy

This document records the current gaps in the fixture harness and the recommended direction for evaluating `bt-flywheel` as a skill.

## Current Gaps

The current offline harness is useful, but it is not yet the strongest answer to "does this skill help?"

- The scripted runner is a harness smoke test, not an agent eval. It proves the checks work, not that the skill helps.
- The fixture repos are tiny. They do not reflect large repos, messy histories, real dependency failures, ambiguous product constraints, or long-running agent behavior.
- The fake `bt` shim is hand-authored. It does not yet replay real Braintrust projects or test whether SQL/search queries are semantically good.
- Deterministic checks are partly term-based and can be gamed by summaries that mention expected words without doing deep diagnosis.
- Full Claude/Codex transcripts are not parsed into first-class trace events yet. The harness captures stdout/stderr, changed files, and fake `bt` commands, but not a rich tool-call trace.
- The bundled handoff JSON Schema is not yet used for validation; the harness has a lightweight structural check.
- The optional LLM judge is available behind `FLYWHEEL_HARNESS_LLM_JUDGE=1`, but it is not calibrated against human labels.
- There is no repeated-run flakiness measurement, statistical comparison, cost tracking, or token accounting.
- `none` vs `current` is meaningful only with a real agent runner. With `scripted`, both variants execute the same canned behavior.
- This evaluates skill execution in fixture repos. It does not yet evaluate live production Braintrust projects, real project auth, or real `bt` CLI behavior.
- There is no easy "I already ran the skill; score that run" path. That is probably the most important missing workflow.

## Foundational Position

The primary evaluation target should be the observed agent-harness run, not the fixture harness.

For this skill, the question is not just "did a final JSON artifact look right?" The question is:

- Did the agent discover the right production evidence?
- Did it inspect enough of the repository and Braintrust state before editing?
- Did it choose the right intervention type: measurement, dataset, agent, instrumentation, or no change?
- Did it verify changes and handle regressions correctly?
- Did the handoff give the surrounding workflow enough structured state to act safely?
- Did using the skill improve behavior compared with not using it or using a previous skill version?

Those are trace-level questions. They require the task prompt, runner, repository state, tool calls, `bt` queries, file changes, tests, generated artifacts, and final handoff to be visible together.

Braintrust is the right fit when it becomes the system of record for those runs:

- A skill run can be logged as a trace with spans for setup, agent execution, tool calls, artifact collection, tests, and handoff parsing.
- Trace-level scorers can evaluate behavior across the whole run, including `trace.getSpans()` data.
- Online scoring can score real skill runs as they happen, asynchronously, without making the developer wait.
- Experiments can compare skill versions, runners, prompts, and scenario sets side by side.
- Remote evals or sandboxes can invoke complex agent harnesses while Braintrust still owns comparison, scoring, and review.

References:

- Braintrust evaluation anatomy: data, task, scores, experiments, online monitoring: https://www.braintrust.dev/docs/evaluate
- Online scoring for production traces and trace-level scorers: https://www.braintrust.dev/docs/observe/score-online
- Remote evals and sandboxes for complex agent code: https://www.braintrust.dev/docs/evaluate/remote-evals
- Custom tracing for tool calls and workflow spans: https://www.braintrust.dev/docs/instrument/custom-tracing

## Recommended Architecture

Use an online trace-first architecture as the main product/demo path.

1. **Run capture**
   - A thin wrapper runs Claude, Codex, or another agent exactly as the user would.
   - The wrapper logs one Braintrust trace per skill run.
   - Metadata includes skill name/version/path, runner, model, repo URL or local path, git SHA, scenario or trigger, harness version, and whether the skill was enabled.
   - Artifacts include prompt, stdout/stderr or transcript, changed files, git diff, `bt-flywheel-summary.json`, `bt-flywheel-narrative.md`, acceptance test output, and command logs.

2. **Trace shape**
   - Root span: `bt-flywheel.skill_run`
   - Child spans: `setup`, `agent_invocation`, `braintrust_discovery`, `repo_changes`, `verification`, `handoff_parse`, `artifact_upload`
   - Tool spans should preserve command, cwd, exit status, duration, and a bounded stdout/stderr sample.
   - Handoff parse span should include normalized JSON plus schema validation results.

3. **Online scorers**
   - Structural scorers: summary present, schema valid, required fields, next-step contract.
   - Process scorers: evidence before change, smoke before full eval, no credential seeking, efficient command use.
   - Outcome scorers: expected outcome for known scenarios, tests passed, diff matches allowed change policy.
   - Judgment scorers: diagnosis quality, evidence grounding, intervention appropriateness, handoff usefulness.
   - Comparative scorers: did this run beat the no-skill or previous-skill baseline for the same scenario?

4. **Experiment mode**
   - Braintrust Eval remains useful, but as a controlled comparison mode over actual runner invocations.
   - Rows should be `scenario × runner × skill_variant`.
   - The task should invoke the real runner and return a trace/artifact bundle, not a scripted answer.
   - Fixture repos and fake `bt` can still exist for deterministic CI, but they should not be presented as proof that the skill works.

5. **Bring-your-own-run mode**
   - This should be the easiest setup path.
   - A developer runs the skill locally or in CI.
   - A capture command uploads the run artifacts to Braintrust.
   - Online scorers evaluate the run automatically.
   - This creates immediate value even before a team builds a full scenario matrix.

## What To Build Next

Prioritize the path that produces real, scored agent traces with the least setup.

1. Add a `bt-flywheel-capture` script or harness mode that logs an already-completed run to Braintrust.
2. Add schema-backed handoff validation and expose validation errors as scorer metadata.
3. Adapt existing online scorers so they work against the captured trace shape, not only agent-specific span names.
4. Run Claude on the current scenarios and store real traces/artifacts in Braintrust.
5. Add one hard scenario where `none` should fail and `current` should help, then compare both runs in Braintrust.
6. Only after that, expand fixture coverage and recorded `bt` replay.

## Role Of The Current Offline Harness

The offline harness should remain, but its role should be explicit:

- It is a deterministic development harness for scorer and runner plumbing.
- It is a CI smoke test for the fake `bt` shim, fixture setup, artifact extraction, and score calculation.
- It is a way to create controlled scenario rows for Braintrust Eval.
- It is not, by itself, evidence that the skill improves real agent behavior.

The demo should lead with real traces and online scoring. The offline harness should support that story, not be the story.
