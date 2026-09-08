# Opt-in CPU SAM target; no checkpoint, credential or pilot image enters build.
FROM python:3.13-bookworm@sha256:62eafe52c91cad83c2c74e630bfde917da8c253673e695665d454def84fc9a13
WORKDIR /app
COPY containers/worker/sam3-requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements.lock
COPY src/specimen_digitization /app/specimen_digitization
RUN useradd --uid 10001 --create-home worker
ARG SOURCE_SHA
ENV SPECIMEN_SOURCE_SHA=$SOURCE_SHA
RUN python -c "import os,re,json,pathlib; sha=os.environ['SPECIMEN_SOURCE_SHA']; assert re.fullmatch('[0-9a-f]{40}', sha), 'SOURCE_SHA must be a full commit SHA'; pathlib.Path('/app/specimen_digitization/_build.json').write_text(json.dumps({'source_sha':sha}))"
LABEL org.opencontainers.image.revision=$SOURCE_SHA
USER 10001
ENV PYTHONUNBUFFERED=1 OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false HF_HOME=/tmp/huggingface
EXPOSE 8080
ENTRYPOINT ["python", "-m", "specimen_digitization.application.sam3_server"]
