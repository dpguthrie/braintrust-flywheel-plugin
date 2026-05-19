# Simple Docker bt eval

This is the small, separate path. It does not use Harbor.

It builds a container with:

- Python + `braintrust`
- the `bt` CLI
- Claude Code
- Braintrust's `trace-claude-code` plugin

The command inside the container is still:

```bash
bt eval --runner python3 evals/bt-flywheel-docker/eval_subprocess.py
```

Run it from the repo root:

```bash
UPLOAD=1 evals/bt-flywheel-docker/run_docker.sh
```

The default Claude Code model is `claude-sonnet-4-6`. Override it with
`BT_FLYWHEEL_DOCKER_MODEL` when you want to test a different Claude Code model
or alias.

The repo is mounted at `/workspace`. A repo-root `.env` is passed at runtime when present, so `BRAINTRUST_API_KEY` and Claude auth are not baked into the image.

When upload/tracing is enabled, the eval passes Claude Code:

```text
TRACE_TO_BRAINTRUST=true
CC_PARENT_SPAN_ID=<Braintrust task child span id>
CC_ROOT_SPAN_ID=<Braintrust eval row root span id>
CC_EXPERIMENT_ID=<Braintrust experiment id>
```

That is the key difference from the Harbor importer path: Braintrust owns the eval trace directly, and Claude Code attaches under the row span.
