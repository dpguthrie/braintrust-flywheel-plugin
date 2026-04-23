# bt eval Patterns

## Important Notes

- `bt eval` supports `--env-file <PATH>`, but sourcing `.env` manually is preferred — it ensures auth resolves before `load_dotenv()` is called inside eval scripts
- Prefer `bt eval`; fall back to `braintrust eval` if `bt eval` fails or is unavailable
- Always run a smoke run (`--first 20`) before a full eval during active iteration — it catches catastrophic failures fast
- `bt eval` output includes the experiment ID on completion — capture this for the Analyze phase

---

## Standard Invocation (bt eval preferred)

```bash
# Source .env first — bt CLI auth runs before load_dotenv() in eval scripts
set -a && source .env && set +a
bt eval <eval_file>
```

## Fallback: braintrust eval (supports --env-file natively)

```bash
braintrust eval --env-file .env <eval_file>
```

## Smoke Run (first 20 examples — fast sanity check)

> Check `bt eval --help` first — `--first` may not be available in your `bt` version.

```bash
set -a && source .env && set +a
bt eval --first 20 <eval_file>
```

If smoke run shows near-zero scores: **stop and go back to Curate/Iterate**. Do not run full eval.

## Deterministic Sample (reproducible subset for CI)

> Check `bt eval --help` first — `--sample` and `--sample-seed` may not be available in your `bt` version.

```bash
set -a && source .env && set +a
bt eval --sample 20 --sample-seed 7 <eval_file>
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
