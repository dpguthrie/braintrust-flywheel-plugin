# Evals

Offline evals are grouped by skill and validate the behavior of the skill itself.

| Skill | Evals |
|---|---|
| `bt-flywheel` | [`bt-flywheel/eval_scorers.py`](bt-flywheel/eval_scorers.py), [`bt-flywheel/eval_behavior.py`](bt-flywheel/eval_behavior.py) |

Only add evals here when they test a skill's behavior, bundled scorers, or prompt quality. Product or customer evals should live in the caller repository.
