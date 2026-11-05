FROM public.ecr.aws/docker/library/python:3.13-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

COPY app ./app
COPY metadata ./metadata
COPY web ./web
COPY scripts/run_api.py ./scripts/run_api.py

ENV QUERY_ENGINE=maxcompute
EXPOSE 8000
CMD [".venv/bin/python", "scripts/run_api.py"]
