FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv
FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
ARG SOURCE_SHA
RUN SOURCE_SHA="$SOURCE_SHA" python -c "import json,os,re,pathlib; s=os.environ['SOURCE_SHA']; assert re.fullmatch('[0-9a-f]{40}', s), 'SOURCE_SHA must be a full commit SHA'; pathlib.Path('src/specimen_digitization/_build.json').write_text(json.dumps({'source_sha':s}))"
LABEL org.opencontainers.image.revision=$SOURCE_SHA
RUN uv sync --frozen --no-dev --no-editable && useradd --uid 10001 --create-home worker
USER 10001
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["specimen-worker"]
CMD ["--mode", "production"]
