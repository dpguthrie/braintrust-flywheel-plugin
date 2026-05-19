FROM python:3.12-bookworm

RUN apt-get update \
  && apt-get install -y --no-install-recommends bash ca-certificates curl git jq nodejs npm ripgrep \
  && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash agent

COPY evals/bt-flywheel-docker/requirements.txt /tmp/bt-flywheel-docker-requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
  && python -m pip install --no-cache-dir -r /tmp/bt-flywheel-docker-requirements.txt

USER agent
ENV HOME="/home/agent" \
    PATH="/home/agent/.local/bin:${PATH}"

RUN curl -fsSL -o /tmp/bt-installer.sh https://github.com/braintrustdata/bt/releases/latest/download/bt-installer.sh \
  && sh /tmp/bt-installer.sh \
  && rm -f /tmp/bt-installer.sh

USER root
RUN npm install -g @anthropic-ai/claude-code

USER agent
RUN claude plugin marketplace add braintrustdata/braintrust-claude-plugin \
  && claude plugin install trace-claude-code@braintrust-claude-plugin

ENV BT_FLYWHEEL_DOCKER_TRACE_CLAUDE="1" \
    PYTHONUNBUFFERED="1"

WORKDIR /workspace
ENTRYPOINT ["/workspace/evals/bt-flywheel-docker/run.sh"]
