# Evals

Offline evals are grouped by skill and validate the behavior of the skill itself.

| Skill | Evals |
|---|---|
| `bt-flywheel` | [`bt-flywheel/eval_scorers.py`](bt-flywheel/eval_scorers.py), [`bt-flywheel/eval_behavior.py`](bt-flywheel/eval_behavior.py), [`bt-flywheel-harness/eval_harness.py`](bt-flywheel-harness/eval_harness.py) |

Only add evals here when they test a skill's behavior, bundled scorers, or prompt quality. Product or customer evals should live in the caller repository.

`bt-flywheel-harness/` is a fixture-repo harness for offline skill evaluation. It uses a fake `bt` CLI by default so scenario results are deterministic and can run in CI without live Braintrust credentials.
