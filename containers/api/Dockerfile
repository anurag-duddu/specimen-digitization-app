# Build from repository root. Base images and Python dependencies are immutable.
FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv
FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7 AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
ARG SOURCE_SHA
RUN python -c 'import json,os,re; from pathlib import Path; sha=os.environ["SOURCE_SHA"]; assert re.fullmatch("[a-f0-9]{40}",sha); Path("src/specimen_digitization/application/_build.json").write_text(json.dumps({"source_sha":sha}))'
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
ARG SOURCE_SHA
LABEL org.opencontainers.image.source="https://github.com/anurag-duddu/specimen-digitization-app" \
      org.opencontainers.image.revision=$SOURCE_SHA
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
COPY --from=build /app/.venv /app/.venv
USER 65532:65532
WORKDIR /app
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["specimen-api", "--mode", "production"]
