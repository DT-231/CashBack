FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir .
COPY . .
CMD ["alembic", "upgrade", "head"]
