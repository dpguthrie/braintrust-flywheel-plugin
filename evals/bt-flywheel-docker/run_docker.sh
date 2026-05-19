#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
IMAGE="${BT_FLYWHEEL_DOCKER_IMAGE:-bt-flywheel-docker-eval:local}"

if [[ ! -f "${REPO_ROOT}/evals/bt-flywheel-docker/requirements.txt" ]]; then
  echo "Could not find repo root from ${SCRIPT_DIR}" >&2
  exit 1
fi

docker build -f "${SCRIPT_DIR}/Dockerfile" -t "${IMAGE}" "${REPO_ROOT}"

docker_args=(
  run
  --rm
  --workdir /workspace
  --volume "${REPO_ROOT}:/workspace"
)

if [[ "${BT_FLYWHEEL_DOCKER_LOAD_ENV:-1}" == "1" && -f "${REPO_ROOT}/.env" ]]; then
  docker_args+=(--env-file "${REPO_ROOT}/.env")
fi

while IFS='=' read -r name _; do
  case "${name}" in
    ANTHROPIC_*|BRAINTRUST_*|BT_*|CLAUDE_CODE_*|OPENAI_*|UPLOAD|TRACE_TO_BRAINTRUST)
      docker_args+=(--env "${name}")
      ;;
  esac
done < <(env)

docker_args+=("${IMAGE}")
exec docker "${docker_args[@]}"
