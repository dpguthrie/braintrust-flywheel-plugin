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
Instead, include recommended_actions in bt-flywheel-summary.json.
```

## Common GitHub Actions Setup

All runners need the same basic setup:

```yaml
steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0

  - name: Install Braintrust CLI
    run: |
      curl -fsSL https://bt.dev/cli/install.sh | bash
      echo "$HOME/.local/bin" >> $GITHUB_PATH
      echo "$HOME/.cargo/bin" >> $GITHUB_PATH

  - name: Install bt-flywheel skill bundle
    run: |
      mkdir -p .agent-skills
      curl -fsSL https://github.com/dpguthrie/flywheel-plugin/archive/refs/heads/main.tar.gz \
        | tar -xz --strip-components=2 -C .agent-skills flywheel-plugin-main/skills/bt-flywheel

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
      Put any recommended follow-up in recommended_actions.
      EOF
```

## Claude Code

Use the reusable workflow in this repo if you want a complete Claude Code harness with PR/issue handling:

```yaml
jobs:
  flywheel:
    uses: dpguthrie/flywheel-plugin/.github/workflows/bt-flywheel-claude.yml@main
    with:
      project_name: my-braintrust-project
      system_context: |
        Agent code: src/
        Eval files: evals/eval_agent.py
        Scorers: scorers.py
      code_paths: src/ evals/ scorers.py
      act_mode: auto
    secrets: inherit
```

Or invoke Claude Code directly after the common setup:

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

## Consuming Act Recommendations

After any runner exits, consume the same artifacts:

```bash
jq '.recommended_actions' bt-flywheel-summary.json
cat bt-flywheel-narrative.md
```

Validate the summary when you include this repo's schema in your harness:

```bash
python -m jsonschema schemas/bt-flywheel-summary.schema.json bt-flywheel-summary.json
```

Typical harness policy:

- Open a PR only when code changed and `recommended_actions` includes `pull_request`.
- Create an issue/ticket when `recommended_actions` includes `issue`, `jira`, or `linear`.
- Send Slack only as notification, not as the system of record.
- Do nothing when the action type is `none`.

## Non-CI Triggers

- Local interactive improvement session: run an agent in your repo and ask it to use `skills/bt-flywheel/SKILL.md`.
- Cron outside GitHub Actions: run the same prompt from Buildkite, CircleCI, Jenkins, Dagster, Airflow, or a plain server cron.
- Braintrust degradation alert: trigger a job when production scores drop below a threshold.
- Post-deploy check: run after a release and route regressions to issues or Slack.
- PR command: trigger from a comment such as `/flywheel` and post the narrative back to the PR.
- Dataset refresh: run on a cadence to find production/eval coverage gaps.
- Incident follow-up: run after an incident to turn trace evidence into a ticket and eval additions.
