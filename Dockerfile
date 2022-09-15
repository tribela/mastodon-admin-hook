FROM python:3.10

WORKDIR /app
ENV PATH="/root/.local/bin:${PATH}"

COPY pyproject.toml poetry.lock ./
RUN \
    curl -sSL https://install.python-poetry.org | POETRY_VERSION=1.2.0 python3 && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-root
COPY . ./


CMD ["uvicorn", "app:app", "--proxy-headers", "--host=0", "--port=5000"]
