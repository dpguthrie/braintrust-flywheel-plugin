FROM python:3.12-alpine

RUN apk add --no-cache bash coreutils curl git jq nodejs npm ripgrep

RUN adduser -D -s /bin/bash agent \
  && mkdir -p /home/agent/.npm-global \
  && chown -R agent:agent /home/agent/.npm-global

WORKDIR /app

COPY bin/bt /usr/local/bin/bt
COPY fixtures/ /fixtures/
COPY skills/ /skills/
COPY app/ /app/

RUN chmod +x /usr/local/bin/bt \
  && mkdir -p /app/.bt /logs/artifacts /logs/verifier \
  && printf '{\n  "project": "Support Agent",\n  "project_id": "proj_support_agent"\n}\n' > /app/.bt/config.json

RUN chmod -R a-w /fixtures /skills \
  && chown -R agent:agent /app /logs \
  && chmod -R a-w /app/src /app/evals /app/scorers

ENV NPM_CONFIG_PREFIX="/home/agent/.npm-global" \
    PATH="/home/agent/.npm-global/bin:/usr/local/bin:${PATH}" \
    BT_PROJECT_SNAPSHOT_FILE="/fixtures/scenario.json" \
    BT_COMMAND_LOG="/logs/artifacts/bt-command-log.jsonl" \
    FLYWHEEL_AUTONOMOUS="true" \
    FLYWHEEL_GOAL="general health check" \
    BRAINTRUST_API_KEY="sandbox-placeholder-key" \
    BRAINTRUST_DEFAULT_PROJECT="Support Agent"
