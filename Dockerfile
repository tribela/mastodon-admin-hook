FROM python:3.12.3

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /uvx /bin/

COPY . ./
RUN uv sync --frozen

CMD ["uv", "run", "uvicorn", "app:app", "--proxy-headers", "--host=0", "--port=5000"]
