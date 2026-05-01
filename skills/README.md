# Skills Catalog

This directory contains installable Braintrust skills. Each child directory is a complete skill bundle that can be copied or installed independently.

## Skills

| Skill | Description | Entry point |
|---|---|---|
| `bt-flywheel` | Evidence-backed improvement loop for Braintrust-backed agents. | [`bt-flywheel/SKILL.md`](bt-flywheel/SKILL.md) |
| `bt-cost-optimizer` | Usage-cost analysis across logs, scorers, Topics, Gateway/provider spend, datasets, and experiments. | [`bt-cost-optimizer/SKILL.md`](bt-cost-optimizer/SKILL.md) |

## Skill Package Contract

Every skill should follow this shape:

```text
<skill-name>/
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
  assets/
```

- `SKILL.md` is required and is the canonical per-skill documentation.
- `agents/openai.yaml` is recommended for UI metadata.
- `references/` holds detailed context loaded only when needed.
- `scripts/` holds deterministic helpers that belong with the skill.
- `assets/` is optional and should contain reusable output resources.

Avoid per-skill `README.md` files unless there is a human-only document that clearly does not belong in `SKILL.md`. In most cases, use `SKILL.md` for per-skill navigation and this catalog for repository navigation.

## Adding a Skill

1. Create `skills/<skill-name>/SKILL.md` with clear `name` and `description` frontmatter.
2. Add `agents/openai.yaml`.
3. Put detailed references and scripts inside that skill directory.
4. Add runner examples under `examples/<skill-name>/` if needed.
5. Add skill-specific evals or scorers under `evals/<skill-name>/` or `scorers/<skill-name>/` only if they validate or support that skill.
6. Update this catalog and the root README.
