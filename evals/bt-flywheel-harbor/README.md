# bt-flywheel Harbor Eval

This is the Braintrust-Harbor approach.

Use it when you want Harbor to own sandboxed agent execution, task artifacts,
multi-agent adapters, and trial concurrency. The runner materializes Harbor task
variants and imports the completed Harbor job into Braintrust.

Run locally without upload:

```bash
evals/bt-flywheel-harbor/run.sh
```

Upload imported Harbor rows to Braintrust:

```bash
UPLOAD=1 evals/bt-flywheel-harbor/run.sh
```

Useful filters:

```bash
HARBOR_SCENARIOS=measurement-gap \
HARBOR_SKILL_VARIANTS=with-skill \
HARBOR_TARGETS=codex-gpt-5.4 \
evals/bt-flywheel-harbor/run.sh
```

The Harbor path is implemented by:

- `run.sh`
- `run_harbor_batch.py`
- `suite.toml`
- `suite_artifacts.py`
- `scorers.py`
- `harbor/tasks/...`

For the separate minimal Docker/`bt eval` subprocess approach, see
`evals/bt-flywheel-docker/`.
