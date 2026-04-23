# bt eval Patterns

## Important Notes

- `bt eval` supports `--env-file <PATH>`, but sourcing `.env` manually is preferred — it ensures auth resolves before `load_dotenv()` is called inside eval scripts
- Prefer `bt eval`; fall back to `braintrust eval` if `bt eval` fails or is unavailable
- Always run a smoke run (`--first 20`) before a full eval during active iteration — it catches catastrophic failures fast
- `bt eval` output includes the experiment ID on completion — capture this for the Analyze phase

---

## Standard Invocation

```bash
# Source .env first — bt CLI auth runs before load_dotenv() in eval scripts
set -a && source .env && set +a
bt eval <eval_file>
```

## Fallback: braintrust eval (supports --env-file natively)

```bash
braintrust eval --env-file .env <eval_file>
```

---

## Smoke Run (first N examples — fast sanity check)

```bash
set -a && source .env && set +a
bt eval --first 20 <eval_file>
```

If smoke run shows near-zero scores: **stop and go back to Curate/Iterate**. Do not run full eval.

---

## Deterministic Sample (reproducible subset for CI)

```bash
set -a && source .env && set +a
bt eval --sample 20 --sample-seed 7 <eval_file>
```

---

## Watch Mode (re-run on file changes — useful during iteration)

```bash
set -a && source .env && set +a
bt eval --watch <eval_file>
```

---

## Filter: Run Only Specific Evaluators

```bash
bt eval --filter <expression> <eval_file>
```

---

## Override Evaluator Parameters

```bash
# Override individual parameters (value is JSON)
bt eval --param model='"claude-sonnet-4-6"' <eval_file>
bt eval --param temperature=0.7 <eval_file>

# Override multiple parameters at once with a JSON object
bt eval --param '{"model":"claude-sonnet-4-6","temperature":0.7}' <eval_file>
```

---

## Run Without Sending Logs (local-only)

```bash
bt eval --no-send-logs <eval_file>
```

---

## Finding Eval Files

Check in this order:
1. Project `CLAUDE.md` — look for entries listing eval files or an `evals/` directory
2. Search the repo:
   ```bash
   find . -name "eval_*.py" -o -name "eval_*.ts" | grep -v node_modules | grep -v .venv
   ```
3. Check for an `evals/` directory:
   ```bash
   ls evals/ 2>/dev/null
   ```
