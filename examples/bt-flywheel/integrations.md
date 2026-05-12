# bt-flywheel Integration Examples

These examples show how to plug the skill into different runners. They are templates, not a supported multi-agent CI product.

## Portable Prompt

Use the same prompt shape with any coding agent:

```text
Use the bt-flywheel skill in skills/bt-flywheel/SKILL.md to run an autonomous improvement cycle.

System context:
- Braintrust project: <project-name>
- Agent code: <paths>
- Eval files: <paths>
- Scorers: <paths or Braintrust scorer names>
- Target metric or behavior: <goal>

When complete, write:
- bt-flywheel-summary.json
- bt-flywheel-narrative.md

Do not create PRs, issues, Slack messages, Jira tickets, or Linear tickets directly.
Instead, include adapter-neutral next_steps in bt-flywheel-summary.json.
```

## Common GitHub Actions Setup

All runners need the same basic setup. Install the whole skill directory so bundled references and scripts are available to the coding agent.

```yaml
steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0

  - name: Install Braintrust CLI
    run: |
      curl -fsSL https://bt.dev/cli/install.sh | bash
      echo "$HOME/.local/bin" >> "$GITHUB_PATH"
      echo "$HOME/.cargo/bin" >> "$GITHUB_PATH"

  - name: Install bt-flywheel skill bundle
    run: |
      mkdir -p .agent-skills
      curl -fsSL https://github.com/dpguthrie/braintrust-flywheel-plugin/archive/refs/heads/main.tar.gz \
        | tar -xz --strip-components=2 -C .agent-skills braintrust-flywheel-plugin-main/skills/bt-flywheel

  - name: Write flywheel prompt
    run: |
      cat > /tmp/bt-flywheel-prompt.md <<'EOF'
      Use the bt-flywheel skill in .agent-skills/bt-flywheel/SKILL.md to run the autonomous improvement cycle.

      System context:
      - Braintrust project: my-braintrust-project
      - Agent code: src/
      - Eval files: evals/eval_agent.py
      - Scorers: scorers.py
      - Goal: general health check

      Write bt-flywheel-summary.json and bt-flywheel-narrative.md.
      Do not directly create PRs, issues, Slack messages, Jira tickets, or Linear tickets.
      Put any recommended follow-up in next_steps.
      EOF
```

## Claude Code

Invoke Claude Code directly after the common setup, or copy the full workflow in `examples/bt-flywheel/flywheel-caller.yml`:

```yaml
- name: Run flywheel with Claude Code
  run: |
    npm install -g @anthropic-ai/claude-code
    claude --print --dangerously-skip-permissions -p "$(cat /tmp/bt-flywheel-prompt.md)"
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    BRAINTRUST_API_KEY: ${{ secrets.BRAINTRUST_API_KEY }}
    BRAINTRUST_DEFAULT_PROJECT: my-braintrust-project
    CI: "true"
    FLYWHEEL_AUTONOMOUS: "true"
```

## Codex

Use the same prompt and point Codex at the checked-out skill bundle. Adjust install/auth commands to match your Codex environment.

```yaml
- name: Run flywheel with Codex
  run: |
    npm install -g @openai/codex
    codex exec --full-auto - < /tmp/bt-flywheel-prompt.md
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    BRAINTRUST_API_KEY: ${{ secrets.BRAINTRUST_API_KEY }}
    BRAINTRUST_DEFAULT_PROJECT: my-braintrust-project
    CI: "true"
    FLYWHEEL_AUTONOMOUS: "true"
```

## Cursor

Use Cursor's agent/CLI runner if available in your environment. The important part is that the runner receives the portable prompt and can read `.agent-skills/bt-flywheel`.

```yaml
- name: Run flywheel with Cursor
  run: |
    cursor-agent --print --force "$(cat /tmp/bt-flywheel-prompt.md)"
  env:
    CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
    BRAINTRUST_API_KEY: ${{ secrets.BRAINTRUST_API_KEY }}
    BRAINTRUST_DEFAULT_PROJECT: my-braintrust-project
    CI: "true"
    FLYWHEEL_AUTONOMOUS: "true"
```

## OpenCode

Use OpenCode's non-interactive runner if available in your environment. Keep the skill path and output contract the same.

```yaml
- name: Run flywheel with OpenCode
  run: |
    # Replace with your OpenCode CLI invocation.
    opencode run --prompt-file /tmp/bt-flywheel-prompt.md
  env:
    BRAINTRUST_API_KEY: ${{ secrets.BRAINTRUST_API_KEY }}
    BRAINTRUST_DEFAULT_PROJECT: my-braintrust-project
    CI: "true"
    FLYWHEEL_AUTONOMOUS: "true"
```

## Consuming The Handoff

After any runner exits, consume the same artifacts:

```bash
jq '{outcome, severity, blocking, confidence, next_steps}' bt-flywheel-summary.json
cat bt-flywheel-narrative.md
```

Validate the summary when you include this repo's schema in your harness:

```bash
python -m jsonschema .agent-skills/bt-flywheel/schemas/bt-flywheel-summary.schema.json bt-flywheel-summary.json
```

Each next step includes:

- `intent`: adapter-neutral purpose, such as `review_change`, `investigate`, `block_release`, `rollback`, `label_data`, `rerun`, `notify`, or `no_action`.
- `priority`: `low`, `normal`, or `high`.
- `suggested_destination`: advisory routing hint, such as `code_review`, `issue_tracker`, `chat`, `release_gate`, `scheduler`, `app_ui`, `external_system`, or `none`.
- `blocking`: whether the caller should block promotion or require immediate attention.
- `requires_human_review`: whether a person should review before executing side effects.

Typical harness policy:

- Open a PR only when code changed and `next_steps` includes `intent: "review_change"` with `suggested_destination: "code_review"`.
- Create an issue/ticket when `next_steps` includes `investigate` or `label_data` with `suggested_destination: "issue_tracker"`.
- Send chat only as notification, not as the system of record.
- Fail or block a deploy when the summary has `blocking: true` or a next step has `intent: "block_release"` or `rollback`.
- Trigger generic external integrations from caller-owned configuration; never read raw webhook URLs from the summary.
- Do nothing when `outcome` is `healthy` and the only next step is `intent: "no_action"`.

## Non-CI Triggers

- Local interactive improvement session: run an agent in your repo and ask it to use `skills/bt-flywheel/SKILL.md`.
- Cron outside GitHub Actions: run the same prompt from Buildkite, CircleCI, Jenkins, Dagster, Airflow, or a plain server cron.
- Braintrust degradation alert: trigger a job when production scores drop below a threshold.
- Post-deploy check: run after a release and map blocking regressions to your release policy.
- PR command: trigger from a comment such as `/flywheel` and post the narrative back to the PR.
- Dataset refresh: run on a cadence to find production/eval coverage gaps.
- Incident follow-up: run after an incident to turn trace evidence into your team's follow-up system and eval additions.
