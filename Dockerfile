FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1
RUN pip install --no-cache-dir uv==0.8.* && useradd -m app
WORKDIR /srv
COPY pyproject.toml uv.lock README.md ./
COPY indiafacts ./indiafacts
RUN uv sync --frozen --no-dev --extra api
USER app
ENV INDIAFACTS_TRUST_PROXY=1 HOME=/home/app
EXPOSE 8000
CMD ["/srv/.venv/bin/uvicorn", "indiafacts.api:app", "--host", "0.0.0.0", "--port", "8000"]
